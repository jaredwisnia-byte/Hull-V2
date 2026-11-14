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
    return feats


def apply(keep, front, side, top, feats, report=None):
    """Remove each localised bump's material outside its measured width (outlines kept)."""
    feats = [f for f in feats or [] if f.get('keep')]
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
