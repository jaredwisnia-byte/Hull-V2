"""QA against what the object is supposed to look like.

Two checks, both on the exported mesh:

1. Against the drawing (propkit/drafting.py), in millimetres: the mesh is projected along each
   drawing view's axis and its outline compared with the drawn profile on the same metric
   grid, aligned at the lower-left corner and never stretched to fit. Reports overlap (IoU),
   the 95th-percentile distance between the two outlines, and each overall size's error.
   A wrong proportion, a missing taper or a boxed-in round shows here, unlike a comparison
   that rescales the mesh's outline to the reference first.

2. Against the sheet's pictorial (isometric/perspective) views, by computer vision: the camera
   angle is searched until the mesh's outline best matches the picture's outline (scale and
   position fitted to the outline's box); the best overlap is the score and an overlay image is
   saved for review. A pictorial view is the closest thing on the sheet to "what it really
   looks like", and it was never used to build the mesh, so it is an independent witness.
"""
import json
import math
import os
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

DRAWING_IOU = 0.90          # the mesh's outline must cover the drawn profile this well...
DRAWING_P95_FRAC = 0.03     # ...and stay within 3% of the object's size (95% of the outline)
PICTORIAL_IOU = 0.85        # best-pose outline overlap with the sheet's pictorial view
GRID_MM = 0.5

AXES = {'front': (0, 2, False), 'back': (0, 2, True), 'right': (1, 2, False), 'left': (1, 2, True),
        'top': (0, 1, False), 'bottom': (0, 1, True)}


def _raster(points2d, tris, shape, scale, origin):
    """Fill triangles (2D points in mm) into a mask of `shape` (rows up from origin)."""
    h, w = shape
    im = Image.new('L', (w, h), 0)
    dr = ImageDraw.Draw(im)
    P = (points2d - origin) / scale
    P[:, 1] = h - P[:, 1]
    for t in tris:
        dr.polygon([tuple(P[i]) for i in t], fill=255)
    return np.asarray(im) > 0


def _outline_distance(a, b, scale):
    """95th-percentile distance (mm) from each outline to the other (symmetric)."""
    ea = a & ~ndimage.binary_erosion(a)
    eb = b & ~ndimage.binary_erosion(b)
    if not ea.any() or not eb.any():
        return float('inf')
    da = ndimage.distance_transform_edt(~eb)[ea]
    db = ndimage.distance_transform_edt(~ea)[eb]
    return float(np.percentile(np.r_[da, db], 95) * scale)


def _drawn_mask(record, view, scale):
    from .drafting import rasterize
    prof = record['profiles'][view]
    w, h = prof['image_px']
    size = {k: v * 1000 for k, v in record['size_m'].items()}
    su = {'front': 'width', 'back': 'width', 'right': 'depth', 'left': 'depth', 'top': 'width', 'bottom': 'width'}[view]
    sv = {'front': 'height', 'back': 'height', 'right': 'height', 'left': 'height', 'top': 'depth', 'bottom': 'depth'}[view]
    m = rasterize(np.asarray(prof['vertices_px']), (h, w), openings=prof.get('openings', ()))
    gw, gh = max(2, int(round(size[su] / scale))), max(2, int(round(size[sv] / scale)))
    return np.asarray(Image.fromarray(m.astype(np.uint8) * 255).resize((gw, gh), Image.Resampling.BILINEAR)) >= 128


def against_drawing(verts, tris, record, out_dir=None):
    """verts: (N,3) metres in the asset frame (x right, y back, z up); tris: (M,3)."""
    V = np.asarray(verts, float) * 1000.0
    T = np.asarray(tris, int)
    lo = V.min(0)
    size_mm = {k: v * 1000 for k, v in record['size_m'].items()}
    big = max(size_mm.values())
    metrics, fails = {}, []
    got_size = V.max(0) - lo
    for i, (k, want) in enumerate((('width', size_mm['width']), ('depth', size_mm['depth']),
                                   ('height', size_mm['height']))):
        err = float(got_size[i] - want)
        metrics.setdefault('size_error_mm', {})[k] = round(err, 1)
        if abs(err) > max(2.0, 0.03 * want):
            fails.append('overall %s is %.1f mm against the drawing\'s %.1f mm' % (k, got_size[i], want))
    for view in record['profiles']:
        if view not in AXES:
            continue
        a, b, flip = AXES[view]
        drawn = _drawn_mask(record, view, GRID_MM)
        P = V[:, [a, b]] - lo[[a, b]]
        if flip:
            P[:, 0] = got_size[a] - P[:, 0]
        if view == 'bottom':
            P[:, 1] = got_size[b] - P[:, 1]
        got = _raster(P, T, drawn.shape, GRID_MM, np.zeros(2))
        iou = float((got & drawn).sum() / max(1, (got | drawn).sum()))
        p95 = _outline_distance(got, drawn, GRID_MM)
        metrics.setdefault('views', {})[view] = {'iou': round(iou, 3), 'outline_p95_mm': round(p95, 2)}
        if iou < DRAWING_IOU or p95 > DRAWING_P95_FRAC * big:
            fails.append('%s view: mesh outline matches the drawing %.0f%%, outlines up to %.1f mm apart '
                         '(limits %.0f%%, %.1f mm)' % (view, 100 * iou, p95, 100 * DRAWING_IOU, DRAWING_P95_FRAC * big))
        if out_dir:
            ov = np.zeros(drawn.shape + (3,), np.uint8) + 255
            ov[drawn & ~got] = (220, 60, 60)      # drawn, missing from the mesh
            ov[got & ~drawn] = (60, 110, 220)     # mesh, not in the drawing
            ov[got & drawn] = (200, 200, 200)
            Image.fromarray(ov).save(os.path.join(out_dir, 'drawing-match-%s.png' % view))
    return metrics, fails


def _rotation(az, el):
    a, e = math.radians(az), math.radians(el)
    Rz = np.array([[math.cos(a), -math.sin(a), 0], [math.sin(a), math.cos(a), 0], [0, 0, 1]])
    Rx = np.array([[1, 0, 0], [0, math.cos(e), -math.sin(e)], [0, math.sin(e), math.cos(e)]])
    return Rx @ Rz


def _pose_mask(V, T, az, el, ref_shape):
    """Orthographic outline of the mesh seen from (az, el), fitted to the reference's box."""
    Q = V @ _rotation(az, el).T
    P = Q[:, [0, 2]]                      # screen x = world x after rotation, screen y = z
    lo, hi = P.min(0), P.max(0)
    h, w = ref_shape
    s = min((w - 4) / max(1e-9, hi[0] - lo[0]), (h - 4) / max(1e-9, hi[1] - lo[1]))
    P = (P - (lo + hi) / 2) * s
    P[:, 0] += w / 2
    P[:, 1] = h / 2 - P[:, 1]
    im = Image.new('L', (w, h), 0)
    dr = ImageDraw.Draw(im)
    # far-to-near order is irrelevant for an outline
    for t in T:
        dr.polygon([tuple(P[i]) for i in t], fill=255)
    return np.asarray(im) > 0


def _fit_box(mask, shape):
    ys, xs = np.nonzero(mask)
    m = mask[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    h, w = shape
    s = min((w - 4) / m.shape[1], (h - 4) / m.shape[0])
    im = Image.fromarray(m.astype(np.uint8) * 255).resize(
        (max(1, int(m.shape[1] * s)), max(1, int(m.shape[0] * s))), Image.Resampling.BILINEAR)
    out = Image.new('L', (w, h), 0)
    out.paste(im, ((w - im.width) // 2, (h - im.height) // 2))
    return np.asarray(out) >= 128


def against_pictorial(verts, tris, image_path, out_dir=None, height_px=140):
    """Best outline overlap between the mesh and a pictorial view over camera angles."""
    from .silhouette import silhouette
    ref, painting = silhouette(image_path)
    h = height_px
    w = max(8, int(round(h * ref.shape[1] / ref.shape[0])))
    shape = (h + 4, w + 4)
    R = _fit_box(ref, shape)
    V = np.asarray(verts, float)
    V = V - V.mean(0)
    T = np.asarray(tris, int)
    if len(T) > 6000:                          # the outline needs no more than this
        T = T[np.random.default_rng(0).choice(len(T), 6000, replace=False)]
    best = (-1.0, 0, 0)

    def score(az, el):
        G = _pose_mask(V, T, az, el, shape)
        return float((G & R).sum() / max(1, (G | R).sum()))
    for az in range(0, 360, 15):
        for el in (5, 15, 25, 35, 45, 60):
            best = max(best, (score(az, el), az, el))
    for step in (6, 3):
        _, az0, el0 = best
        for az in (az0 - step, az0, az0 + step):
            for el in (el0 - step, el0, el0 + step):
                best = max(best, (score(az % 360, max(0, min(80, el))), az % 360, max(0, min(80, el))))
    iou, az, el = best
    if out_dir:
        G = _pose_mask(V, T, az, el, shape)
        ov = np.zeros(shape + (3,), np.uint8) + 255
        ov[R & ~G] = (220, 60, 60)
        ov[G & ~R] = (60, 110, 220)
        ov[G & R] = (200, 200, 200)
        big = Image.fromarray(ov).resize((shape[1] * 3, shape[0] * 3), Image.Resampling.NEAREST)
        name = Path(image_path).stem
        big.save(os.path.join(out_dir, 'pictorial-match-%s.png' % name))
    result = {'iou': round(iou, 3), 'azimuth_deg': az, 'elevation_deg': el}
    try:
        result.update(shading_agreement(np.asarray(verts, float), np.asarray(tris, int), painting, ref,
                                        az, el, out_dir, Path(image_path).stem))
    except Exception as exc:
        result['crease_error'] = str(exc)
    return result


CREASE_DEG = 35.0           # a mesh edge this sharp is a visible corner line
CREASE_PRECISION = 0.40     # share of the mesh's visible corner lines the painting must also show


def _zbuffer(P2, depth, T, shape, faces_out=None):
    """Per-pixel nearest depth of the triangles (screen coords P2, depth along the view);
    with faces_out (an int array of shape), also the nearest triangle's index per pixel."""
    h, w = shape
    zb = np.full(shape, np.inf)
    for fi, t in enumerate(T):
        p = P2[t]
        x0, y0 = np.floor(p.min(0)).astype(int)
        x1, y1 = np.ceil(p.max(0)).astype(int)
        x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, w - 1), min(y1, h - 1)
        if x1 < x0 or y1 < y0:
            continue
        xs, ys = np.meshgrid(np.arange(x0, x1 + 1) + .5, np.arange(y0, y1 + 1) + .5)
        a, b, c = p
        den = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(den) < 1e-12:
            continue
        l1 = ((b[1] - c[1]) * (xs - c[0]) + (c[0] - b[0]) * (ys - c[1])) / den
        l2 = ((c[1] - a[1]) * (xs - c[0]) + (a[0] - c[0]) * (ys - c[1])) / den
        l3 = 1 - l1 - l2
        inside = (l1 >= -1e-6) & (l2 >= -1e-6) & (l3 >= -1e-6)
        if not inside.any():
            continue
        z = l1 * depth[t[0]] + l2 * depth[t[1]] + l3 * depth[t[2]]
        sub = zb[y0:y1 + 1, x0:x1 + 1]
        zz = np.where(inside, z, np.inf)
        if faces_out is not None:
            fsub = faces_out[y0:y1 + 1, x0:x1 + 1]
            fsub[zz < sub] = fi
        np.minimum(sub, zz, out=sub)
    return zb


def crease_agreement(V, T, painting, ref_mask, az, el, out_dir=None, name='pictorial'):
    """Inside the outline: the mesh's visible corner lines (edges sharper than CREASE_DEG) seen
    from the solved camera, against the painting's own edges. A corner the painting does not
    show (a boxed handle drawn soft) lowers the precision."""
    from skimage.feature import canny
    h0 = 220
    w0 = max(8, int(round(h0 * ref_mask.shape[1] / ref_mask.shape[0])))
    shape = (h0 + 4, w0 + 4)
    V = V - V.mean(0)
    R = _rotation(az, el)
    Q = V @ R.T
    P = Q[:, [0, 2]]
    lo, hi = P.min(0), P.max(0)
    sc = min((shape[1] - 4) / max(1e-9, hi[0] - lo[0]), (shape[0] - 4) / max(1e-9, hi[1] - lo[1]))
    P2 = (P - (lo + hi) / 2) * sc
    P2[:, 0] += shape[1] / 2
    P2[:, 1] = shape[0] / 2 - P2[:, 1]
    depth = -Q[:, 1]                     # camera looks along +y after rotation: nearer = larger y
    depth = Q[:, 1]
    zb = _zbuffer(P2, depth, T, shape)
    # face normals and sharp edges
    a, b, c = V[T[:, 0]], V[T[:, 1]], V[T[:, 2]]
    n = np.cross(b - a, c - a)
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    edges = {}
    for fi, t in enumerate(T):
        for i, j in ((0, 1), (1, 2), (2, 0)):
            edges.setdefault((min(t[i], t[j]), max(t[i], t[j])), []).append(fi)
    crease = np.zeros(shape, bool)
    span = max(1e-9, float(zb[np.isfinite(zb)].max() - zb[np.isfinite(zb)].min())) if np.isfinite(zb).any() else 1
    for (i, j), fs in edges.items():
        if len(fs) != 2:
            continue
        if np.degrees(np.arccos(np.clip(n[fs[0]] @ n[fs[1]], -1, 1))) < CREASE_DEG:
            continue
        for t in np.linspace(0.1, 0.9, 6):
            p = P2[i] * (1 - t) + P2[j] * t
            d = depth[i] * (1 - t) + depth[j] * t
            x, y = int(p[0]), int(p[1])
            if 0 <= x < shape[1] and 0 <= y < shape[0] and d <= zb[y, x] + 0.01 * span:
                crease[y, x] = True
    # only corner lines inside the outline (the outline itself is checked separately)
    sil = np.isfinite(zb)
    crease &= ndimage.binary_erosion(sil, iterations=3)
    g = np.asarray(painting.convert('L').resize((shape[1] - 4, shape[0] - 4))).astype(float) / 255
    g = np.pad(g, 2, mode='edge')
    painted = canny(g, sigma=1.5)
    near = ndimage.binary_dilation(painted, iterations=3)
    total = int(crease.sum())
    precision = float((crease & near).sum() / total) if total else 1.0
    if out_dir:
        ov = np.zeros(shape + (3,), np.uint8) + 255
        ov[painted] = (170, 170, 170)
        ov[crease & near] = (40, 160, 60)
        ov[crease & ~near] = (220, 50, 50)
        from PIL import Image as _I
        _I.fromarray(ov).resize((shape[1] * 3, shape[0] * 3), _I.Resampling.NEAREST).save(
            os.path.join(out_dir, 'crease-match-%s.png' % name))
    return {'crease_pixels': total, 'crease_precision': round(precision, 3)}


SHADING_R2 = 0.25          # the mesh's geometry must explain at least this much of the painted shading


def shading_agreement(V, T, painting, ref_mask, az, el, out_dir=None, name='pictorial'):
    """Inside the outline, at the solved camera: fit one light to the painting from the mesh's
    own surface normals (brightness = n . l + c, linear least squares in l and c) and report the
    share of the painted brightness variation that this geometry explains (R^2), measured on
    the brightness gradient so flat paint colours count less than shading. A boxed shape where
    the picture shades smoothly (or the reverse) explains less."""
    h0 = 220
    w0 = max(8, int(round(h0 * ref_mask.shape[1] / ref_mask.shape[0])))
    shape = (h0 + 4, w0 + 4)
    V = V - V.mean(0)
    R = _rotation(az, el)
    Q = V @ R.T
    P = Q[:, [0, 2]]
    lo, hi = P.min(0), P.max(0)
    sc = min((shape[1] - 4) / max(1e-9, hi[0] - lo[0]), (shape[0] - 4) / max(1e-9, hi[1] - lo[1]))
    P2 = (P - (lo + hi) / 2) * sc
    P2[:, 0] += shape[1] / 2
    P2[:, 1] = shape[0] / 2 - P2[:, 1]
    faces = np.full(shape, -1, int)
    zb = _zbuffer(P2, Q[:, 1], T, shape, faces)
    a, b, c = Q[T[:, 0]], Q[T[:, 1]], Q[T[:, 2]]
    n = np.cross(b - a, c - a)
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    inside = ndimage.binary_erosion(faces >= 0, iterations=2)
    # the painting fitted into the same box as the projection
    ys, xs = np.nonzero(ref_mask)
    crop = painting.crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1)).convert('L')
    gw = int(round((hi[0] - lo[0]) * sc)) or 1
    gh = int(round((hi[1] - lo[1]) * sc)) or 1
    from PIL import Image as _I
    g = np.zeros(shape)
    im = np.asarray(crop.resize((max(1, gw), max(1, gh)), _I.Resampling.BILINEAR)).astype(float) / 255
    oy, ox = (shape[0] - im.shape[0]) // 2, (shape[1] - im.shape[1]) // 2
    g[oy:oy + im.shape[0], ox:ox + im.shape[1]] = im
    N = n[faces[inside]]
    I = g[inside]
    if len(I) < 50:
        return {'shading_r2': None}
    A = np.c_[N, np.ones(len(N))]
    coef, *_ = np.linalg.lstsq(A, I, rcond=None)
    pred = A @ coef
    r2 = 1 - ((I - pred) ** 2).sum() / max(1e-12, ((I - I.mean()) ** 2).sum())
    if out_dir:
        out = np.zeros(shape)
        out[inside] = pred
        both = np.concatenate([g, out], 1)
        _I.fromarray((np.clip(both, 0, 1) * 255).astype(np.uint8)).resize(
            (both.shape[1] * 2, both.shape[0] * 2)).save(os.path.join(out_dir, 'shading-match-%s.png' % name))
    return {'shading_r2': round(float(r2), 3), 'light_direction_view': [round(float(v), 3) for v in coef[:3]]}


def check(verts, tris, order, out_dir=None):
    """All drawing/pictorial checks for an order that went through the drawing stage."""
    drawing = (order.get('measured') or {}).get('drawing') or {}
    metrics, fails = {}, []
    path = drawing.get('json')
    if not path or not os.path.exists(path):
        return metrics, fails
    record = json.loads(Path(path).read_text())
    out_dir = out_dir or os.path.dirname(path)
    m, f = against_drawing(verts, tris, record, out_dir)
    metrics['drawing'] = m
    fails += f
    pics = {}
    for p in order.get('reference_images', []):
        if os.path.exists(p):
            r = against_pictorial(verts, tris, p, out_dir)
            pics[Path(p).name] = r
            if r['iou'] < PICTORIAL_IOU:
                fails.append('looks unlike the sheet\'s pictorial view %s: best outline match %.0f%% '
                             '(limit %.0f%%)' % (Path(p).stem, 100 * r['iou'], 100 * PICTORIAL_IOU))
            if r.get('shading_r2') is not None and r['shading_r2'] < SHADING_R2:
                fails.append('surface shape unlike the sheet\'s pictorial view %s: the mesh\'s surface '
                             'explains only %.0f%% of the painted shading (limit %.0f%%)' % (
                                 Path(p).stem, 100 * r['shading_r2'], 100 * SHADING_R2))
    if pics:
        metrics['pictorial'] = pics
    return metrics, fails
