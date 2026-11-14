"""Measured roundness: the cross-section shape a sheet's views imply, for any object.

Geometry. Two orthographic outlines that share an axis (front and side share height) fix
every slice across that axis only up to a set of rectangles: each rectangle is one span of the
first outline's row times one span of the second's. The real slice is some shape inscribed in
each rectangle. We model it as the superellipse |u/a|^n + |v/b|^n <= 1 that fills the
rectangle: n = 2 is an ellipse, larger n squarer, n -> infinity the rectangle itself (what a
plain visual hull builds). There are three such pairs, one per axis:

    axis z (height):  front x side   -> rounds edges that run vertically   (a handle, a can)
    axis x (width):   front x top    -> rounds edges that run left-right   (a loaf, a bar)
    axis y (depth):   side  x top    -> rounds edges that run front-back   (a barrel, a nozzle)

Rounding never changes any view's outline: a corner a view needs (its column would otherwise
go empty) is put back. So every outline still matches its drawing exactly; only what the
outlines cannot see changes.

Evidence for n, per axis, measured, never by object type:
  * the sheet's pictorial (isometric) view: a square section seen at angle t spans
    w(|cos t| + |sin t|), a round one w. The camera pose is searched, then each axis's n is
    the one whose outline matches the picture best (mean outline distance). Changes smaller
    than the measurement's resolution keep n = infinity (no rounding without evidence).
  * the painted shading across each rectangle in the view that looks along the other axis:
    under light from the viewer, brightness follows the cosine of the surface tilt, so the
    ratio of edge brightness to centre brightness is a known function of n. Reported as a
    second witness, used when there is no pictorial view.
"""
import math

import numpy as np
from scipy import ndimage

EXPONENTS = (2.0, 2.6, 3.5, 5.0, 8.0, math.inf)


def _runs(b):
    """[start, stop) index runs of True in a 1D bool array."""
    d = np.diff(np.r_[0, b.astype(np.int8), 0])
    return list(zip(np.nonzero(d == 1)[0], np.nonzero(d == -1)[0]))


def sample(mask, u, v):
    """mask (rows, cols) sampled at normalised (u right, v down) coordinates."""
    h, w = mask.shape
    return mask[np.clip((v * h).astype(int), 0, h - 1), np.clip((u * w).astype(int), 0, w - 1)]


def view_masks(front, side, top, shape):
    """The three views sampled on the voxel grid's own axes: front [x, z], side [y, z], top [x, y]."""
    nx, ny, nz = shape
    x = (np.arange(nx) + .5) / nx
    y = (np.arange(ny) + .5) / ny
    z = (np.arange(nz) + .5) / nz
    X, Z = np.meshgrid(x, z, indexing='ij')
    Fm = sample(front, X, 1 - Z)
    Y, Z2 = np.meshgrid(y, z, indexing='ij')
    Sm = sample(side, Y, 1 - Z2) if side is not None else np.ones((ny, nz), bool)
    X2, Y2 = np.meshgrid(x, y, indexing='ij')
    Tm = sample(top, X2, 1 - Y2) if top is not None else np.ones((nx, ny), bool)
    return Fm, Sm, Tm


def _cell_n(n, axis, k, a0, a1, b0, b1, dims):
    """Exponent for one cell: n is a number (whole axis) or a list of measured parts, each
    {'n', 'box': [k_lo, k_hi, a_lo, a_hi, b_lo, b_hi]} in normalised grid coordinates."""
    if not isinstance(n, (list, tuple)):
        return n
    nk, na, nb = dims
    ck, ca, cb = (k + .5) / nk, (a0 + a1) / 2 / na, (b0 + b1) / 2 / nb
    for part in n:
        k0, k1, a0_, a1_, b0_, b1_ = part['box']
        if k0 <= ck <= k1 and a0_ <= ca <= a1_ and b0_ <= cb <= b1_:
            return part['n']
    return math.inf


def _cells(A, B, n, axis='', k=0, dims=(1, 1, 1)):
    """Union of superellipses, one per (span of A) x (span of B): A is [i] bool, B is [j] bool."""
    out = np.zeros((len(A), len(B)), bool)
    for a0, a1 in _runs(A):
        for b0, b1 in _runs(B):
            nn = _cell_n(n, axis, k, a0, a1, b0, b1, dims)
            if nn is None or not math.isfinite(nn):
                out[a0:a1, b0:b1] = True
                continue
            ra, rb = (a1 - a0) / 2.0, (b1 - b0) / 2.0
            ca, cb = (a0 + a1 - 1) / 2.0, (b0 + b1 - 1) / 2.0
            # voxel centres inside the superellipse that fills the cell (half a voxel of slack
            # so a one-voxel cell is not erased)
            ia = np.clip(np.abs((np.arange(a0, a1) - ca) / ra) - .5 / ra, 0, None)
            ib = np.clip(np.abs((np.arange(b0, b1) - cb) / rb) - .5 / rb, 0, None)
            out[a0:a1, b0:b1] |= (ia[:, None] ** nn + ib[None, :] ** nn) <= 1.0
    return out


def _axis_slices(axis, Fm, Sm, Tm):
    """For an axis: (number of slices, A(k), B(k)) giving each slice's two span arrays."""
    if axis == 'z':
        return Fm.shape[1], (lambda k: Fm[:, k]), (lambda k: Sm[:, k])
    if axis == 'x':
        return Fm.shape[0], (lambda k: Tm[k, :]), (lambda k: Fm[k, :])
    return Sm.shape[0], (lambda k: Tm[:, k]), (lambda k: Sm[k, :])


def _slice_index(axis, k):
    return {'z': (slice(None), slice(None), k), 'x': (k, slice(None), slice(None)),
            'y': (slice(None), k, slice(None))}[axis]


def _finite(n):
    if isinstance(n, (list, tuple)):
        return any(math.isfinite(p['n']) for p in n)
    return n is not None and math.isfinite(n)


def rounded_hull(keep, Fm, Sm, Tm, exponents, protect=(True, True, True)):
    """keep [x,y,z] with each pair's rectangles rounded by its exponent (a number for the whole
    axis, or measured parts), every view's outline preserved."""
    out = keep.copy()
    for axis in ('z', 'x', 'y'):
        n = exponents.get(axis, math.inf)
        if not _finite(n):
            continue
        nk, A, B = _axis_slices(axis, Fm, Sm, Tm)
        dims = (nk, len(A(0)), len(B(0)))
        for k in range(nk):
            out[_slice_index(axis, k)] &= _cells(A(k), B(k), n, axis, k, dims)
    # outlines are kept: where rounding would empty a column a view sees, its removed voxels return
    removed = keep & ~out
    if removed.any():
        for (ax, want), on in zip(((1, Fm), (0, Sm), (2, Tm)), protect):
            if not on:
                continue          # no such view on the sheet: no outline to keep
            have = out.any(ax)
            lost = want & ~have & keep.any(ax)
            if lost.any():
                out |= removed & np.expand_dims(lost, ax)
    return out


def smooth_max(a, b, k):
    """Polynomial smooth maximum (blend radius k): where two surfaces meet almost tangentially a
    plain maximum leaves a razor crease and hairline slivers, which mesh as folds."""
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0.0, 1.0)
    return a * (1 - h) + b * h + k * h * (1 - h)


def _cell_field(A, B, n, axis, k, dims, shape2):
    """Signed distance-like field of the rounded cells in one slice: inside a rounded cell's box,
    (r - 1) * min(a, b) with r the superellipse radius; elsewhere -inf (no constraint)."""
    G = np.full(shape2, -np.inf)
    nk = dims[0]
    for a0, a1 in _runs(A):
        for b0, b1 in _runs(B):
            nn = _cell_n(n, axis, k, a0, a1, b0, b1, dims)
            if nn is None or not math.isfinite(nn):
                continue
            # a part's rounding fades in and out over its first and last three slices, so a
            # rounded part blends into its square-cornered neighbour instead of stepping
            taper = 1.0
            if isinstance(n, (list, tuple)):
                ck = (k + .5) / nk
                for part in n:
                    k0, k1 = part['box'][0], part['box'][1]
                    if k0 <= ck <= k1 and part['n'] == nn:
                        taper = float(np.clip(min(ck - k0, k1 - ck) / (3.0 / nk), 0.0, 1.0))
                        if k0 <= .5 / nk:
                            taper = float(np.clip((k1 - ck) / (3.0 / nk), 0.0, 1.0))
                        if k1 >= 1 - .5 / nk:
                            taper = min(1.0, float(np.clip((ck - k0) / (3.0 / nk), 0.0, 1.0))) if k0 > .5 / nk else 1.0
                        break
            ra, rb = (a1 - a0) / 2.0, (b1 - b0) / 2.0
            ca, cb = (a0 + a1 - 1) / 2.0, (b0 + b1 - 1) / 2.0
            ua = np.abs((np.arange(a0, a1) - ca) / (ra + .5))
            vb = np.abs((np.arange(b0, b1) - cb) / (rb + .5))
            r = (ua[:, None] ** nn + vb[None, :] ** nn) ** (1.0 / nn)
            g = (r - 1.0) * min(ra + .5, rb + .5)
            G[a0:a1, b0:b1] = np.where(g > 0, g * taper, g)
    return G


def field(F, front, side, top, exponents, vox_m, report=None):
    """Rounding applied to the hull's signed distance field (metres), smooth below the voxel
    size: each rounded cell carves with its superellipse's distance. Where a view needs a
    corner for its outline (the voxel rule in rounded_hull puts it back), the field is left as
    it was."""
    if not exponents or not any(_finite(exponents.get(a, math.inf)) for a in 'xyz'):
        return F
    keep = F < 0
    Fm, Sm, Tm = view_masks(front, side, top, keep.shape)
    protect = (True, side is not None, top is not None)
    from scipy import ndimage as _nd
    floor = -3.0
    G = np.full(F.shape, floor)
    for axis in ('z', 'x', 'y'):
        n = exponents.get(axis, math.inf)
        if not _finite(n):
            continue
        nk, A, B = _axis_slices(axis, Fm, Sm, Tm)
        dims = (nk, len(A(0)), len(B(0)))
        Ga = np.full(F.shape, -np.inf)
        for k in range(nk):
            idx = _slice_index(axis, k)
            Ga[idx] = _cell_field(A(k), B(k), n, axis, k, dims, Ga[idx].shape)
        # each slice's rectangle follows the painted outline's wobble; the rounded surface must
        # vary smoothly along the part, so this axis's field is smoothed along it (and lightly
        # across), as the round end-view sections smooth their extents
        sig = [0.8, 0.8, 0.8]
        sig[{'x': 0, 'y': 1, 'z': 2}[axis]] = 2.5
        Ga = _nd.gaussian_filter(np.maximum(Ga, floor), sig)
        G = np.maximum(G, Ga)
    # corners a view needs: what the voxel rule restores stays unrounded
    raw = keep & ~(G > 0)
    final = rounded_hull(keep, Fm, Sm, Tm, exponents, protect)
    restored = final & ~raw
    # corners kept for an outline blend in over a couple of voxels ('no rounding' is a floor
    # three voxels inside, never minus infinity: the field must stay continuous)
    if restored.any():
        w = np.clip(_nd.gaussian_filter(restored.astype(np.float32), 1.5) * 2.5, 0, 1)
        G = G * (1 - w) + floor * w
    out = smooth_max(F, G * vox_m, 1.5 * vox_m).astype(F.dtype)
    # a field value of exactly zero is neither inside nor outside; later stages compare signs
    out = np.where(np.isfinite(out), out, F)
    out[out == 0] = np.finfo(out.dtype).tiny * 1e6
    if report is not None:
        report.update({'exponents': {a: exponents.get(a) for a in 'xyz'},
                       'voxels_removed': int((keep & ~(out < 0)).sum()),
                       'voxels_kept_for_outlines': int(restored.sum())})
    return out


def tracks(axis, Fm, Sm, Tm, min_cells=3, ratio_limit=0.8):
    """Connected runs of cells along an axis (a handle, a barrel, a leg): cells in neighbouring
    slices that overlap belong to one run. Returns [{'box': normalised [k,a,b] bounds, 'cells'}]."""
    nk, A, B = _axis_slices(axis, Fm, Sm, Tm)
    na, nb = len(A(0)), len(B(0))
    parent = {}

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    cells, prev = [], []
    for k in range(nk):
        cur = []
        for a0, a1 in _runs(A(k)):
            for b0, b1 in _runs(B(k)):
                idx = len(cells)
                cells.append((k, a0, a1, b0, b1))
                parent[idx] = idx
                for j in prev:
                    _, pa0, pa1, pb0, pb1 = cells[j]
                    # one part continues while its section overlaps and changes gradually; an
                    # abrupt change (a handle meeting a barrel) starts another part
                    ratio = ((a1 - a0) * (b1 - b0)) / max(1, (pa1 - pa0) * (pb1 - pb0))
                    if pa0 < a1 and a0 < pa1 and pb0 < b1 and b0 < pb1 and ratio_limit <= ratio <= 1 / ratio_limit:
                        parent[find(idx)] = find(j)
                cur.append(idx)
        prev = cur
    groups = {}
    for i in range(len(cells)):
        groups.setdefault(find(i), []).append(cells[i])
    out = []
    for g in groups.values():
        if len(g) < min_cells:
            continue
        ks = [c[0] for c in g]
        out.append({'axis': axis, 'cells': len(g),
                    'box': [float(v) for v in (min(ks) / nk, (max(ks) + 1) / nk,
                                               min(c[1] for c in g) / na, max(c[2] for c in g) / na,
                                               min(c[3] for c in g) / nb, max(c[4] for c in g) / nb)],
                    # each station's section rectangle, normalised: (along, a0, a1, b0, b1)
                    'stations': [[float((c[0] + .5) / nk), float(c[1] / na), float(c[2] / na),
                                  float(c[3] / nb), float(c[4] / nb)] for c in sorted(g)]})
    return out


def apply(keep, front, side, top, exponents, report=None):
    """Rounding as a hull step (propkit/hull.py): keep is the visual hull's voxels."""
    if not exponents or not any(_finite(exponents.get(a, math.inf)) for a in 'xyz'):
        return keep
    Fm, Sm, Tm = view_masks(front, side, top, keep.shape)
    out = rounded_hull(keep, Fm, Sm, Tm, exponents, (True, side is not None, top is not None))
    if report is not None:
        report.update({'exponents': {a: exponents.get(a) for a in 'xyz'},
                       'voxels_removed': int((keep & ~out).sum())})
    return out


# ------------------------------------------------------------------ evidence

def _rotation(az, el):
    a, e = math.radians(az), math.radians(el)
    Rz = np.array([[math.cos(a), -math.sin(a), 0], [math.sin(a), math.cos(a), 0], [0, 0, 1]])
    Rx = np.array([[1, 0, 0], [0, math.cos(e), -math.sin(e)], [0, math.sin(e), math.cos(e)]])
    return Rx @ Rz


def _fit_box(mask, shape):
    from PIL import Image
    ys, xs = np.nonzero(mask)
    m = mask[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    h, w = shape
    s = min((w - 4) / m.shape[1], (h - 4) / m.shape[0])
    im = Image.fromarray(m.astype(np.uint8) * 255).resize(
        (max(1, int(m.shape[1] * s)), max(1, int(m.shape[0] * s))), Image.Resampling.BILINEAR)
    out = Image.new('L', (w, h), 0)
    out.paste(im, ((w - im.width) // 2, (h - im.height) // 2))
    return np.asarray(out) >= 128


def splat(points, az, el, shape, fit=None):
    """Orthographic outline of a point cloud (voxel centres) from (az, el). The scale and centre
    fit the cloud's box to shape unless `fit` (from an earlier call) is given, so that candidates
    are compared in one fixed camera. Returns (mask, fit)."""
    Q = points @ _rotation(az, el).T
    P = Q[:, [0, 2]]
    h, w = shape
    if fit is None:
        lo, hi = P.min(0), P.max(0)
        fit = (min((w - 4) / max(1e-9, hi[0] - lo[0]), (h - 4) / max(1e-9, hi[1] - lo[1])), (lo + hi) / 2)
    s, c = fit
    u = np.clip(((P[:, 0] - c[0]) * s + w / 2).astype(int), 0, w - 1)
    v = np.clip((h / 2 - (P[:, 1] - c[1]) * s).astype(int), 0, h - 1)
    g = np.zeros(shape, bool)
    g[v, u] = True
    g = ndimage.binary_closing(g, iterations=2)
    return ndimage.binary_fill_holes(g), fit


def outline_distance(a, b):
    """Mean symmetric distance (px) between two masks' outlines."""
    ea = a & ~ndimage.binary_erosion(a)
    eb = b & ~ndimage.binary_erosion(b)
    if not ea.any() or not eb.any():
        return float('inf')
    return float((ndimage.distance_transform_edt(~eb)[ea].mean() + ndimage.distance_transform_edt(~ea)[eb].mean()) / 2)


def local_outline_distance(a, b, region):
    """Mean symmetric outline distance (px), counting only outline pixels inside `region`."""
    oa = a & ~ndimage.binary_erosion(a)
    ob = b & ~ndimage.binary_erosion(b)
    ea, eb = oa & region, ob & region
    if not ea.any() or not eb.any():
        return float('inf')
    return float((ndimage.distance_transform_edt(~ob)[ea].mean() + ndimage.distance_transform_edt(~oa)[eb].mean()) / 2)


def _points(keep, W, D, H):
    nx, ny, nz = keep.shape
    i, j, k = np.nonzero(keep)
    return np.c_[(i + .5) / nx * W - W / 2, (j + .5) / ny * D - D / 2, (k + .5) / nz * H - H / 2]


def solve_pose(points, ref, shape):
    best = (math.inf, 0, 0)
    for az in range(0, 360, 10):
        for el in (5, 15, 25, 35, 45, 60):
            best = min(best, (outline_distance(splat(points, az, el, shape)[0], ref), az, el))
    for step in (5, 2, 1):
        _, az0, el0 = best
        for az in (az0 - step, az0, az0 + step):
            for el in (el0 - step, el0, el0 + step):
                e = max(0, min(80, el))
                best = min(best, (outline_distance(splat(points, az % 360, e, shape)[0], ref), az % 360, e))
    return best


def shading_exponent(painting, mask_cols_rows, cells):
    """Second witness from painted shading: for each rectangle (cols c0:c1 over rows r0:r1 of a
    view), brightness at its outer quarters relative to its middle half. Under light from the
    viewer, brightness ~ cos(tilt); for a superellipse of exponent n the expected ratio is
    computed numerically and the measured median ratio inverted. Returns (n, ratio) or None."""
    g = np.asarray(painting.convert('L')).astype(float)
    ratios = []
    for (c0, c1, r0, r1) in cells:
        if c1 - c0 < 8 or r1 - r0 < 4:
            continue
        band = g[r0:r1, c0:c1]
        prof = np.median(band, axis=0)
        n = len(prof)
        mid = prof[n // 4: 3 * n // 4].mean()
        edge = np.r_[prof[:max(1, n // 8)], prof[-max(1, n // 8):]].mean()
        if mid > 10:
            ratios.append(edge / mid)
    if not ratios:
        return None
    r = float(np.median(ratios))

    def expected(nn):
        u = np.linspace(-1, 1, 801)[1:-1]
        if not math.isfinite(nn):
            return 1.0
        y = (1 - np.abs(u) ** nn) ** (1 / nn)
        dy = np.gradient(y, u)
        cos_t = 1 / np.sqrt(1 + dy ** 2)
        m = len(u)
        return float(np.r_[cos_t[:m // 8], cos_t[-m // 8:]].mean() / cos_t[m // 4: 3 * m // 4].mean())
    table = [(abs(expected(nn) - r), nn) for nn in EXPONENTS]
    return min(table)[1], round(r, 3)


def estimate(masks, size_m, pictorial=None, paintings=None, res=110):
    """Per-axis exponents from the pictorial view (and shading as a second witness).
    masks: drawing masks by view; size_m: {'width','depth','height'}. Returns a report."""
    W, D, H = size_m['width'], size_m['depth'], size_m['height']
    big = max(W, D, H)
    shape = tuple(max(8, int(round(res * s / big))) for s in (W, D, H))
    front = masks['front']
    side = masks.get('right') if 'right' in masks else (masks['left'][:, ::-1] if 'left' in masks else None)
    top = masks.get('top')
    Fm, Sm, Tm = view_masks(front, side, top, shape)
    keep = Fm[:, None, :] & Sm[None, :, :] & Tm[:, :, None]
    report = {'grid': list(shape), 'evidence': {}, 'exponents': {'x': math.inf, 'y': math.inf, 'z': math.inf}}
    if not keep.any():
        return report
    # shading witness: front view rectangles for axis z (front x side), side view for axis y...
    if paintings:
        wit = {}
        # axis z: the front painting, rows run up the height, spans across them run in x.
        # axis y: the top painting, rows run along depth, spans in x. axis x: the top painting
        # transposed, columns run along width, spans in depth.
        for axis, view, transpose in (('z', 'front', False), ('y', 'top', False), ('x', 'top', True)):
            if view not in paintings or view not in masks:
                continue
            p = paintings[view]
            m = masks[view]
            if p.size != (m.shape[1], m.shape[0]):
                continue
            if transpose:
                from PIL import Image
                p = Image.fromarray(np.asarray(p).transpose(1, 0, 2))
                m = m.T
            cells = []
            for r in range(0, m.shape[0], max(1, m.shape[0] // 32)):
                for c0, c1 in _runs(m[r]):
                    cells.append((int(c0), int(c1), max(0, r - 2), min(m.shape[0], r + 3)))
            res_ = shading_exponent(p, None, cells)
            if res_:
                wit[axis] = {'exponent': res_[0] if math.isfinite(res_[0]) else None,
                             'edge_to_middle_brightness': res_[1], 'view': view}
        report['evidence']['shading'] = wit
    if pictorial is not None:
        from .silhouette import silhouette
        ref, _ = silhouette(pictorial)
        h = 220
        w = max(8, int(round(h * ref.shape[1] / ref.shape[0])))
        sh = (h + 4, w + 4)
        R = _fit_box(ref, sh)
        P0 = _points(keep, W, D, H)
        d0, az, el = solve_pose(P0, R, sh)
        _, fit = splat(P0, az, el, sh)          # one camera for every candidate
        ex = {'x': [], 'y': [], 'z': []}
        trials = []
        square_mask = splat(P0, az, el, sh, fit)[0]
        for axis in ('z', 'y', 'x'):
            for tr in tracks(axis, Fm, Sm, Tm):
                # where this part forms the outline: what rounding it fully would remove, seen
                # from the solved camera, widened a little
                only = keep & ~rounded_hull(keep, Fm, Sm, Tm, {axis: [dict(tr, n=2.0)]})
                if only.sum() < 4:
                    continue          # rounding this part would not move anything visible
                region = ndimage.binary_dilation(splat(_points(only, W, D, H), az, el, sh, fit)[0], iterations=4)
                scores = []
                for nn in EXPONENTS:
                    if math.isfinite(nn):
                        m = splat(_points(rounded_hull(keep, Fm, Sm, Tm, {axis: [dict(tr, n=nn)]}), W, D, H),
                                  az, el, sh, fit)[0]
                    else:
                        m = square_mask
                    scores.append((local_outline_distance(m, R, region), nn))
                best_d, best_n = min(scores)
                square_d = scores[-1][0]
                ok = math.isfinite(best_n) and square_d - best_d > max(0.15, 0.05 * square_d)
                trials.append({'axis': axis, 'box': [round(v, 3) for v in tr['box']], 'cells': tr['cells'],
                               'scores': [(round(d, 3), nn if math.isfinite(nn) else 'inf') for d, nn in scores],
                               'chosen': best_n if ok else 'inf'})
                if ok:
                    ex[axis].append({'n': best_n, 'box': tr['box'], 'stations': tr['stations']})
        report['evidence']['pictorial'] = {'pose_azimuth_deg': az, 'pose_elevation_deg': el,
                                           'square_outline_distance_px': round(d0, 3), 'trials': trials}
        report['exponents'] = {a: (v if v else math.inf) for a, v in ex.items()}
    elif report['evidence'].get('shading'):
        for axis, w_ in report['evidence']['shading'].items():
            report['exponents'][axis] = w_['exponent'] or math.inf
        report['source'] = 'shading only (no pictorial view)'
    report['exponents_json'] = {a: (v if isinstance(v, list) else (v if math.isfinite(v) else None))
                                for a, v in report['exponents'].items()}
    return report
