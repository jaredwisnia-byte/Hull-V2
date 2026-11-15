"""Mathematical curves traced in one painted view, with paint noise rejected by statistics.

Design: docs/CURVE_RECONSTRUCTION.md, steps 1-2. Pixels are read once, here. Every
later stage works on the fitted curves (lines, circular arcs, ellipses, B-splines), never on
brightness. Nothing in this module guesses depth.

Candidates. Line segments come from LSD (Grompone von Gioi et al.), which keeps a segment only
when its a-contrario number of false alarms (NFA) is below 1: fewer than one segment that well
aligned is expected by chance in this image's gradient noise. LSD reports -log10(NFA).

Statistics (each a measured property of the curve, never an object-specific exception):
  1. not an accident: -log10(NFA) > 0 (LSD's own test) and length >= MIN_LENGTH_PX;
  2. scale persistence: a real edge is found again in the view reduced 2x and 4x; wear, fabric
     and brush texture are not. Measured on the linked chain (an arc is many short LSD pieces
     but one curve): found again at half or more of the coarser scales the chain is long enough
     for (with full resolution, two of three scales), so a thin painted line that fades at 4x
     but survives 2x is kept;
  3. contrast coherence: across a real edge the brightness step keeps one sign along its length
     and varies little (coefficient of variation <= MAX_CONTRAST_CV); a highlight fades in and out;
  4. symmetry vote: on a view whose outline is mirror-symmetric, a curve whose mirror image is
     also traced gains confidence. It never rejects a curve on its own.

Cross-view consensus and RANSAC lifting into 3D need several views and live in the next stage.

Curve type. Accepted segments are chained end to end and each chain is fitted as a line, a
circle, an ellipse and a smoothing B-spline. The type with the lowest Bayesian information
criterion wins (error plus log(n) per parameter), so pixel noise cannot buy a more complex curve.
"""

import numpy as np
from scipy import ndimage

MIN_LENGTH_PX = 8.0
SCALES = (2, 4)
MAX_CONTRAST_CV = 0.6
MIN_SIGN_AGREEMENT = 0.9
NOISE_FLOOR_PX = 0.5          # positional noise of a traced pixel edge
LINK_ANGLE_DEG = 35.0
SYMMETRIC_VIEW_IOU = 0.9


def _gray(image):
    a = np.asarray(image)
    if a.ndim == 3:
        a = a[..., :3].astype(np.float64) @ np.array([0.299, 0.587, 0.114])
    return a.astype(np.float64)


def object_mask(image, thresh=30):
    """The object against the sheet background, estimated from the border (as silhouette.py)."""
    a = np.asarray(image)[..., :3].astype(np.int32)
    border = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])
    m = np.abs(a - np.median(border, axis=0)).sum(2) > thresh
    m = ndimage.binary_closing(m, iterations=2)
    return ndimage.binary_fill_holes(m)


def _lsd(gray):
    import cv2
    detector = cv2.createLineSegmentDetector(cv2.LSD_REFINE_ADV)
    lines, width, precision, nfa = detector.detect(np.clip(gray, 0, 255).astype(np.uint8))
    if lines is None:
        return np.zeros((0, 4)), np.zeros(0)
    return lines.reshape(-1, 4).astype(np.float64), np.asarray(nfa, np.float64).reshape(-1)


def _segment_geometry(s):
    p0, p1 = np.array(s[:2]), np.array(s[2:])
    d = p1 - p0
    length = float(np.hypot(*d))
    return p0, p1, d / max(length, 1e-9), length


def _matches(seg, others, scale):
    """True if a segment found at a coarser scale lies on `seg` (angle, offset, overlap)."""
    p0, p1, u, length = _segment_geometry(seg)
    n = np.array([-u[1], u[0]])
    for o in others:
        q0, q1, v, olen = _segment_geometry(o)
        if abs(float(u @ v)) < np.cos(np.radians(6.0)):
            continue
        mid = (q0 + q1) / 2
        if abs(float((mid - p0) @ n)) > 1.5 * scale:
            continue
        t = sorted([float((q0 - p0) @ u), float((q1 - p0) @ u)])
        overlap = min(t[1], length) - max(t[0], 0.0)
        if overlap >= 0.5 * min(length, olen):
            return True
    return False


def persistence(seg, coarse):
    """Fraction of coarser scales at which the segment is found again; None if too short."""
    length = _segment_geometry(seg)[3]
    eligible = [(s, lines) for s, lines in coarse if length >= MIN_LENGTH_PX * s / 2]
    if not eligible:
        return None
    return sum(_matches(seg, lines, s) for s, lines in eligible) / len(eligible)


def _point_segment_distance(pts, lines):
    if len(lines) == 0:
        return np.full(len(pts), np.inf)
    a, b = lines[:, None, :2], lines[:, None, 2:]
    ab = b - a
    t = np.clip(np.sum((pts[None] - a) * ab, -1) / np.maximum(np.sum(ab * ab, -1), 1e-12), 0, 1)
    d = np.hypot(*np.moveaxis(pts[None] - (a + t[..., None] * ab), -1, 0))
    return d.min(0)


def _step(gray, pts, normals, scale=1.0, offset=(1.5, 3.0)):
    """Median brightness step across a curve, sampled at `offset` pixels of the given scale."""
    q = pts / scale
    sides = []
    for sign in (1, -1):
        vals = [ndimage.map_coordinates(gray, [(q + sign * o * normals)[:, 1], (q + sign * o * normals)[:, 0]],
                                        order=1, mode='nearest') for o in offset]
        sides.append(np.mean(vals, axis=0))
    return float(np.median(np.abs(sides[0] - sides[1])))


def _normals(pts):
    d = np.gradient(pts, axis=0)
    n = np.column_stack([-d[:, 1], d[:, 0]])
    return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-9)


def chain_persistence(pts, length, coarse, cover=0.6, gray=None, retention=0.5):
    """Persistence of a whole chain (an arc is many short LSD pieces but one curve).

    At every coarser scale the chain is long enough for, the chain persists if either
      - at least `cover` of its points lie within 1.5 coarse pixels of a segment LSD finds at that
        scale (long lines, including thin painted ones), or
      - its brightness step survives the reduction: the step across the chain in the reduced view
        is at least `retention` of the full-resolution step. A real edge keeps its step; a brush
        stroke a pixel or two wide is averaged away. This catches small round features, whose
        pieces are too short for LSD to find again.
    Returns (fraction of eligible scales at which it persists, number eligible)."""
    eligible = [c for c in coarse if length >= MIN_LENGTH_PX * c[0]]
    if not eligible:
        return None, 0
    normals = _normals(pts)
    fine = _step(gray, pts, normals) if gray is not None else 0.0
    found = 0
    for entry in eligible:
        s, lines = entry[0], entry[1]
        if float(np.mean(_point_segment_distance(pts, lines) <= 1.5 * s)) >= cover:
            found += 1
        elif gray is not None and len(entry) > 2 and fine > 1e-6 and \
                _step(entry[2], pts, normals, scale=s) >= retention * fine:
            found += 1
    return found / len(eligible), len(eligible)


def contrast(seg, gray, offset=(1.5, 3.0)):
    """Brightness step across the segment along its length: (sign agreement, CV of magnitude)."""
    p0, p1, u, length = _segment_geometry(seg)
    n = np.array([-u[1], u[0]])
    k = max(8, int(length / 2))
    t = np.linspace(0.1, 0.9, k)
    pts = p0[None] + t[:, None] * (p1 - p0)[None]

    def side(sign):
        vals = []
        for o in offset:
            q = pts + sign * o * n[None]
            vals.append(ndimage.map_coordinates(gray, [q[:, 1], q[:, 0]], order=1, mode='nearest'))
        return np.mean(vals, axis=0)
    step = side(1) - side(-1)
    signs = np.sign(step)
    major = 1.0 if signs.sum() >= 0 else -1.0
    agreement = float(np.mean(signs == major))
    mag = np.abs(step)
    cv = float(mag.std() / max(mag.mean(), 1e-9))
    return agreement, cv


def symmetry_axis(mask):
    """Column about which the outline is most nearly mirror-symmetric, and that IoU."""
    cols = np.nonzero(mask.any(0))[0]
    if len(cols) == 0:
        return None, 0.0
    best = (None, 0.0)
    for x2 in range(2 * cols[0], 2 * cols[-1] + 1):      # axis at x2 / 2, half-pixel steps
        xs = np.arange(mask.shape[1])
        mx = x2 - xs
        ok = (mx >= 0) & (mx < mask.shape[1])
        mirrored = np.zeros_like(mask)
        mirrored[:, xs[ok]] = mask[:, mx[ok]]
        inter = np.logical_and(mask, mirrored).sum()
        union = np.logical_or(mask, mirrored).sum()
        iou = inter / max(union, 1)
        if iou > best[1]:
            best = (x2 / 2.0, float(iou))
    return best


# ---------------------------------------------------------------- curve fitting and selection

def _bic(residuals, params):
    n = len(residuals)
    rss = float(np.sum(np.square(residuals)))
    return n * np.log(max(rss / n, NOISE_FLOOR_PX ** 2)) + params * np.log(n)


def fit_line(pts):
    c = pts.mean(0)
    _, _, vt = np.linalg.svd(pts - c)
    u = vt[0]
    n = np.array([-u[1], u[0]])
    return {'type': 'line', 'point': c.tolist(), 'direction': u.tolist()}, (pts - c) @ n, 2


def fit_circle(pts):
    x, y = pts[:, 0], pts[:, 1]
    A = np.column_stack([x, y, np.ones_like(x)])
    b = x ** 2 + y ** 2
    sol, *_ = np.linalg.lstsq(A, b, rcond=None)
    cx, cy = sol[0] / 2, sol[1] / 2
    r = float(np.sqrt(max(sol[2] + cx ** 2 + cy ** 2, 0.0)))
    res = np.hypot(x - cx, y - cy) - r
    return {'type': 'circle', 'center': [float(cx), float(cy)], 'radius': r}, res, 3


def fit_ellipse(pts):
    """Direct least-squares ellipse (Fitzgibbon, in Halir and Flusser's stable form).

    Deterministic numpy; returns None for points that do not determine an ellipse (a line).
    """
    if len(pts) < 6:
        return None
    c = pts.mean(0)
    scale = float(np.abs(pts - c).max()) or 1.0
    x, y = ((pts - c) / scale).T
    D1 = np.column_stack([x * x, x * y, y * y])
    D2 = np.column_stack([x, y, np.ones_like(x)])
    S1, S2, S3 = D1.T @ D1, D1.T @ D2, D2.T @ D2
    try:
        T = -np.linalg.solve(S3, S2.T)
    except np.linalg.LinAlgError:
        return None
    M = S1 + S2 @ T
    M = np.array([M[2] / 2, -M[1], M[0] / 2])
    w, v = np.linalg.eig(M)
    v = np.real(v)
    cond = 4 * v[0] * v[2] - v[1] ** 2
    good = np.nonzero(cond > 0)[0]
    if len(good) != 1:
        return None
    a1 = v[:, good[0]]
    A, B, C, Dl, El, F = np.concatenate([a1, T @ a1])
    den = 4 * A * C - B * B
    if den <= 0:
        return None
    x0 = (B * El - 2 * C * Dl) / den
    y0 = (B * Dl - 2 * A * El) / den
    Fc = A * x0 * x0 + B * x0 * y0 + C * y0 * y0 + Dl * x0 + El * y0 + F
    lam, vec = np.linalg.eigh(np.array([[A, B / 2], [B / 2, C]]))
    if Fc == 0 or np.any(-Fc / lam <= 0):
        return None
    axes = np.sqrt(-Fc / lam) * scale
    th = float(np.arctan2(vec[1, 0], vec[0, 0]))
    cx, cy = x0 * scale + c[0], y0 * scale + c[1]
    s = np.linspace(0, 2 * np.pi, 720, endpoint=False)
    ex = cx + axes[0] * np.cos(s) * np.cos(th) - axes[1] * np.sin(s) * np.sin(th)
    ey = cy + axes[0] * np.cos(s) * np.sin(th) + axes[1] * np.sin(s) * np.cos(th)
    from scipy.spatial import cKDTree
    res, _ = cKDTree(np.column_stack([ex, ey])).query(pts)
    return ({'type': 'ellipse', 'center': [float(cx), float(cy)],
             'axes': [float(axes[0]), float(axes[1])], 'angle_deg': float(np.degrees(th))}, res, 5)


def fit_spline(pts):
    from scipy.interpolate import splprep, splev
    if len(pts) < 8:
        return None
    try:
        tck, u = splprep([pts[:, 0], pts[:, 1]], s=len(pts) * NOISE_FLOOR_PX ** 2, k=3)
    except Exception:
        return None
    x, y = splev(u, tck)
    res = np.hypot(pts[:, 0] - x, pts[:, 1] - y)
    coefficients = len(tck[1][0])
    return ({'type': 'spline', 'knots': np.asarray(tck[0]).tolist(),
             'control': np.column_stack(tck[1]).tolist(), 'degree': int(tck[2])}, res, 2 * coefficients)


def classify(pts):
    """Fit every curve type; keep the one with the lowest BIC. Returns (curve, scores)."""
    pts = np.asarray(pts, np.float64)
    scores, best = {}, None
    for fitter in (fit_line, fit_circle, fit_ellipse, fit_spline):
        out = fitter(pts)
        if out is None:
            continue
        curve, res, k = out
        bic = _bic(res, k)
        scores[curve['type']] = round(float(bic), 3)
        curve['rms_px'] = round(float(np.sqrt(np.mean(np.square(res)))), 4)
        if best is None or bic < best[0]:
            best = (bic, curve)
    return best[1], scores


def _sample(seg, step=1.0):
    p0, p1, u, length = _segment_geometry(seg)
    t = np.linspace(0.0, 1.0, max(2, int(length / step) + 1))
    return p0[None] + t[:, None] * (p1 - p0)[None]


def chains(segs):
    """Link accepted segments end to end into ordered chains (indices into segs)."""
    n = len(segs)
    geo = [_segment_geometry(s) for s in segs]
    used = [False] * n

    def neighbour(end, direction, exclude):
        best, best_d = None, None
        for j in range(n):
            if used[j] or j in exclude:
                continue
            q0, q1, v, ln = geo[j]
            for flip, q in ((False, q0), (True, q1)):
                d = float(np.hypot(*(q - end)))
                gap = max(3.0, 0.15 * min(ln, geo[exclude[-1]][3]))
                vv = -v if flip else v
                if d <= gap and float(direction @ vv) >= np.cos(np.radians(LINK_ANGLE_DEG)):
                    if best_d is None or d < best_d:
                        best, best_d = (j, flip), d
        return best

    out = []
    for i in sorted(range(n), key=lambda k: -geo[k][3]):
        if used[i]:
            continue
        used[i] = True
        chain = [(i, False)]
        for forward in (True, False):
            while True:
                j, flip = chain[-1] if forward else chain[0]
                p0, p1, u, _ = geo[j]
                if forward:
                    end, direction = (p0, -u) if flip else (p1, u)
                else:
                    end, direction = (p1, u) if flip else (p0, -u)
                nxt = neighbour(end, direction, [c for c, _ in chain])
                if nxt is None:
                    break
                k, kflip = nxt
                used[k] = True
                if forward:
                    chain.append((k, kflip))
                else:
                    chain.insert(0, (k, not kflip))
        out.append(chain)
    return out


def trace(image):
    """Trace one view. Returns segments (with their tests), fitted curves, symmetry and counts."""
    import cv2
    gray = _gray(image)
    mask = object_mask(image)
    lines, lognfa = _lsd(gray)
    coarse = []
    for s in SCALES:
        small = cv2.resize(gray, (max(1, gray.shape[1] // s), max(1, gray.shape[0] // s)),
                           interpolation=cv2.INTER_AREA)
        cl, _ = _lsd(small)
        coarse.append((s, cl * s, small))
    near = ndimage.binary_dilation(mask, iterations=2)
    axis, sym_iou = symmetry_axis(mask)
    segments = []
    for i, (seg, nfa) in enumerate(zip(lines, lognfa)):
        p0, p1, u, length = _segment_geometry(seg)
        mid = (p0 + p1) / 2
        rec = {'id': i, 'p0': p0.round(3).tolist(), 'p1': p1.round(3).tolist(),
               'length_px': round(length, 3), 'log10_nfa_inv': round(float(nfa), 3), 'reasons': []}
        if not near[int(np.clip(round(mid[1]), 0, mask.shape[0] - 1)),
                    int(np.clip(round(mid[0]), 0, mask.shape[1] - 1))]:
            rec['reasons'].append('outside the object')
        if nfa <= 0:
            rec['reasons'].append('chance alignment (NFA >= 1)')
        agreement, cv = contrast(seg, gray)
        rec['contrast_sign_agreement'] = round(agreement, 3)
        rec['contrast_cv'] = round(cv, 3)
        if agreement < MIN_SIGN_AGREEMENT or cv > MAX_CONTRAST_CV:
            rec['reasons'].append('incoherent contrast along its length')
        rec['accepted'] = not rec['reasons']
        segments.append(rec)
    accepted = [s for s in segments if s['accepted']]
    seg_arrays = [np.array(s['p0'] + s['p1']) for s in accepted]
    curves = []
    for chain in chains(seg_arrays):
        pts = []
        for j, flip in chain:
            p = _sample(seg_arrays[j])
            pts.append(p[::-1] if flip else p)
        pts = np.vstack(pts)
        length = float(sum(np.hypot(*np.diff(pts, axis=0).T)))
        ids = [accepted[j]['id'] for j, _ in chain]
        reasons = []
        if length < MIN_LENGTH_PX:
            reasons.append('shorter than %.0f px' % MIN_LENGTH_PX)
        per, eligible = chain_persistence(pts, length, coarse, gray=gray)
        if per is not None and per < 0.5:
            reasons.append('vanishes at the coarser scales')
        if reasons:
            for i in ids:
                segments[i]['accepted'] = False
                segments[i]['reasons'] = segments[i]['reasons'] + reasons
            continue
        curve, scores = classify(pts)
        curve.update(segments=ids, length_px=round(length, 3), persistence=per,
                     persistence_scales=eligible, bic=scores, points=pts.round(2).tolist())
        curves.append(curve)
    accepted = [s for s in segments if s['accepted']]
    curves = join_arcs(curves)
    _label_kinds(curves, mask)
    if axis is not None and sym_iou >= SYMMETRIC_VIEW_IOU:
        _vote_symmetry(curves, axis)
    ys, xs = np.nonzero(mask)
    bbox = [int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1] if len(xs) else None
    return {'segments': segments, 'curves': curves, 'bbox': bbox,
            'symmetry': {'axis_x': axis, 'outline_iou': round(sym_iou, 4),
                         'symmetric': bool(sym_iou >= SYMMETRIC_VIEW_IOU)},
            'counts': {'candidates': len(segments), 'accepted': len(accepted),
                       'curves': len(curves),
                       'by_type': {t: sum(c['type'] == t for c in curves)
                                   for t in ('line', 'circle', 'ellipse', 'spline')}}}


def _coverage(points, center):
    """Fraction of the full turn the points cover around `center` (36 bins of 10 degrees)."""
    a = np.arctan2(points[:, 1] - center[1], points[:, 0] - center[0])
    bins = np.unique(np.floor((a + np.pi) / (2 * np.pi) * 36).astype(int) % 36)
    return len(bins) / 36.0


def join_arcs(curves, max_rms=1.0):
    """Join pieces of one round edge (a dial ring traced as short arcs or chords) into one curve.

    Two curves are joined when the union of their points is better explained by one circle or
    ellipse (BIC chooses a round type, within `max_rms` px or 1.2x the pieces' own error) and
    together they cover more of the turn than either alone. Long straight lines never join: a
    set of collinear points also fits a circle of enormous radius, which is excluded.
    """
    def candidate(c):
        return c['type'] in ('circle', 'ellipse', 'spline') or (c['type'] == 'line' and c['length_px'] < 40)

    def pair(ci, cj):
        pi, pj = np.asarray(ci['points']), np.asarray(cj['points'])
        union = np.vstack([pi, pj])
        span = float(np.ptp(union, axis=0).max())
        lo_i, hi_i, lo_j, hi_j = pi.min(0), pi.max(0), pj.min(0), pj.max(0)
        box_gap = float(np.max(np.maximum(0, np.maximum(lo_i - hi_j, lo_j - hi_i))))
        if box_gap > 0.5 * span:
            return None
        from scipy.spatial import cKDTree
        if float(cKDTree(pi).query(pj)[0].min()) > 0.5 * span:
            return None
        limit = max(max_rms, 1.2 * max(ci.get('rms_px', 0), cj.get('rms_px', 0)))
        quick, res, _ = fit_circle(union)                 # cheap test before the full model choice
        if quick['radius'] > 2 * span or quick['radius'] < 4 or                 float(np.sqrt(np.mean(res ** 2))) > 2 * limit:
            return None
        curve, scores = classify(union)
        if curve['type'] not in ('circle', 'ellipse'):
            return None
        center = curve['center']
        size = curve.get('radius') or max(curve['axes'])
        if size > 2 * span or size < 4 or curve['rms_px'] > limit:
            return None
        gain = _coverage(union, center) - max(_coverage(pi, center), _coverage(pj, center))
        if gain <= 0:
            return None
        return (curve['rms_px'], -gain), curve, scores, union

    items = {k: c for k, c in enumerate(curves)}
    next_id = len(curves)
    cand = sorted(k for k, c in items.items() if candidate(c))
    pairs = {}
    for x, i in enumerate(cand):
        for j in cand[x + 1:]:
            r = pair(items[i], items[j])
            if r is not None:
                pairs[(i, j)] = r
    while pairs:
        (i, j), (key, curve, scores, union) = min(pairs.items(), key=lambda kv: (kv[1][0], kv[0]))
        merged = dict(curve, bic=scores, points=union.round(2).tolist(),
                      segments=sorted(items[i]['segments'] + items[j]['segments']),
                      length_px=round(items[i]['length_px'] + items[j]['length_px'], 3),
                      joined=items[i].get('joined', 1) + items[j].get('joined', 1))
        del items[i], items[j]
        pairs = {k: v for k, v in pairs.items() if i not in k and j not in k}
        new = next_id
        next_id += 1
        for k in sorted(items):
            if candidate(items[k]):
                r = pair(items[k], merged)
                if r is not None:
                    pairs[(k, new)] = r
        items[new] = merged
    curves = [items[k] for k in sorted(items)]
    return curves


def _label_kinds(curves, mask):
    """Label what can be told from one view: outline (on the silhouette), closed (a loop that may
    be a part boundary) or interior. Crease versus decoration needs a second view
    (propkit/curve_views.py): a crease agrees across views, paint does not."""
    edge = mask & ~ndimage.binary_erosion(mask)
    dist = ndimage.distance_transform_edt(~edge)
    for c in curves:
        p = np.asarray(c['points'])
        r = np.clip(np.round(p[:, 1]).astype(int), 0, mask.shape[0] - 1)
        k = np.clip(np.round(p[:, 0]).astype(int), 0, mask.shape[1] - 1)
        on = float(np.mean(dist[r, k] <= 2.0))
        c['on_outline'] = round(on, 3)
        gap = float(np.hypot(*(p[0] - p[-1])))
        c['closed'] = bool(c['type'] in ('circle', 'ellipse') and c.get('joined', 1) > 1
                           or gap <= max(3.0, 0.1 * c['length_px']) and c['length_px'] > 30)
        c['kind'] = 'outline' if on >= 0.8 else ('closed' if c['closed'] else 'interior')


def _vote_symmetry(curves, axis, tolerance=2.0):
    from scipy.spatial import cKDTree
    trees = [cKDTree(np.asarray(c['points'])) for c in curves]
    for c in curves:
        p = np.asarray(c['points']).copy()
        p[:, 0] = 2 * axis - p[:, 0]
        c['mirrored'] = any(float(np.mean(t.query(p)[0])) <= tolerance for t in trees)


def overlay(image, result, path):
    """Accepted curves in colour by type over the view; rejected candidates in thin red."""
    from PIL import Image, ImageDraw
    base = Image.fromarray(np.asarray(image)[..., :3].astype(np.uint8)).convert('RGB')
    scale = max(1, int(np.ceil(900 / max(base.size))))
    im = base.resize((base.width * scale, base.height * scale), Image.NEAREST)
    im = Image.blend(im, Image.new('RGB', im.size, (255, 255, 255)), 0.45)
    d = ImageDraw.Draw(im)
    for s in result['segments']:
        if not s['accepted']:
            d.line([tuple(np.multiply(s['p0'], scale)), tuple(np.multiply(s['p1'], scale))],
                   fill=(220, 40, 40), width=1)
    colours = {'line': (20, 140, 60), 'circle': (30, 90, 220), 'ellipse': (130, 40, 200),
               'spline': (230, 130, 0)}
    for c in result['curves']:
        pts = [tuple(np.multiply(p, scale)) for p in c['points']]
        d.line(pts, fill=colours[c['type']], width=3)
    im.save(path)
