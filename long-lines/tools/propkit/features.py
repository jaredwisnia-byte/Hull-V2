"""Local features: a bump one outline shows is built only as wide as the views show it.

Why. Two outlines fix each slice only as rectangles (propkit/rounding.py). A switch that
sticks out of the back of a handle shows in the side outline, so every rectangle at its
height grows by the switch's depth across the handle's full width: a band, not a switch.

Measurement (for any object):
  1. Along each part (a run of section rectangles, rounding.tracks), each edge of the
     rectangle is followed station by station. Its smooth trend is a running median; a short
     run of stations where the edge stands out beyond the trend by more than the larger of two
     voxels and 8% of the section is a bump.
  2. The bump's other extent is not in any outline. It is measured in the painting of the view
     whose image axes are the bump's width direction and the part's axis: across the bump's
     rows, the pixels whose colour differs from the part's own (median colour of the part's
     other stations) by more than a threshold form the feature; its largest contiguous span is
     the feature's width. If no distinct painted feature narrower than the part is found, the
     bump keeps the full width (and the record says so).
  3. Build: at those stations, material beyond the trend edge and outside the measured width is
     removed. The bump's own outline is untouched, so every view still matches its drawing.
"""
import math

import numpy as np
from scipy import ndimage

from .rounding import _axis_slices, _slice_index, tracks, view_masks

DIMS = {'z': ('x', 'y', 'z'), 'x': ('y', 'z', 'x'), 'y': ('x', 'z', 'y')}   # axis: (a, b, along)
VIEW_FOR = {frozenset('xz'): 'front', frozenset('yz'): 'right', frozenset('xy'): 'top'}
COLOUR_STEP = 28.0      # RGB distance that separates a painted feature from its part


# each view's painting frame: object coordinate -> (image axis, flipped?)
FRAMES = {'front': {'x': ('col', False), 'z': ('row', True)},
          'back': {'x': ('col', True), 'z': ('row', True)},
          'right': {'y': ('col', False), 'z': ('row', True)},
          'left': {'y': ('col', True), 'z': ('row', True)},
          'top': {'x': ('col', False), 'y': ('row', True)},
          'bottom': {'x': ('col', False), 'y': ('row', False)}}
# the view that faces a bump: it looks along the bump's direction from the side it sticks out on
FACING = {('y', -1): 'front', ('y', 1): 'back', ('x', 1): 'right', ('x', -1): 'left',
          ('z', 1): 'top', ('z', -1): 'bottom'}


def _pixel(view, dim, value, size):
    """Where a normalised object coordinate falls in a view's painting: ('col'|'row', pixel)."""
    w, h = size
    axis, flip = FRAMES[view][dim]
    v = 1 - value if flip else value
    return (axis, v * (w if axis == 'col' else h))


def _span_in_painting(painting, view, width_dim, along_dim, along_range, width_range, reference=None):
    """The largest contiguous span (normalised, in width_dim) where the painting changes at the
    bump: each column across the bump is compared with the same column just before and after
    it along the part. Stripes and panels that run along the part cancel; a feature that starts
    and stops with the bump remains. Returns [lo, hi] or None."""
    a = np.asarray(painting.convert('RGB')).astype(float)
    size = painting.size
    k0 = _pixel(view, along_dim, along_range[0], size)
    k1 = _pixel(view, along_dim, along_range[1], size)
    w0 = _pixel(view, width_dim, width_range[0], size)
    w1 = _pixel(view, width_dim, width_range[1], size)
    lo_k, hi_k = sorted((int(k0[1]), int(math.ceil(k1[1]))))
    lo_w, hi_w = sorted((int(w0[1]), int(math.ceil(w1[1]))))
    hi_k, hi_w = max(hi_k, lo_k + 1), max(hi_w, lo_w + 1)
    L = max(2, hi_k - lo_k)
    if k0[0] == 'row':
        arr = a                                   # rows along the part
    else:
        arr = a.transpose(1, 0, 2)                # make rows run along the part
    n_along = arr.shape[0]
    inside = arr[lo_k:hi_k, lo_w:hi_w].mean(0)
    before = arr[max(0, lo_k - L):lo_k, lo_w:hi_w]
    after = arr[hi_k:min(n_along, hi_k + L), lo_w:hi_w]
    around = np.concatenate([before, after], 0) if len(before) + len(after) else None
    if around is None or len(around) == 0:
        return None
    prof = np.linalg.norm(inside - np.median(around, 0), axis=1)
    if prof.size < 3:
        return None
    hot = ndimage.binary_closing(prof > COLOUR_STEP, iterations=1)
    lab, n = ndimage.label(hot)
    if n == 0:
        return None
    sizes = ndimage.sum(hot, lab, range(1, n + 1))
    best = 1 + int(np.argmax(sizes))
    idx = np.nonzero(lab == best)[0]
    # a local feature is narrow against its part: wider than 40% of it is a different part or a
    # paint band, not a bump to localise
    if len(idx) > 0.4 * len(prof) or len(idx) < 2:
        return None
    span = (width_range[1] - width_range[0]) / len(prof)
    pix_lo, pix_hi = idx[0], idx[-1] + 1
    if w0[1] > w1[1]:
        pix_lo, pix_hi = len(prof) - pix_hi, len(prof) - pix_lo
    return [width_range[0] + pix_lo * span, width_range[0] + pix_hi * span]


def _reference_colour(painting, view, along_dim, width_dim, stations, skip, dims_ab):
    """Median colour of the part over its stations outside the bump."""
    a = np.asarray(painting.convert('RGB')).astype(float)
    size = painting.size
    samples = []
    for i, st in enumerate(stations):
        if i in skip:
            continue
        along = st[0]
        wc = (st[1] + st[2]) / 2 if dims_ab == 'a' else (st[3] + st[4]) / 2
        p_al = _pixel(view, along_dim, along, size)
        p_w = _pixel(view, width_dim, wc, size)
        r, c = (p_al[1], p_w[1]) if p_al[0] == 'row' else (p_w[1], p_al[1])
        r, c = int(min(max(r, 0), size[1] - 1)), int(min(max(c, 0), size[0] - 1))
        samples.append(a[r, c])
    return np.median(samples, axis=0) if samples else None


def _view_box(view, dims_ranges, size):
    """Pixel box (r0, r1, c0, c1) in a view's painting for normalised ranges of its two dims."""
    rows, cols = None, None
    for dim, (lo, hi) in dims_ranges.items():
        a = _pixel(view, dim, lo, size)
        b = _pixel(view, dim, hi, size)
        p0, p1 = sorted((int(a[1]), int(math.ceil(b[1]))))
        if a[0] == 'row':
            rows = (max(0, p0), min(size[1], max(p0 + 1, p1)))
        else:
            cols = (max(0, p0), min(size[0], max(p0 + 1, p1)))
    return rows, cols


def _painted(painting, mask):
    """Pixels the painting actually covers: inside the drawn outline and unlike the background
    (the median colour outside the outline). A drawn outline can be fuller than the paint, e.g.
    where two opposite views disagree and both are kept."""
    a = np.asarray(painting.convert('RGB')).astype(float)
    m = np.asarray(mask) > 0
    if m.shape != a.shape[:2]:
        return a, None
    bg = np.median(a[~m], axis=0) if (~m).any() else np.zeros(3)
    return a, m & (np.linalg.norm(a - bg, axis=2) > 12.0)


LOOKS_FROM = {'front': ('y', 0), 'right': ('x', 1), 'top': ('z', 1)}   # view: (axis, end it looks from)


def _span_by_colour(paintings, masks, width_dim, other_dim, along_dim, other_range, along_range,
                    width_range, min_fraction=0.15):
    """How wide a separate part really is across width_dim, read from the painting.

    The part's colour is the median painted colour inside its outline in the view that shows that
    outline (axes: other_dim and its axis). The view looking along the part's axis (axes:
    width_dim and other_dim) sees the part's cross-section end on, in front of whatever lies
    behind it; it is used only when the outline view shows no painted material between the
    part and that view. Columns across the width where the part's colour covers at least half
    the peak share (and min_fraction) of the part's band are the part. Returns ([lo, hi]
    normalised in width_dim, evidence) or (None, evidence)."""
    outline_view = VIEW_FOR.get(frozenset(other_dim + along_dim))
    measure_view = VIEW_FOR.get(frozenset(width_dim + other_dim))
    ev = {'colour_from': outline_view, 'measured_in': measure_view}
    if not all(v in paintings and v in masks for v in (outline_view, measure_view)):
        return None, ev
    if LOOKS_FROM.get(measure_view, (None,))[0] != along_dim:
        return None, ev
    sa, sp = _painted(paintings[outline_view], masks[outline_view])
    if sp is None:
        return None, ev
    size = paintings[outline_view].size
    rows, cols = _view_box(outline_view, {other_dim: other_range, along_dim: along_range}, size)
    fg = sp[rows[0]:rows[1], cols[0]:cols[1]]
    patch = sa[rows[0]:rows[1], cols[0]:cols[1]]
    if fg.sum() < 4:
        return None, ev
    colour = np.median(patch[fg], axis=0)
    # anything painted between the part and the measuring view would hide it there
    end = LOOKS_FROM[measure_view][1]
    near_range = (0.0, along_range[0]) if end == 0 else (along_range[1], 1.0)
    if near_range[1] - near_range[0] > 1e-6:
        r2, c2 = _view_box(outline_view, {other_dim: other_range, along_dim: near_range}, size)
        if sp[r2[0]:r2[1], c2[0]:c2[1]].mean() > 0.02 if sp[r2[0]:r2[1], c2[0]:c2[1]].size else False:
            ev['rejected'] = 'part hidden from the %s view' % measure_view
            return None, ev
    da, dp = _painted(paintings[measure_view], masks[measure_view])
    if dp is None:
        return None, ev
    rows, cols = _view_box(measure_view, {width_dim: width_range, other_dim: other_range},
                           paintings[measure_view].size)
    band = da[rows[0]:rows[1], cols[0]:cols[1]]
    bfg = dp[rows[0]:rows[1], cols[0]:cols[1]]
    if FRAMES[measure_view][width_dim][0] == 'row':
        band, bfg = band.transpose(1, 0, 2), bfg.T          # columns run across the width
    if band.shape[0] < 1 or band.shape[1] < 3:
        return None, ev
    near = (np.linalg.norm(band - colour, axis=2) < COLOUR_STEP) & bfg
    frac = near.mean(0)
    ev['colour'] = [round(float(c), 1) for c in colour]
    ev['peak_share'] = round(float(frac.max()), 3)
    hot = ndimage.binary_closing(frac >= max(min_fraction, 0.5 * frac.max()), iterations=1)
    lab, n = ndimage.label(hot)
    if n == 0 or frac.max() < min_fraction:
        ev['rejected'] = 'colour not found across the width'
        return None, ev
    sizes = ndimage.sum(hot, lab, range(1, n + 1))
    idx = np.nonzero(lab == 1 + int(np.argmax(sizes)))[0]
    if len(idx) > 0.4 * len(frac) or len(idx) < 2:
        ev['rejected'] = 'colour span %.0f%% of the width' % (100.0 * len(idx) / len(frac))
        return None, ev
    span = (width_range[1] - width_range[0]) / len(frac)
    pix_lo, pix_hi = idx[0], idx[-1] + 1
    if FRAMES[measure_view][width_dim][1]:
        pix_lo, pix_hi = len(frac) - pix_hi, len(frac) - pix_lo
    return [width_range[0] + pix_lo * span, width_range[0] + pix_hi * span], ev


def find(masks, paintings, size_m, res=110):
    """Local features of the drawn object. Returns a list of feature records (normalised)."""
    W, D, H = size_m['width'], size_m['depth'], size_m['height']
    big = max(W, D, H)
    shape = tuple(max(8, int(round(res * s / big))) for s in (W, D, H))
    front = masks['front']
    side = masks.get('right') if 'right' in masks else (masks['left'][:, ::-1] if 'left' in masks else None)
    top = masks.get('top')
    Fm, Sm, Tm = view_masks(front, side, top, shape)
    feats = []
    for axis in ('z', 'x', 'y'):
        a_dim, b_dim, along_dim = DIMS[axis]
        nk, A, B = _axis_slices(axis, Fm, Sm, Tm)
        na, nb = len(A(0)), len(B(0))
        for tr in tracks(axis, Fm, Sm, Tm, min_cells=8, ratio_limit=0.35):
            st = np.array(tr['stations'])
            if len(st) < 8:
                continue
            win = max(5, int(len(st) * 0.5) | 1)      # at least twice the longest feature allowed (25%)
            for col, sign, bump_dim, n_dim in ((1, -1, 'a', na), (2, 1, 'a', na), (3, -1, 'b', nb), (4, 1, 'b', nb)):
                e = st[:, col]
                trend = ndimage.median_filter(e, size=win, mode='nearest')
                dev = (e - trend) * sign
                width = (st[:, 2] - st[:, 1]) if bump_dim == 'a' else (st[:, 4] - st[:, 3])
                thr = np.maximum(2.0 / n_dim, 0.08 * np.median(width))
                lab, n = ndimage.label(ndimage.binary_closing(dev > thr, structure=np.ones(3), iterations=1) | (dev > thr))
                for i in range(1, n + 1):
                    run = np.nonzero(lab == i)[0]
                    # a local feature is small against its part: short along it, shallow across it
                    if len(run) > 0.25 * len(st) or dev[run].max() > 0.3 * np.median(width):
                        continue
                    width_dim = b_dim if bump_dim == 'a' else a_dim
                    out_dim = a_dim if bump_dim == 'a' else b_dim
                    view = FACING[(out_dim, sign)]
                    if view not in paintings or width_dim not in FRAMES[view] or along_dim not in FRAMES[view]:
                        continue
                    painting = paintings[view]
                    other = 'b' if bump_dim == 'a' else 'a'
                    ref = _reference_colour(painting, view, along_dim, width_dim, st, set(run.tolist()), other)
                    if ref is None:
                        continue
                    along_range = [float(st[run[0], 0] - .5 / nk), float(st[run[-1], 0] + .5 / nk)]
                    wr = [float(st[run, 3].min()), float(st[run, 4].max())] if other == 'b' else \
                         [float(st[run, 1].min()), float(st[run, 2].max())]
                    span = _span_in_painting(painting, view, width_dim, along_dim, along_range, wr, ref)
                    cut = float(trend[run].max() if sign > 0 else trend[run].min())
                    feats.append({'axis': axis, 'edge': ('a', 'b')[col > 2] + ('0', '1')[sign > 0],
                                  'bump_dim': {'a': a_dim, 'b': b_dim}[bump_dim],
                                  'width_dim': width_dim, 'along': along_range, 'cut': cut,
                                  'outward': sign, 'stands_out': float(dev[run].max()),
                                  'keep': span, 'measured_in': view,
                                  'status': 'localised from the painting' if span else
                                            'no distinct painted feature: full width kept'})
        # Separate parts (not the object's main body): a part's rectangle at each station is as
        # wide as two outlines allow, so a lever reaching over a body takes the full width of
        # whatever the front view shows at that height. The view looking down the part's length
        # sees its real footprint; where the painting localises the part narrower than 40% of
        # that width, the rest is removed (outlines are restored by apply).
        parts = tracks(axis, Fm, Sm, Tm, min_cells=8, ratio_limit=0.35)
        if len(parts) > 1:
            main = max(range(len(parts)), key=lambda i: parts[i].get('cells', 0))
            for pi, tr in enumerate(parts):
                if pi == main:
                    continue
                st = np.array(tr['stations'])
                along_range = [float(st[0, 0] - .5 / nk), float(st[-1, 0] + .5 / nk)]
                ar = [float(st[:, 1].min()), float(st[:, 2].max())]
                br = [float(st[:, 3].min()), float(st[:, 4].max())]
                for w_is_a in (True, False):
                    width_dim, other_dim = (a_dim, b_dim) if w_is_a else (b_dim, a_dim)
                    wr, orng = (ar, br) if w_is_a else (br, ar)
                    # suspicious: as wide as the whole object one way, local the other way
                    if wr[1] - wr[0] < 0.8 or orng[1] - orng[0] > 0.5:
                        continue
                    span, ev = _span_by_colour(paintings, masks, width_dim, other_dim, along_dim,
                                               orng, along_range, wr)
                    if not span:
                        continue
                    # remove beyond the part's inner face in the other dimension, outside the span
                    centre = 0.5 * (orng[0] + orng[1])
                    outward = 1 if centre >= 0.5 else -1
                    cut = orng[0] if outward > 0 else orng[1]
                    feats.append({'axis': axis, 'edge': ('b' if w_is_a else 'a') + ('1' if outward > 0 else '0'),
                                  'bump_dim': other_dim, 'width_dim': width_dim, 'along': along_range,
                                  'cut': float(cut), 'outward': outward, 'stands_out': float(orng[1] - orng[0]),
                                  'keep': span, 'measured_in': ev.get('measured_in'), 'kind': 'part',
                                  'evidence': ev, 'status': 'separate part localised from the painting'})
    feats += end_shapes(masks, paintings, shape)
    return feats


def _body_extent(cover):
    """Where an outline's cover along an axis is at least half its largest: the main body."""
    on = np.nonzero(cover >= 0.5 * cover.max())[0]
    return (int(on.min()), int(on.max()) + 1) if on.size else (0, len(cover))


def _painted_shape(painting, mask, view, box_dims, box):
    """The painted feature filling a box of a view: the area its painted edges enclose around the
    box's centre, holes filled. Returns (polygon in the view's normalised dims, fill of the box)
    or (None, reason). The shape is whatever the paint shows (round, square, anything)."""
    from skimage.feature import canny
    from skimage.measure import find_contours
    a = np.asarray(painting.convert('RGB')).astype(float) / 255
    size = painting.size
    (d0, r0), (d1, r1) = box_dims[0], box_dims[1]
    rows, cols = _view_box(view, {d0: r0, d1: r1}, size)
    pad_r, pad_c = max(2, (rows[1] - rows[0]) // 8), max(2, (cols[1] - cols[0]) // 8)
    R0, R1 = max(0, rows[0] - pad_r), min(size[1], rows[1] + pad_r)
    C0, C1 = max(0, cols[0] - pad_c), min(size[0], cols[1] + pad_c)
    win = a[R0:R1, C0:C1]
    if min(win.shape[:2]) < 8:
        return None, 'too small to trace'
    from skimage.color import rgb2lab
    lab = rgb2lab(win)
    sigma = max(1.0, min(win.shape[:2]) / 60)
    edges = np.zeros(win.shape[:2], bool)
    for c in range(3):
        edges |= canny(lab[..., c], sigma=sigma)
    edges = ndimage.binary_dilation(edges, iterations=1)
    lab_regions, n = ndimage.label(~edges)
    if n == 0:
        return None, 'no enclosed area'
    # the largest area the painted edges enclose inside the box (not one touching the window's rim)
    inner = np.zeros(win.shape[:2], bool)
    inner[rows[0] - R0:rows[1] - R0, cols[0] - C0:cols[1] - C0] = True
    rim = set(np.unique(np.r_[lab_regions[0], lab_regions[-1], lab_regions[:, 0], lab_regions[:, -1]]))
    sizes = ndimage.sum(inner, lab_regions, range(1, n + 1))
    order = [i + 1 for i in np.argsort(sizes)[::-1] if i + 1 not in rim]
    if not order:
        return None, 'no enclosed area inside the box'
    region = ndimage.binary_fill_holes(lab_regions == order[0])
    region = ndimage.binary_closing(region, iterations=max(1, int(sigma)))
    ys, xs = np.nonzero(region)
    bh, bw = rows[1] - rows[0], cols[1] - cols[0]
    span_r = (ys.max() - ys.min() + 1) / max(1, bh)
    span_c = (xs.max() - xs.min() + 1) / max(1, bw)
    if not (0.75 <= span_r <= 1.3 and 0.75 <= span_c <= 1.3):
        return None, 'painted feature does not fill the box (%.2f x %.2f)' % (span_r, span_c)
    fill = region.sum() / float(max(1, (ys.max() - ys.min() + 1) * (xs.max() - xs.min() + 1)))
    cont = max(find_contours(np.pad(region, 1).astype(float), 0.5), key=len) - 1
    poly = []
    for r, c in cont[::max(1, len(cont) // 64)]:
        pr, pc = r + R0, c + C0
        out = {}
        for dim in (d0, d1):
            axis, flip = FRAMES[view][dim]
            v = (pc / size[0]) if axis == 'col' else (pr / size[1])
            out[dim] = 1 - v if flip else v
        poly.append([round(float(out[d0]), 4), round(float(out[d1]), 4)])
    return poly, round(float(fill), 3)


def _closed_features(painting, mask, min_share=0.002, max_share=0.15):
    """Closed areas a view's painted edges enclose (holes filled): each feature's own outline."""
    a = np.asarray(painting.convert('RGB')).astype(float) / 255
    m = np.asarray(mask, bool)
    if m.shape != a.shape[:2]:
        return []
    # structural edges (propkit/feature_regions.py): the trained detector where it is configured
    # (HULL_TRACE_BACKEND=auto), classical multiscale edges otherwise; paint cracks and brush
    # marks are its fine candidates and never split a feature
    from . import feature_regions
    import os as _os
    linear = np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)
    traced = feature_regions.trace(linear, m, _os.environ.get('HULL_FEATURE_BACKEND', 'auto'))
    edges = ndimage.binary_closing((traced['structural_score'] > 0.5) & m, iterations=1)
    edges = ndimage.binary_dilation(edges, iterations=1)
    regions, n = ndimage.label(m & ~edges)
    total = float(m.sum())
    out = []
    for i, sl in enumerate(ndimage.find_objects(regions), 1):
        if sl is None:
            continue
        r = ndimage.binary_fill_holes(regions[sl] == i)
        share = r.sum() / total
        if not (min_share <= share <= max_share):
            continue
        if r.mean() < 0.55:                     # a ragged sliver, not a feature
            continue
        colour = np.median(a[sl][r], axis=0) * 255
        out.append({'slice': sl, 'region': r, 'colour': colour, 'share': share})
    return out


def _same_paint(pixels, colour, chroma_tol=0.035, bright=(0.4, 1.7)):
    """The same paint under another view's lighting: the same hue and saturation (chromaticity,
    each channel's share of the sum) at a brightness within a range of the reference."""
    px = np.asarray(pixels, float)
    c = np.asarray(colour, float)
    s_px = px.sum(-1, keepdims=True) + 1e-6
    s_c = c.sum() + 1e-6
    chroma = np.linalg.norm(px / s_px - c / s_c, axis=-1)
    ratio = s_px[..., 0] / s_c
    return (chroma < chroma_tol) & (ratio >= bright[0]) & (ratio <= bright[1])


def _body_span(mask, view, dim):
    """Normalised (lo, hi) of the main body along one of a view's dims: where the outline covers at
    least half its largest cover. Views are compared in body coordinates, so a lever or knob that
    sticks out further in one view does not stretch its frame."""
    m = np.asarray(mask, bool)
    axis, flip = FRAMES[view][dim]
    cover = m.mean(0) if axis == 'col' else m.mean(1)
    lo, hi = _body_extent(cover)
    n = len(cover)
    u0, u1 = lo / n, hi / n
    return (1 - u1, 1 - u0) if flip else (u0, u1)


def _to_body(u, span):
    return (u - span[0]) / max(1e-6, span[1] - span[0])


def _colour_run(painting, mask, view, band, across, colour, min_frac=0.3):
    """Contiguous runs, across a view, where a colour fills at least min_frac of a band."""
    a = np.asarray(painting.convert('RGB')).astype(float)
    m = np.asarray(mask, bool)
    band_dim, (lo, hi) = band
    rows, cols = _view_box(view, {band_dim: (lo, hi), across: (0.0, 1.0)}, painting.size)
    win = a[rows[0]:rows[1], cols[0]:cols[1]]
    wm = m[rows[0]:rows[1], cols[0]:cols[1]]
    if FRAMES[view][across][0] == 'row':
        win, wm = win.transpose(1, 0, 2), wm.T
    hot = (_same_paint(win, colour) & wm).mean(0) >= min_frac
    hot = ndimage.binary_closing(hot, iterations=1)
    lab, n = ndimage.label(hot)
    runs = []
    for i in range(1, n + 1):
        idx = np.nonzero(lab == i)[0]
        if len(idx) < 2:
            continue
        u0, u1 = idx[0] / len(hot), (idx[-1] + 1) / len(hot)
        if FRAMES[view][across][1]:
            u0, u1 = 1 - u1, 1 - u0
        runs.append((u0, u1))
    return runs


def end_shapes(masks, paintings, shape):
    """Parts painted in the view that looks along them take their cross-section from that view.

    The way a draftsman reads a knob: in the side view it is a closed painted outline (here
    round); projection lines carry its height into the front view and its depth into the top view,
    where the same paint shows its width. When both agree, the part is the traced outline extruded
    over that width, so whatever lies inside its box but outside its outline (a square's corners)
    is not the part. Paint, not silhouettes, marks where a knob stops and the carriage starts."""
    view = 'right'
    need = (view, 'front', 'top')
    if not all(v in paintings and v in masks for v in need):
        return []
    out = []
    size = paintings[view].size
    for f in _closed_features(paintings[view], masks[view]):
        sl, r = f['slice'], f['region']
        if max(f['colour']) < 25:            # the background enclosed between parts, not paint
            continue
        # the feature's box in world coordinates (side view: columns -> y, rows -> z, z up)
        y0, y1 = sl[1].start / size[0], sl[1].stop / size[0]
        z0, z1 = 1 - sl[0].stop / size[1], 1 - sl[0].start / size[1]
        front = _colour_run(paintings['front'], masks['front'], 'front', ('z', (z0, z1)), 'x', f['colour'])
        top = _colour_run(paintings['top'], masks['top'], 'top', ('y', (y0, y1)), 'x', f['colour'])
        fspan = _body_span(masks['front'], 'front', 'x')
        tspan = _body_span(masks['top'], 'top', 'x')
        tol = 0.04
        for u0, u1 in front:
            if u1 - u0 > 0.15:                 # wider than a part sticking out of the body
                continue
            b0, b1 = _to_body(u0, fspan), _to_body(u1, fspan)
            agree = [t for t in top if abs(_to_body(t[0], tspan) - b0) <= tol
                     and abs(_to_body(t[1], tspan) - b1) <= tol]
            if not agree:
                continue
            ys, xs = np.nonzero(r)
            from skimage.measure import find_contours
            cont = max(find_contours(np.pad(r, 1).astype(float), 0.5), key=len) - 1
            poly = [[round(float((c + sl[1].start) / size[0]), 4), round(float(1 - (rr + sl[0].start) / size[1]), 4)]
                    for rr, c in cont[::max(1, len(cont) // 64)]]
            fill = float(r.mean())
            out.append({'kind': 'end_shape', 'axis': 'x', 'along': [round(u0, 4), round(u1, 4)],
                        'shape_view': view, 'box': {'y': [round(y0, 4), round(y1, 4)], 'z': [round(z0, 4), round(z1, 4)]},
                        'section': poly, 'fill': round(fill, 3), 'keep': True,
                        'colour': [round(float(c)) for c in f['colour']],
                        'status': 'traced in the %s view (fills %.0f%% of its box); width from front and top paint'
                                  % (view, 100 * fill)})
    return out


def _apply_end_shape(out, f, Fm, Sm, Tm):
    """Inside the part's box and width, remove what lies outside its traced outline (dilated one voxel)."""
    from PIL import Image as _Image, ImageDraw as _Draw
    nx, ny, nz = out.shape
    img = _Image.new('L', (ny, nz), 0)
    _Draw.Draw(img).polygon([(p[0] * ny, (1 - p[1]) * nz) for p in f['section']], fill=1)
    sec = ndimage.binary_dilation(np.asarray(img, bool)[::-1].T, iterations=1)    # [y, z]
    box = np.zeros((ny, nz), bool)
    y0, y1 = int(f['box']['y'][0] * ny), int(np.ceil(f['box']['y'][1] * ny))
    z0, z1 = int(f['box']['z'][0] * nz), int(np.ceil(f['box']['z'][1] * nz))
    box[y0:y1, z0:z1] = True
    k0, k1 = int(round(f['along'][0] * nx)), int(round(f['along'][1] * nx))
    if k1 <= k0:
        f['applied'] = 'no width at this resolution'
        return out
    # A part sticking out stands alone over its width: most material there is inside its box.
    # Paint on a larger body (a stripe, a plate) is not: its slices are mostly the body.
    # Only where the part stands clear of the body: slices whose material is mostly inside its box.
    # Paint on a larger body (a stripe, a plate) never does; a knob does over its protruding length.
    cut = 0
    for k in range(k0, k1):
        sl = out[k]
        total = sl.sum()
        if total and (sl & box).sum() / float(total) >= 0.7:
            out[k] &= ~(box & ~sec)
            cut += 1
    f['applied'] = ('cut to its outline over %d of %d slices' % (cut, k1 - k0)) if cut else         'nowhere stands clear of the body'
    return out


def apply(keep, front, side, top, feats, report=None):
    """Remove each localised bump's material outside its measured width (outlines kept)."""
    shapes = [f for f in feats or [] if f.get('kind') == 'end_shape' and f.get('keep')]
    feats = [f for f in feats or [] if f.get('keep') and f.get('kind') != 'end_shape']
    if shapes:
        Fm0, Sm0, Tm0 = view_masks(front, side, top, keep.shape)
        cut = keep.copy()
        for f in shapes:
            cut = _apply_end_shape(cut, f, Fm0, Sm0, Tm0)
        removed = keep & ~cut
        for ax, want in ((1, Fm0), (0, Sm0), (2, Tm0)):
            lost = want & ~cut.any(ax) & keep.any(ax)
            if lost.any():
                cut |= removed & np.expand_dims(lost, ax)
        if report is not None:
            report['end_shapes'] = {'candidates': len(shapes), 'voxels_removed': int((keep & ~cut).sum()),
                                    'decisions': [[f['along'], f['box'], f.get('applied')] for f in shapes]}
        keep = cut
    if not feats:
        return keep
    Fm, Sm, Tm = view_masks(front, side, top, keep.shape)
    out = keep.copy()
    for f in feats:
        axis = f['axis']
        nk, A, B = _axis_slices(axis, Fm, Sm, Tm)
        na, nb = len(A(0)), len(B(0))
        ia = (np.arange(na) + .5) / na
        ib = (np.arange(nb) + .5) / nb
        for k in range(nk):
            c = (k + .5) / nk
            if not (f['along'][0] <= c <= f['along'][1]):
                continue
            bump_is_a = f['edge'][0] == 'a'
            coord_b, coord_w = (ia, ib) if bump_is_a else (ib, ia)
            beyond = (coord_b > f['cut']) if f['outward'] > 0 else (coord_b < f['cut'])
            outside = (coord_w < f['keep'][0]) | (coord_w > f['keep'][1])
            cut = (beyond[:, None] & outside[None, :]) if bump_is_a else (outside[:, None] & beyond[None, :])
            out[_slice_index(axis, k)] &= ~cut
    removed = keep & ~out
    if removed.any():
        for ax, want in ((1, Fm), (0, Sm), (2, Tm)):
            lost = want & ~out.any(ax) & keep.any(ax)
            if lost.any():
                out |= removed & np.expand_dims(lost, ax)
    if report is not None:
        report['local_features'] = {'applied': len(feats), 'voxels_removed': int((keep & ~out).sum())}
    return out
