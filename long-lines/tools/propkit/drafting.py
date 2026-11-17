"""The drawing stage: the sheet's painted views become one consistent engineering drawing,
and the build is made from that drawing.

It runs right after intake has split the sheet into views, before any geometry:

1. Orientation. Each view is put into the standard frame (third-angle projection: front,
   top above it, right side to its right). A top or bottom view drawn turned or mirrored is
   tried in all eight orientations and the one that agrees with the front and side views is
   used; the decision and its scores are recorded.
2. Size. Width and height come from the front view, depth from the side view, at the scale
   intake fitted. Every other view is measured against them and its disagreement reported.
3. Clean profiles. Each outline is fitted with straight lines and true arcs (one closed
   polyline with bulges, the way CAD stores it) within a stated tolerance; near-axis lines
   are snapped square; a view that is mirror-symmetric is made exactly symmetric.
4. Features. Circles drawn inside a view (openings, dials, bosses) are found and measured.
   An end view whose outline is round marks that axis as round: the build then gives the
   part round cross-sections along it instead of the square ones two outlines produce.
5. Output. An AutoCAD DXF (layers, centre lines, dimensions in mm, title block), a PNG of
   the same sheet, and a JSON record the build and QA read.

Nothing here is a measurement of a real object: sizes are estimates at intake's scale, and
the drawing says so in its title block.
"""
import json
import math
import os
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
from scipy.optimize import minimize_scalar

from .silhouette import observed_silhouettes, silhouette

# how each view's image axes map to the object (hull frame: x left->right, y front->back,
# z up). cols/rows: which object axis runs along image columns/rows, and its direction.
FRAME = {'front': ('x', +1, 'z', -1), 'back': ('x', -1, 'z', -1),
         'right': ('y', +1, 'z', -1), 'left': ('y', -1, 'z', -1),
         'top': ('x', +1, 'y', -1), 'bottom': ('x', +1, 'y', +1)}
FIT_TOL_PX = 1.0          # largest distance from the painted outline to a drawn line or arc
SNAP_DEG = 2.0            # lines this close to horizontal/vertical are drawn square
SYMMETRY_IOU = 0.94       # a view at least this close to its mirror image is drawn symmetric
ROUND_COVERAGE = 0.55     # share of a circle the outline must follow to call the end view round


# ---------------------------------------------------------------- orientation and size

def _orientations(a):
    """The eight ways a view can be drawn: four turns, each optionally mirrored."""
    for flip in (False, True):
        b = a[:, ::-1] if flip else a
        for k in range(4):
            yield k, flip, np.rot90(b, k)


def _profile(mask, axis, n=96):
    """How much object there is at each position along one image axis, resampled to n."""
    p = mask.sum(axis=axis).astype(float)
    return np.interp(np.linspace(0, len(p) - 1, n), np.arange(len(p)), p) / max(1.0, p.max())


def _corr(a, b):
    if a.std() < 1e-6 or b.std() < 1e-6:
        return 0.0
    return float(np.corrcoef(a, b)[0, 1])


def orient_plan_view(name, mask, front, side, W, D):
    """Pick the orientation of a top/bottom view that agrees with the front and side views.

    Its proportion must be width:depth; its columns run along x, so the amount of object in
    each column follows the front view's columns; its rows run along depth, following the
    side view's columns (front at the bottom of a top view, at the top of a bottom view)."""
    fx = _profile(front, 0)
    sy = _profile(side, 0)
    if name == 'top':
        sy = sy[::-1]            # top view: the front is the bottom row
    scores = []
    for k, flip, m in _orientations(mask):
        aspect = abs(math.log((m.shape[1] / m.shape[0]) / (W / D)))
        cx = _corr(_profile(m, 0), fx)
        cy = _corr(_profile(m, 1), sy)
        cxm = _corr(_profile(m, 0)[::-1], fx)
        # mirror in x is invisible for symmetric objects; prefer fewer changes on a tie
        score = cx + cy - 3.0 * aspect - 0.01 * (k != 0) - 0.01 * flip
        scores.append({'turns_ccw': k, 'mirrored': flip, 'aspect_error_pct': round(100 * (math.exp(aspect) - 1), 1),
                       'column_agreement': round(cx, 3), 'row_agreement': round(cy, 3),
                       'mirror_ambiguous': abs(cx - cxm) < 0.02, 'score': round(score, 3)})
    best = max(scores, key=lambda s: s['score'])
    as_drawn = scores[0]
    return best, as_drawn, scores


def apply_orientation(arr, turns, mirrored):
    a = arr[:, ::-1] if mirrored else arr
    return np.rot90(a, turns).copy()


# ---------------------------------------------------------------- symmetry

def symmetrize(mask):
    """Mirror-symmetric views (most product fronts and tops) are made exactly symmetric about
    the best vertical axis: the average of the outline and its mirror image."""
    h, w = mask.shape
    sd = ndimage.distance_transform_edt(mask) - ndimage.distance_transform_edt(~mask)
    best = (0.0, 0)
    for shift in range(-max(2, w // 25), max(2, w // 25) + 1):
        flipped = np.roll(mask[:, ::-1], shift, axis=1)
        iou = (mask & flipped).sum() / max(1, (mask | flipped).sum())
        best = max(best, (float(iou), shift))
    iou, shift = best
    if iou < SYMMETRY_IOU:
        return mask, None
    sdf = np.roll(sd[:, ::-1], shift, axis=1)
    out = (sd + sdf) / 2 > 0
    axis_col = (w - 1 + shift) / 2.0
    return out, {'mirror_iou': round(iou, 3), 'axis_col_px': axis_col}


# ---------------------------------------------------------------- lines and arcs

def _outline(mask):
    import cv2
    m = np.pad(mask.astype(np.uint8), 2)
    cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    c = max(cs, key=cv2.contourArea)[:, 0, :].astype(float) - 2   # (x, y) px
    # light smoothing along the outline removes the pixel staircase, not the shape
    c = np.c_[ndimage.gaussian_filter1d(c[:, 0], 1.2, mode='wrap'),
              ndimage.gaussian_filter1d(c[:, 1], 1.2, mode='wrap')]
    return c


def _cross(a, b):
    a = np.asarray(a); b = np.asarray(b)
    return a[..., 0] * b[..., 1] - a[..., 1] * b[..., 0]


def _circle3(a, b, c):
    ax, ay = a; bx, by = b; cx, cy = c
    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-9:
        return None
    ux = ((ax * ax + ay * ay) * (by - cy) + (bx * bx + by * by) * (cy - ay) + (cx * cx + cy * cy) * (ay - by)) / d
    uy = ((ax * ax + ay * ay) * (cx - bx) + (bx * bx + by * by) * (ax - cx) + (cx * cx + cy * cy) * (bx - ax)) / d
    return np.array([ux, uy]), math.hypot(ax - ux, ay - uy)


def _line_dev(P):
    a, b = P[0], P[-1]
    d = b - a
    L = math.hypot(*d)
    if L < 1e-9:
        return np.inf
    return float(np.abs(_cross(d, P - a)).max() / L)


def _arc_through_ends(P, scale):
    """Best arc through both end points (its centre lies on their perpendicular bisector).
    Returns (centre, radius, max deviation) or None."""
    a, b = P[0], P[-1]
    m = (a + b) / 2
    d = b - a
    L = math.hypot(*d)
    if L < 1e-9:
        return None
    n = np.array([-d[1], d[0]]) / L
    first = _circle3(a, P[len(P) // 2], b)
    if first is None:
        return None
    t0 = float(np.dot(first[0] - m, n))

    def cost(t):
        c = m + t * n
        r = math.hypot(*(a - c))
        return float(((np.hypot(*(P - c).T) - r) ** 2).mean())
    span = max(abs(t0), L) * 2 + 1
    res = minimize_scalar(cost, bounds=(t0 - span, t0 + span), method='bounded', options={'xatol': 1e-3})
    c = m + res.x * n
    r = math.hypot(*(a - c))
    if r > 40 * scale:
        return None
    dev = float(np.abs(np.hypot(*(P - c).T) - r).max())
    return c, r, dev


def _grow(P, i, ok, limit, start=2):
    """Largest j (i+start <= j <= limit) with ok(P[i:j+1]), by doubling then bisection."""
    lo, step = i + start, 2
    if lo > limit or not ok(P[i:lo + 1]):
        return i + 1
    while lo + step <= limit and ok(P[i:lo + step + 1]):
        lo += step
        step *= 2
    hi = min(limit, lo + step)
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if ok(P[i:mid + 1]):
            lo = mid
        else:
            hi = mid
    return lo


def fit_profile(mask, tol=FIT_TOL_PX):
    """The outline as CAD entities: a closed list of vertices (x, y px), each with the bulge of
    the segment that leaves it (0 = straight line, tan(sweep/4) = arc). Also the deviation."""
    C = _outline(mask)
    return _fit_contour(C, mask.shape, tol)


def _fit_contour(C, shape, tol=FIT_TOL_PX):
    """Fit one traced, closed pixel contour with the exterior's line/arc algorithm."""
    scale = float(max(shape))
    # start at the sharpest corner so no entity straddles it
    k = 5
    v1 = np.roll(C, -k, 0) - C
    v0 = C - np.roll(C, k, 0)
    turn = np.abs(np.arctan2(_cross(v0, v1), (v0 * v1).sum(1)))
    C = np.roll(C, -int(np.argmax(turn)), 0)
    P = np.vstack([C, C[:1]])
    N = len(P) - 1
    line_ok = lambda Q: _line_dev(Q) <= tol

    def arc_ok(Q):
        if len(Q) < 7:
            return False
        r = _arc_through_ends(Q, scale)
        return r is not None and r[2] <= tol
    verts = []
    i = 0
    while i < N:
        jl = _grow(P, i, line_ok, N)
        ja = _grow(P, i, arc_ok, N, start=6)
        if ja - i >= 7 and (ja >= jl or (ja - i) >= 0.9 * (jl - i)):
            Q = P[i:ja + 1]
            c, r, _ = _arc_through_ends(Q, scale)
            a0 = math.atan2(*(Q[0] - c)[::-1])
            am = math.atan2(*(Q[len(Q) // 2] - c)[::-1])
            a1 = math.atan2(*(Q[-1] - c)[::-1])
            sweep = (a1 - a0) % (2 * math.pi)
            if not ((am - a0) % (2 * math.pi) < sweep):
                sweep -= 2 * math.pi
            verts.append([P[i][0], P[i][1], math.tan(sweep / 4) if abs(sweep) > math.radians(4) else 0.0])
            i = ja
        else:
            verts.append([P[i][0], P[i][1], 0.0])
            i = max(jl, i + 1)
    return _merge_arcs(np.array(verts), P, tol, scale), C


def _merge_arcs(verts, P, tol, scale):
    """Neighbouring arcs (and short lines between them) that one arc fits within tolerance
    become that one arc: a round end is drawn as one arc, not a fan of pieces."""
    idx = [int(np.argmin(np.hypot(*(P[:-1] - v[:2]).T))) for v in verts]
    changed = True
    while changed and len(verts) > 3:
        changed = False
        for k in range(len(verts) - 1):
            i0, i2 = idx[k], (idx[k + 2] if k + 2 < len(idx) else len(P) - 1)
            if i2 <= i0 or abs(verts[k, 2]) + abs(verts[k + 1, 2]) < 1e-9:
                continue
            Q = P[i0:i2 + 1]
            fit = _arc_through_ends(Q, scale)
            if fit is None or fit[2] > tol:
                continue
            c, r, _ = fit
            a0 = math.atan2(*(Q[0] - c)[::-1]); am = math.atan2(*(Q[len(Q) // 2] - c)[::-1])
            a1 = math.atan2(*(Q[-1] - c)[::-1])
            sweep = (a1 - a0) % (2 * math.pi)
            if not ((am - a0) % (2 * math.pi) < sweep):
                sweep -= 2 * math.pi
            verts[k, 2] = math.tan(sweep / 4)
            verts = np.delete(verts, k + 1, axis=0)
            del idx[k + 1]
            changed = True
            break
    return verts


def snap_square(verts, deg=SNAP_DEG):
    """Straight segments within `deg` of horizontal/vertical are made exactly square (shared
    vertices move; arcs keep their sweep)."""
    v = verts.copy()
    n = len(v)
    for i in range(n):
        if abs(v[i, 2]) > 1e-9:
            continue
        j = (i + 1) % n
        dx, dy = v[j, 0] - v[i, 0], v[j, 1] - v[i, 1]
        ang = math.degrees(math.atan2(dy, dx)) % 180
        if min(ang, 180 - ang) < deg:
            v[i, 1] = v[j, 1] = (v[i, 1] + v[j, 1]) / 2
        elif abs(ang - 90) < deg:
            v[i, 0] = v[j, 0] = (v[i, 0] + v[j, 0]) / 2
    return v


def _bulge_points(p0, p1, bulge, n=None):
    """Points along one polyline segment (straight or arc) from p0 to p1."""
    if abs(bulge) < 1e-9:
        L = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
        k = max(1, int(L))
        return [(p0[0] + (p1[0] - p0[0]) * t / k, p0[1] + (p1[1] - p0[1]) * t / k) for t in range(k)]
    sweep = 4 * math.atan(bulge)
    chord = np.asarray(p1) - np.asarray(p0)
    L = math.hypot(*chord)
    r = L / (2 * math.sin(abs(sweep) / 2))
    mid = (np.asarray(p0) + np.asarray(p1)) / 2
    nrm = np.array([-chord[1], chord[0]]) / max(L, 1e-12)
    h = r * math.cos(abs(sweep) / 2) * (1 if (sweep > 0) else -1)
    c = mid + nrm * h
    a0 = math.atan2(p0[1] - c[1], p0[0] - c[0])
    n = n or max(4, int(abs(sweep) * r))      # about one point per pixel
    return [tuple(c + r * np.array([math.cos(a0 + sweep * t / n), math.sin(a0 + sweep * t / n)])) for t in range(n)]


def polyline_points(verts):
    pts = []
    for i in range(len(verts)):
        j = (i + 1) % len(verts)
        pts += _bulge_points(tuple(verts[i, :2]), tuple(verts[j, :2]), verts[i, 2])
    return np.array(pts)


def rasterize(verts, shape, supersample=4, openings=()):
    """The drawn profile as a mask on the view's pixel grid (what the build carves with)."""
    h, w = shape
    im = Image.new('L', (w * supersample, h * supersample), 0)
    pts = polyline_points(verts) * supersample + (supersample - 1) / 2
    ImageDraw.Draw(im).polygon([tuple(p) for p in pts], fill=255)
    for opening in openings:
        pts = polyline_points(np.asarray(opening)) * supersample + (supersample - 1) / 2
        ImageDraw.Draw(im).polygon([tuple(p) for p in pts], fill=0)
    return np.asarray(im.resize((w, h), Image.Resampling.BOX)) >= 128


def _source_openings(views, raw):
    """Observe opposed-mask openings or enclosed sheet-background regions >=0.5% of a view.

    Background uses the silhouette station's border-median RGB and L1 tolerance (30).
    Reconciliation pockets never enter this evidence: candidates come from original pixels.
    A matching painted mark remains an uncertain opening candidate, not a verified bore.
    """
    observed, _ = observed_silhouettes(views)
    result = {}
    for view, path in views.items():
        outer, painting, _ = raw[view]
        opening = outer & ~observed[view][0]
        methods = ['opposed_hole_mask'] if opening.any() else []
        with Image.open(path) as source:
            full = np.asarray(source.convert('RGB')).astype(np.int32)
        border = np.concatenate([full[0], full[-1], full[:, 0], full[:, -1]])
        bg = np.median(border, axis=0)
        bg_like = np.abs(np.asarray(painting).astype(np.int32) - bg).sum(2) <= 30
        labels, count = ndimage.label(bg_like)
        for index, box in enumerate(ndimage.find_objects(labels), 1):
            if box is None or box[0].start == 0 or box[1].start == 0 or \
                    box[0].stop == outer.shape[0] or box[1].stop == outer.shape[1]:
                continue
            region = labels == index
            if region.sum() < 0.005 * outer.size or not outer[region].all():
                continue
            if not opening[region].all():
                methods.append('enclosed_sheet_background')
            opening |= region
        result[view] = opening, sorted(set(methods))
    return result


def _fit_openings(outer, evidence, view, path, source_box, orientation):
    """Trace only evidenced inner loops (CCOMP); ignore reconciliation-created pockets."""
    import cv2
    topology = ndimage.binary_fill_holes(outer) & ~evidence
    contours, hierarchy = cv2.findContours(np.pad(topology.astype(np.uint8), 2),
                                         cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    openings, traces = [], []
    if hierarchy is None:
        return openings, traces
    for contour, relation in zip(contours, hierarchy[0]):
        if relation[3] < 0:
            continue
        points = contour[:, 0, :].astype(float) - 2
        smooth = np.c_[ndimage.gaussian_filter1d(points[:, 0], 1.2, mode='wrap'),
                       ndimage.gaussian_filter1d(points[:, 1], 1.2, mode='wrap')]
        verts, _ = _fit_contour(smooth, outer.shape)
        verts = snap_square(verts)
        openings.append(verts.round(3).tolist())
        traces.append({'source_view': view, 'source_image': str(path),
                       'source_crop_xyxy': list(map(int, source_box)),
                       'pixel_frame': 'oriented_source_crop', 'orientation': orientation,
                       'traced_pixels_xy': points.tolist(), 'method': 'cv2.RETR_CCOMP',
                       'max_deviation_px': round(_outline_deviation(points, verts), 2),
                       'physical_opening_verified': False})
    return openings, traces


# ---------------------------------------------------------------- circles

def find_circles(painting, mask, max_count=3):
    """Circles drawn inside a view (openings, dials, bosses): Hough on the painting's edges,
    kept only where the edge follows most of the circumference and the circle lies on the
    object. Returns [{'center_px', 'radius_px', 'support'}], largest first."""
    from skimage.feature import canny
    from skimage.transform import hough_circle, hough_circle_peaks
    g = np.asarray(painting.convert('L')).astype(float) / 255
    if g.shape != mask.shape:
        g = np.asarray(Image.fromarray((g * 255).astype(np.uint8)).resize(mask.shape[::-1])) / 255
    e = canny(g, sigma=1.5) & ndimage.binary_erosion(mask, iterations=2)
    s = min(mask.shape)
    radii = np.arange(max(6, int(s * 0.12)), max(9, int(s * 0.5)), 1)
    acc = hough_circle(e, radii)
    _, cx, cy, rr = hough_circle_peaks(acc, radii, total_num_peaks=24, min_xdistance=3, min_ydistance=3)
    near = ndimage.binary_dilation(e, iterations=1)
    out = []
    for x, y, r in zip(cx, cy, rr):
        t = np.linspace(0, 2 * np.pi, 180, endpoint=False)
        px = np.round(x + r * np.cos(t)).astype(int)
        py = np.round(y + r * np.sin(t)).astype(int)
        inside = (px >= 0) & (py >= 0) & (px < mask.shape[1]) & (py < mask.shape[0])
        if inside.mean() < 0.98 or not mask[py[inside], px[inside]].all():
            continue
        support = float(near[py, px].mean())
        if support < 0.8:
            continue
        out.append({'center_px': [float(x), float(y)], 'radius_px': float(r), 'support': round(support, 3)})
    # overlapping candidates are one feature: keep the best-supported
    out.sort(key=lambda c: -c['support'])
    kept = []
    for c in out:
        if any(math.hypot(c['center_px'][0] - k['center_px'][0], c['center_px'][1] - k['center_px'][1])
               < c['radius_px'] + k['radius_px'] and
               not math.hypot(c['center_px'][0] - k['center_px'][0], c['center_px'][1] - k['center_px'][1])
               < 0.1 * max(c['radius_px'], k['radius_px']) for k in kept):
            continue
        if any(math.hypot(c['center_px'][0] - k['center_px'][0], c['center_px'][1] - k['center_px'][1])
               < 0.1 * k['radius_px'] and abs(c['radius_px'] - k['radius_px']) < 0.12 * k['radius_px'] for k in kept):
            continue
        kept.append(c)
    out = kept
    out.sort(key=lambda c: -c['support'] * c['radius_px'])
    return out[:max_count]


def round_outline(outline, mask):
    """Is this view's outline (an end view) round? Fit circles to stretches of the outline and
    keep the one the outline follows around the most of. Returns the circle or None."""
    best = None
    n = len(outline)
    s = float(max(mask.shape))
    for frac in (0.12, 0.2, 0.3):
        span = max(8, int(n * frac))
        for i in range(0, n, max(1, n // 48)):
            Q = np.vstack([outline, outline])[i:i + span]
            c3 = _circle3(Q[0], Q[len(Q) // 2], Q[-1])
            if c3 is None:
                continue
            c, r = c3
            if r < 0.15 * s or r > 0.6 * s:
                continue
            d = np.abs(np.hypot(*(outline - c).T) - r)
            on = d <= max(1.5, 0.02 * r)
            ang = np.arctan2(outline[on, 1] - c[1], outline[on, 0] - c[0])
            cover = len(np.unique(np.floor((ang + np.pi) / (2 * np.pi) * 72))) / 72.0
            if best is None or cover > best['coverage']:
                best = {'center_px': [float(c[0]), float(c[1])], 'radius_px': float(r), 'coverage': round(cover, 3)}
    if best and best['coverage'] >= ROUND_COVERAGE:
        return best
    return None


# ---------------------------------------------------------------- the stage

# each view's image frame in normalised object coordinates: (column axis, flipped?), (row axis, flipped?)
VIEW_UV = {'front': (('x', False), ('z', True)), 'back': (('x', True), ('z', True)),
           'right': (('y', False), ('z', True)), 'left': (('y', True), ('z', True)),
           'top': (('x', False), ('y', True)), 'bottom': (('x', False), ('y', False))}
PAIRS = (('front', 'back', ('x', 'z')), ('right', 'left', ('y', 'z')), ('top', 'bottom', ('x', 'y')))


def _sample_plane(mask, view, a_dim, b_dim, na, nb):
    """A view's mask sampled on a normalised (a, b) grid of the object, [na, nb]."""
    (cu, fu), (cv, fv) = VIEW_UV[view]
    a = (np.arange(na) + .5) / na
    b = (np.arange(nb) + .5) / nb
    A, B = np.meshgrid(a, b, indexing='ij')
    coords = {a_dim: A, b_dim: B}
    u = coords[cu]
    v = coords[cv]
    u = 1 - u if fu else u
    v = 1 - v if fv else v
    h, w = mask.shape
    return mask[np.clip((v * h).astype(int), 0, h - 1), np.clip((u * w).astype(int), 0, w - 1)]


def _to_view(plane, view, a_dim, b_dim, shape):
    """A normalised (a, b) plane resampled back onto a view's own pixel grid."""
    h, w = shape
    (cu, fu), (cv, fv) = VIEW_UV[view]
    u = (np.arange(w) + .5) / w
    v = (np.arange(h) + .5) / h
    V, U = np.meshgrid(v, u, indexing='ij')
    U = 1 - U if fu else U
    V = 1 - V if fv else V
    coords = {cu: U, cv: V}
    na, nb = plane.shape
    return plane[np.clip((coords[a_dim] * na).astype(int), 0, na - 1),
                 np.clip((coords[b_dim] * nb).astype(int), 0, nb - 1)]


def reconcile_opposites(masks, W, D, H, res=320):
    """Opposite orthographic views see the same silhouette, mirrored. Painted sheets often leave
    something out of one of them (a lever drawn only on the front). Where a pair disagrees, a
    pixel seen in only one of the two is kept when the other two directions support it (some
    depth along the view has material in both other directions' outlines) and dropped otherwise.
    Returns (reconciled masks by view, report by pair)."""
    big = max(W, D, H)
    n = {'x': max(16, int(res * W / big)), 'y': max(16, int(res * D / big)), 'z': max(16, int(res * H / big))}
    planes, union = {}, {}
    for v1, v2, (a, b) in PAIRS:
        got = [_sample_plane(masks[v], v, a, b, n[a], n[b]) for v in (v1, v2) if v in masks]
        planes[(v1, v2)] = got
        if got:
            union[(a, b)] = got[0] | got[-1]
    out, report = {}, {}

    def support(a, b):
        # material at (a, b) needs some depth c with (a, c) and (c, b) or (b, c) inside the others
        c = ({'x', 'y', 'z'} - {a, b}).pop()
        P = union.get((a, c)) if (a, c) in union else (union[(c, a)].T if (c, a) in union else None)
        Q = union.get((c, b)) if (c, b) in union else (union[(b, c)].T if (b, c) in union else None)
        if P is None or Q is None:
            return None
        return (P.astype(np.int32) @ Q.astype(np.int32)) > 0
    for v1, v2, (a, b) in PAIRS:
        got = planes[(v1, v2)]
        if len(got) < 2:
            continue
        m1, m2 = got
        both, either = m1 & m2, m1 | m2
        sup = support(a, b)
        if sup is None:
            continue
        only = either & ~both
        keep = both | (only & sup)
        report['%s/%s' % (v1, v2)] = {
            'disagreement_pct': round(100 * only.sum() / max(1, either.sum()), 2),
            'kept_from_one_view_px': int((only & sup).sum()), 'dropped_px': int((only & ~sup).sum())}
        for v in (v1, v2):
            out[v] = _to_view(keep, v, a, b, masks[v].shape)
    return out, report


def draftsman_evidence(paintings, masks, size_m, destination=None):
    """Run the draftsman stage and keep its record; a failure is recorded, never fatal."""
    from . import draftsman
    import os as _os
    try:
        res = draftsman.analyse(paintings, masks, _os.environ.get('HULL_FEATURE_BACKEND', 'auto'))
        rec = draftsman.summary(res)
        if 'error' not in res:
            rec['rows'] = draftsman.validated_rows(res, paintings, masks)
            rec['texture_maps'] = draftsman.texture_maps(res)
        if destination is not None and 'error' not in res:
            rec['feature_images'] = draftsman.feature_images(paintings, res['features'], destination)
            rec['sheet'] = draftsman.sheet(paintings, res, str(Path(destination) / 'draftsman.png'),
                                           (size_m['width'] * 1000, size_m['depth'] * 1000, size_m['height'] * 1000))
        return rec
    except Exception as exc:
        import traceback
        return {'error': '%s: %s' % (type(exc).__name__, exc), 'trace': traceback.format_exc()[-1500:]}


def curve_evidence(paintings, destination=None):
    """Trace every view's curves and match them across views (propkit/curve_views.py).

    Returns a JSON-safe summary: per view, how many curves of each type were traced and how many
    another view confirms; every construction (through, cylinder, plane) with the curves that
    decided it; and the registration tolerances. Overlays are written beside the drawing."""
    from . import curves as _curves, curve_views as _cv
    try:
        images = {k: np.asarray(p.convert('RGB')) for k, p in paintings.items() if k in _cv.VIEWS}
        res = _cv.analyse(images)
    except Exception as exc:                  # evidence only: a failure is recorded, never fatal
        return {'error': '%s: %s' % (type(exc).__name__, exc)}
    views = {}
    for v, tr in res['traces'].items():
        kinds = {}
        for c in tr['curves']:
            kinds[c['type']] = kinds.get(c['type'], 0) + 1
        views[v] = dict(res['counts'][v], types=kinds,
                        closed=sum(bool(c.get('closed')) for c in tr['curves']))
        if destination is not None:
            try:
                _curves.overlay(images[v], tr, Path(destination) / ('curves_%s.png' % v))
            except Exception:
                pass
    return {'views': views, 'constructions': res['constructions'], 'tolerances': res['tolerances']}


def prepare(views, destination, height_m, width_m=None, depth_m=None, name='part', scale_note='',
            pictorials=(), keep_openings=True):
    """Make the drawing from the views. views: {name: image path}. Returns the record, with
    'views' (paths to build and paint from, oriented), 'masks' (the drawn profiles on each
    view's pixel grid), 'size_m', 'round_sections' and the DXF/PNG paths."""
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    raw = {k: silhouette(p, with_box=True) for k, p in views.items()}
    source_openings = _source_openings(views, raw) if keep_openings else {}
    front = raw['front'][0]
    side_key = 'right' if 'right' in raw else 'left'
    side = raw[side_key][0]
    if side_key == 'left':
        side = side[:, ::-1]
    H = float(height_m)
    W = float(width_m or H * front.shape[1] / front.shape[0])
    D = float(depth_m or H * side.shape[1] / side.shape[0])
    record = {'stage': 'drawing_before_geometry', 'units': 'mm', 'projection': 'third_angle',
              'size_m': {'width': W, 'depth': D, 'height': H}, 'scale_note': scale_note,
              'views': {}, 'decisions': [], 'profiles': {}, 'circles': {}, 'symmetry': {},
              'view_agreement': {}, 'round_sections': []}
    masks, paintings, out_paths = {}, {}, {}
    staged = {}
    for k, path in views.items():
        mask, painting, box = raw[k]
        arr = np.asarray(painting)
        if k in ('top', 'bottom'):
            best, drawn, scores = orient_plan_view(k, mask, front, side, W, D)
            record.setdefault('orientation', {})[k] = {'chosen': best, 'as_drawn': drawn}
            if best['turns_ccw'] or best['mirrored']:
                mask = apply_orientation(mask, best['turns_ccw'], best['mirrored'])
                arr = apply_orientation(arr, best['turns_ccw'], best['mirrored'])
                record['decisions'].append(
                    '%s view was drawn %s%s; turned to match the front and side views (agreement %.2f/%.2f, '
                    'proportion off %.0f%% as drawn, %.0f%% after)' % (
                        k, '%d quarter-turn(s)' % best['turns_ccw'] if best['turns_ccw'] else 'unturned',
                        ' and mirrored' if best['mirrored'] else '', best['column_agreement'],
                        best['row_agreement'], drawn['aspect_error_pct'], best['aspect_error_pct']))
            # carry the cut-out hole mask along with the painting
        mask_sym, sym = (symmetrize(mask) if k in ('front', 'back', 'top', 'bottom') else (mask, None))
        if sym:
            record['symmetry'][k] = sym
        staged[k] = (mask_sym, arr, box, path)
    # opposite views must be mirror images; where they disagree, the other directions decide
    recon, rrep = reconcile_opposites({k: v[0] for k, v in staged.items()}, W, D, H)
    record['opposite_views'] = rrep
    for pair, info in rrep.items():
        if info.get('kept_from_one_view_px') or info.get('dropped_px'):
            record['decisions'].append(
                '%s disagree in %.1f%% of their outline area: %d px seen in only one of them kept (supported by '
                'the other two directions), %d px dropped (unsupported)' % (
                    pair, info['disagreement_pct'], info['kept_from_one_view_px'], info['dropped_px']))
    for k, (mask_sym, arr, box, path) in staged.items():
        mask = mask_sym = recon.get(k, mask_sym)
        hole = Path(path).with_name('h_%s.png' % k)
        verts, outline = fit_profile(mask_sym)
        verts = snap_square(verts)
        opening_mask, methods = source_openings.get(k, (np.zeros_like(raw[k][0]), []))
        orientation = record.get('orientation', {}).get(k, {}).get('chosen', {})
        if orientation:
            opening_mask = apply_orientation(opening_mask, orientation['turns_ccw'], orientation['mirrored'])
        openings, traces = _fit_openings(mask_sym, opening_mask, k, path, box, orientation)
        drawn_mask = rasterize(verts, mask.shape, openings=openings)
        dev = _outline_deviation(outline, verts)
        record['profiles'][k] = {'vertices_px': verts.round(3).tolist(), 'image_px': list(mask.shape[::-1]),
                                 'entities': int(len(verts)), 'arcs': int((np.abs(verts[:, 2]) > 1e-9).sum()),
                                 'max_deviation_px': round(dev, 2), 'openings': openings,
                                 'opening_traces': traces, 'opening_evidence': methods}
        img = Image.fromarray(arr)
        record['circles'][k] = find_circles(img, drawn_mask)
        out = destination / ('v_%s.png' % k)
        Image.fromarray(arr).save(out)
        if hole.exists():
            hm = np.asarray(Image.open(hole).convert('L'))
            b = box
            hm = hm[b[1]:b[3], b[0]:b[2]]
            if k in record.get('orientation', {}):
                o = record['orientation'][k]['chosen']
                hm = apply_orientation(hm, o['turns_ccw'], o['mirrored'])
            Image.fromarray(hm).save(destination / ('h_%s.png' % k))
        masks[k], paintings[k], out_paths[k] = drawn_mask, img, str(out)
    # size agreement: each view's own proportion against the decided size
    expect = {'front': W / H, 'back': W / H, 'right': D / H, 'left': D / H, 'top': W / D, 'bottom': W / D}
    for k, m in masks.items():
        own = m.shape[1] / m.shape[0]
        record['view_agreement'][k] = {'proportion': round(own, 3), 'expected': round(expect[k], 3),
                                       'off_pct': round(100 * (own / expect[k] - 1), 1)}
    # round axes: an end view whose outline is round
    for k, axis in (('front', 'y'), ('back', 'y'), ('right', 'x'), ('left', 'x')):
        if k not in masks or any(r['axis'] == axis for r in record['round_sections']):
            continue
        outline = _outline(masks[k])
        circ = round_outline(outline, masks[k])
        if not circ:
            continue
        h, w = masks[k].shape
        su, sv = (W if axis == 'y' else D) / w, H / h
        cu = circ['center_px'][0] * su
        if FRAME[k][1] < 0:
            cu = (W if axis == 'y' else D) - cu
        cz = H - circ['center_px'][1] * sv
        r = circ['radius_px'] * (su + sv) / 2
        record['round_sections'].append({'axis': axis, 'end_view': k, 'center_m': [cu, cz], 'radius_m': r,
                                         'coverage': circ['coverage']})
        record['decisions'].append('%s view outline follows a circle for %.0f%% of its turn (diameter %.1f mm): '
                                   'the part is built with round cross-sections along %s inside that circle' % (
                                       k, 100 * circ['coverage'], 2000 * r, axis))
    record['views'] = out_paths
    # measured roundness of every part's cross-section (propkit/rounding.py): the pictorial view
    # and the painted shading decide how far each rectangle two outlines leave is rounded
    from . import rounding
    pics = [p for p in pictorials if p and Path(p).exists()]
    try:
        rr = rounding.estimate(masks, record['size_m'], pics[0] if pics else None, paintings)
        record['roundness'] = {'exponents': rr['exponents_json'], 'evidence': rr['evidence'],
                               'source': rr.get('source', 'pictorial outline' if pics else 'none')}
        for axis, parts in rr['exponents_json'].items():
            for part in parts or []:
                record['decisions'].append(
                    'parts along %s measured round: superellipse exponent %s (2 = ellipse) over %.0f%%-%.0f%% '
                    'of the %s axis, from the %s' % (axis, part['n'], 100 * part['box'][0], 100 * part['box'][1],
                                                    axis, record['roundness']['source']))
    except Exception as exc:          # no roundness evidence: the plain visual hull stands
        record['roundness'] = {'exponents': {}, 'error': str(exc)}
    # local features (propkit/features.py): bumps an outline shows, built only as wide as the
    # painting shows them
    from . import features as _features
    try:
        record['features'] = _features.find(masks, paintings, record['size_m'])
        for f in record['features']:
            if f.get('kind') == 'end_shape':
                record['decisions'].append(
                    'part painted in the %s view over width %.0f%%-%.0f%%: built to its traced outline '
                    '(fills %.0f%% of its box), not the box the other outlines leave' % (
                        f['shape_view'], 100 * f['along'][0], 100 * f['along'][1], 100 * f['fill']))
            elif f.get('keep'):
                record['decisions'].append(
                    'bump on the %s edge along %s (%.0f%%-%.0f%%) measured %.0f%% of the part wide in the %s '
                    'painting; built that wide, not across the whole part' % (
                        f['edge'], f['axis'], 100 * f['along'][0], 100 * f['along'][1],
                        100 * (f['keep'][1] - f['keep'][0]), f['measured_in']))
    except Exception as exc:
        record['features'] = []
        record['features_error'] = str(exc)
    # curves (propkit/curves.py, propkit/curve_views.py): every view traced as true lines, arcs and
    # ellipses with paint noise rejected by statistics, and the curves matched across views on
    # their shared axes. Recorded as drawing evidence; it does not change the geometry yet.
    record['curves'] = curve_evidence(paintings, destination)
    # the draftsman stage (propkit/draftsman.py, docs/DRAFTSMAN_PIPELINE.md): every feature traced
    # in every view, the views aligned, features matched along projection lines; images beside the
    # drawing (features_<view>.png, draftsman.png). Evidence for the build; the outlines stay the body.
    record['draftsman'] = draftsman_evidence(paintings, masks, record['size_m'], destination)
    # repeated parts confirmed along projection lines become construction: each row's instances are
    # separate parts, so what lies between them in the row's band is not one of them
    try:
        for row in (record['draftsman'].get('rows', []) if os.environ.get('HULL_PART_ROWS', '0') == '1' else []):
            row.update(kind='row', keep=True)
            record['features'].append(row)
            record['decisions'].append('row of %d repeated parts along %s (draftsman): built as separate parts, '
                                       'the gaps between them cut over their band' % (len(row['instances']), row['along']))
    except Exception as exc:
        record['rows_error'] = str(exc)
    from . import drawing_cad
    record['dxf'], record['sheet'] = drawing_cad.write(record, masks, destination, name)
    (destination / 'drawing.json').write_text(json.dumps(record, indent=1))
    record['masks'] = masks
    record['paintings'] = paintings
    return record


def _outline_deviation(outline, verts):
    from scipy.spatial import cKDTree
    pts = polyline_points(verts)
    d, _ = cKDTree(pts).query(outline)
    return float(np.percentile(d, 99))


def view_mask_mm(record, view, mm_per_px=0.5):
    """A drawn view's profile resampled to a metric grid (for QA): mask, mm per pixel."""
    m = record['masks'][view]
    W, D, H = (record['size_m'][k] * 1000 for k in ('width', 'depth', 'height'))
    span = {'front': (W, H), 'back': (W, H), 'right': (D, H), 'left': (D, H), 'top': (W, D), 'bottom': (W, D)}[view]
    size = (max(2, int(round(span[0] / mm_per_px))), max(2, int(round(span[1] / mm_per_px))))
    return np.asarray(Image.fromarray(m.astype(np.uint8) * 255).resize(size, Image.Resampling.BILINEAR)) >= 128
