"""The draftsman stage: every feature traced in each view and matched along projection lines.

Jared's method (2026-11-16). A draftsman reads three orthographic views by carrying each feature
from view to view along projection lines: front and top share width (x), front and side share
height (z), side and top share depth (y, through the 45-degree mitre). A feature is a part when
all three views agree on where it is; the view where its outline shows its shape decides its
cross-section (a knob painted round in the side view is round, whatever rectangles the front and
top views show, because that is what a round part looks like from its side).

This stage adds to the outline drawing; it does not replace it. The outlines stay the body.

1. Features. Each view's structural edges (propkit/feature_regions.py: the trained detector where
   configured, classical edges otherwise; paint cracks never split a feature) enclose areas; each
   area is one feature, its outline fitted with lines and arcs (propkit/drafting.fit_profile).
2. Frame. Views are compared in body coordinates: on each axis the body is where the outline
   covers at least half its largest cover, so a lever or knob sticking out further in one view
   does not stretch its frame.
3. Matching. A feature traced in one view (its shape view) gives two dimensions. Each of the other
   two views shares one of them with it and adds the third: inside the band the shared dimension
   gives, the feature's own paint (same hue, any lighting) runs across the third dimension. Where
   both views put that run at the same place, the part is confirmed in all three views.

Nothing here builds geometry by itself; the parts and the sheet are the drawing evidence.
"""
import math

import numpy as np
from scipy import ndimage

from . import drafting
from .features import FRAMES, _view_box, _same_paint

PRIMARY = ('front', 'right', 'top')
ALL_VIEWS = ('front', 'back', 'right', 'left', 'top', 'bottom')
AXES = {'front': ('x', 'z'), 'back': ('x', 'z'), 'right': ('y', 'z'), 'left': ('y', 'z'),
        'top': ('x', 'y'), 'bottom': ('x', 'y')}
LOOKS_ALONG = {'front': 'y', 'back': 'y', 'right': 'x', 'left': 'x', 'top': 'z', 'bottom': 'z'}
MIN_SHARE, MAX_SHARE = 0.0004, 0.2      # of the view's foreground
EDGE_THRESHOLD = 0.5
MAX_RUN = 0.35                           # a part is narrower than this share of the body
TOL = 0.04                               # agreement between views, body coordinates


def _world(view, size, px, py):
    """Pixel position -> normalised coordinates on the view's two dims."""
    out = {}
    for dim in AXES[view]:
        axis, flip = FRAMES[view][dim]
        v = (px / size[0]) if axis == 'col' else (py / size[1])
        out[dim] = 1 - v if flip else v
    return out


def trace(painting, mask, backend='auto'):
    """Closed features of one view: area, box, colour and line/arc outline of each."""
    from . import feature_regions
    a = np.asarray(painting.convert('RGB')).astype(float) / 255
    m = np.asarray(mask, bool)
    linear = np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)
    traced = feature_regions.trace(linear, m, backend)
    edges = ndimage.binary_closing((traced['structural_score'] > EDGE_THRESHOLD) & m, iterations=1)
    areas, n = ndimage.label(m & ~ndimage.binary_dilation(edges, iterations=1))
    total = float(m.sum())
    feats = []
    for i, sl in enumerate(ndimage.find_objects(areas), 1):
        if sl is None:
            continue
        r = ndimage.binary_fill_holes(areas[sl] == i)
        share = r.sum() / total
        if not (MIN_SHARE <= share <= MAX_SHARE):
            continue
        colour = np.median(a[sl][r], axis=0) * 255
        if colour.max() < 25:                 # background enclosed between parts
            continue
        full = np.zeros(m.shape, bool)
        full[sl] = r
        f = {'id': i, 'share': float(share), 'fill': float(r.mean()), 'colour': colour,
             'px_box': [sl[1].start, sl[0].start, sl[1].stop, sl[0].stop], 'mask': full}
        try:
            verts, dev = drafting.fit_profile(full)
            v = np.asarray(verts, float)
            x0, y0, x1, y1 = f['px_box']
            pad = 0.25 * max(x1 - x0, y1 - y0) + 3
            pts = np.asarray(_entity_points(v))
            if ((pts[:, 0] < x0 - pad) | (pts[:, 0] > x1 + pad) | (pts[:, 1] < y0 - pad) | (pts[:, 1] > y1 + pad)).any():
                f['outline_error'] = 'fitted outline leaves its own area'
            else:
                f['outline'] = v.round(3).tolist()
                f['arcs'] = int((np.abs(v[:, 2]) > 1e-9).sum())
        except Exception as exc:
            f['outline_error'] = str(exc)
        feats.append(f)
    return feats, traced.get('tracing_backend', {})


REFERENCE = {'x': 'front', 'z': 'front', 'y': 'right'}   # the view each axis is measured in


class Frame:
    """A view's coordinates mapped onto each axis's reference view (front for width and height,
    side for depth) by propkit/curve_views.py's registration: matched outline breakpoints (the
    same step seen in both views) anchor a monotone piecewise-linear map, so views painted with
    slightly different proportions, or with a part sticking out further in one, still line up."""

    def __init__(self, view, mask, size, regs):
        self.view, self.size = view, size
        m = np.asarray(mask, bool)
        rows, cols = np.nonzero(m)
        self.bbox = (cols.min(), rows.min(), cols.max() + 1, rows.max() + 1)
        self.regs = regs                     # dim -> (Registration, this view is 'a' or 'b') or None

    def _box_norm(self, dim, u):
        """painting-normalised -> outline-box-normalised (curve_views' frame)."""
        axis, flip = FRAMES[self.view][dim]
        x0, y0, x1, y1 = self.bbox
        W, H = self.size
        u = np.asarray(u, float)
        p = (1 - u if flip else u) * (W if axis == 'col' else H)
        lo, hi = (x0, x1) if axis == 'col' else (y0, y1)
        n = (p - lo) / max(1, hi - lo)
        return 1 - n if flip else n

    def _paint_norm(self, dim, n):
        axis, flip = FRAMES[self.view][dim]
        x0, y0, x1, y1 = self.bbox
        W, H = self.size
        n = np.asarray(n, float)
        n = 1 - n if flip else n
        lo, hi = (x0, x1) if axis == 'col' else (y0, y1)
        p = lo + n * (hi - lo)
        u = p / (W if axis == 'col' else H)
        return 1 - u if flip else u

    def to_body(self, dim, u):
        n = self._box_norm(dim, u)
        reg = self.regs.get(dim)
        if reg is None:
            return n
        c = np.clip(n, 0, 1)                 # the map covers the outline box; beyond it, slope 1
        return reg.to_a(c) + (n - c)

    def from_body(self, dim, b):
        reg = self.regs.get(dim)
        b = np.asarray(b, float)
        if reg is None:
            n = b
        else:
            c = np.clip(b, 0, 1)
            n = reg.to_b(c) + (b - c)
        return self._paint_norm(dim, n)

    def box(self, f):
        x0, y0, x1, y1 = f['px_box']
        p, q = _world(self.view, self.size, x0, y0), _world(self.view, self.size, x1, y1)
        return {d: tuple(sorted((float(self.to_body(d, p[d])), float(self.to_body(d, q[d]))))) for d in AXES[self.view]}


def _box_coord(view, bbox, dim, px, py):
    """Pixel -> outline-box-normalised coordinate on dim (curve_views' frame)."""
    axis, flip = FRAMES[view][dim]
    x0, y0, x1, y1 = bbox
    n = (px - x0) / max(1, x1 - x0) if axis == 'col' else (py - y0) / max(1, y1 - y0)
    return 1 - n if flip else n


def _row_anchors(paintings, masks, boxes, feats, ref, v, dim, min_count=6):
    """Anchors from a repeated part (a row of keys): its rows along `dim` in view v, in order, are
    the same rows the reference view shows as runs of the same paint along `dim`. Outline steps
    cannot register an axis along which the outline does not change (a keyboard's depth seen from
    above); a repeated part's rows can."""
    groups = []
    for f in feats.get(v, []):
        if f['share'] > 0.01:
            continue
        for g in groups:
            r = g[0]
            if np.linalg.norm(f['colour'] - r['colour']) < 40 and 0.5 < f['share'] / r['share'] < 2:
                g.append(f)
                break
        else:
            groups.append([f])
    groups = [g for g in groups if len(g) >= min_count]
    if not groups:
        return []
    g = max(groups, key=len)
    centres = sorted(_box_coord(v, boxes[v]['bbox'], dim, (f['px_box'][0] + f['px_box'][2]) / 2,
                                (f['px_box'][1] + f['px_box'][3]) / 2) for f in g)
    rows = []
    for c in centres:
        if not rows or c - rows[-1][-1] > 0.02:
            rows.append([c])
        else:
            rows[-1].append(c)
    rows = [float(np.mean(r)) for r in rows if len(r) >= 2]
    if len(rows) < 3:
        return []
    colour = np.median([f['colour'] for f in g], axis=0)
    from . import curve_views as cv

    def runs(prof, longest=0.12):
        hot = ndimage.binary_closing(prof > max(0.02, 0.25 * prof.max()), iterations=1)
        lab, n = ndimage.label(hot)
        out = []
        for i in range(1, n + 1):
            idx = np.nonzero(lab == i)[0]
            if 2 <= len(idx) <= longest * len(prof):
                out.append(((idx[0]) / len(prof), (idx[-1] + 1) / len(prof)))
        return out

    def profile(view, along, band_dim=None, band=None):
        a_ = np.asarray(paintings[view].convert('RGB')).astype(float)
        x0, y0, x1, y1 = boxes[view]['bbox']
        win, wm = a_[y0:y1, x0:x1], masks[view][y0:y1, x0:x1]
        same = _same_paint(win, colour) & wm
        if band_dim is not None:
            bax, bflip = FRAMES[view][band_dim]
            lo, hi = (1 - band[1], 1 - band[0]) if bflip else band
            n_ = same.shape[1] if bax == 'col' else same.shape[0]
            i0, i1 = int(lo * n_), max(int(lo * n_) + 1, int(np.ceil(hi * n_)))
            same = same[:, i0:i1] if bax == 'col' else same[i0:i1]
        ax, flip = FRAMES[view][along]
        prof = same.mean(0) if ax == 'col' else same.mean(1)
        return prof[::-1] if flip else prof

    ref_rows = []
    if dim == 'y' and ref == 'right' and 'front' in paintings:
        # The rows' heights from the front view (runs of the part's paint across z), carried into
        # the side view; there each row's depth is where that paint lies along y in its band.
        x_lo = min(_box_coord(v, boxes[v]['bbox'], 'x', f['px_box'][0], 0) for f in g)
        x_hi = max(_box_coord(v, boxes[v]['bbox'], 'x', f['px_box'][2], 0) for f in g)
        zr = runs(profile('front', 'z', 'x', (x_lo, x_hi)))
        reg_z = cv.registration(boxes, masks, 'front', 'right', 'z')
        for z0, z1 in zr:
            b0, b1 = sorted((float(reg_z.to_b(z0)), float(reg_z.to_b(z1))))
            yr = runs(profile('right', 'y', 'z', (b0, b1)), longest=0.3)
            if yr:
                y0_, y1_ = max(yr, key=lambda r: r[1] - r[0])
                ref_rows.append((y0_ + y1_) / 2)
        ref_rows = sorted(ref_rows)
    elif ref in feats:
        # The reference view traces the same repeated part itself (keys in the front and top views):
        # its instances' positions along dim, clustered the same way, are the rows there.
        rg = [f for f in feats[ref] if f['share'] <= 0.01 and np.linalg.norm(f['colour'] - colour) < 45]
        rc = sorted(_box_coord(ref, boxes[ref]['bbox'], dim, (f['px_box'][0] + f['px_box'][2]) / 2,
                               (f['px_box'][1] + f['px_box'][3]) / 2) for f in rg)
        for c in rc:
            if not ref_rows or c - ref_rows[-1][-1] > 0.02:
                ref_rows.append([c])
            else:
                ref_rows[-1].append(c)
        ref_rows = [float(np.mean(r)) for r in ref_rows if len(r) >= 2]
    if len(ref_rows) < len(rows):
        return []
    best = None
    for off in range(len(ref_rows) - len(rows) + 1):
        A = np.array(ref_rows[off:off + len(rows)])
        B = np.array(rows)
        slope, icpt = np.polyfit(B, A, 1)
        res = np.abs(A - (slope * B + icpt)).max()
        if 0.5 < slope < 2 and (best is None or res < best[0]):
            best = (res, A, B)
    if best is None or best[0] > 0.015:
        return []
    return [(float(a_), float(b_)) for a_, b_ in zip(best[1], best[2])]


def frames_for(paintings, masks, feats=None):
    """Frames for the three primary views, each axis registered onto its reference view."""
    from . import curve_views as cv
    views = [v for v in ALL_VIEWS if v in paintings and v in masks]
    boxes = {}
    for v in views:
        m = np.asarray(masks[v], bool)
        rows, cols = np.nonzero(m)
        boxes[v] = {'bbox': (cols.min(), rows.min(), cols.max() + 1, rows.max() + 1)}
    ms = {v: np.asarray(masks[v], bool) for v in views}
    frames, report = {}, {}
    for v in views:
        regs = {}
        for dim in AXES[v]:
            ref = REFERENCE[dim]
            if ref == v:
                regs[dim] = None
                continue
            reg = cv.registration(boxes, ms, ref, v, dim)
            extra = _row_anchors(paintings, ms, boxes, feats, ref, v, dim) if feats else []
            if len(extra) >= 3:
                # candidates: outline steps alone, repeated-part rows alone, and the outline steps
                # that agree with the rows plus the rows; keep the most precise by the
                # registration's own leave-one-out measure
                xb, xa = np.array([e[1] for e in extra]), np.array([e[0] for e in extra])
                slope, icpt = np.polyfit(xb, xa, 1)
                agree = [pq for pq in reg.pairs if abs(pq[0] - (slope * pq[1] + icpt)) <= 0.02]
                cands = [reg]
                for pairs in (extra, agree + extra):
                    c = cv.Registration(list(pairs), reg.floor, reg.rigid_tolerance)
                    c.rigid_tolerance = reg.rigid_tolerance
                    cands.append(c)
                reg = min(cands, key=lambda c: c.tolerance if c.piecewise else c.tolerance + 1)
            regs[dim] = reg
            report['%s->%s %s' % (v, ref, dim)] = dict(reg.summary(), repeated_row_anchors=len(extra))
        frames[v] = Frame(v, masks[v], paintings[v].size, regs)
    return frames, report


def _runs(painting, mask, view, frame, band_dim, band_body, across, colour, min_frac=0.25):
    """Runs (body coordinates on `across`) where the colour fills at least min_frac of the band."""
    a = np.asarray(painting.convert('RGB')).astype(float)
    m = np.asarray(mask, bool)
    lo, hi = (float(frame.from_body(band_dim, band_body[0])), float(frame.from_body(band_dim, band_body[1])))
    rows, cols = _view_box(view, {band_dim: (max(0.0, lo), min(1.0, hi)), across: (0.0, 1.0)}, painting.size)
    win = a[rows[0]:rows[1], cols[0]:cols[1]]
    wm = m[rows[0]:rows[1], cols[0]:cols[1]]
    if win.size == 0:
        return []
    if FRAMES[view][across][0] == 'row':
        win, wm = win.transpose(1, 0, 2), wm.T
    same = _same_paint(win, colour) & wm
    hot = ndimage.binary_closing(same.mean(0) >= min_frac, iterations=1)
    # the same paint just outside the band, at the run's place: a stripe running on past the
    # part (trim, a seam) rather than the part itself
    margin = 0.5 * (hi - lo)                 # the strip right beside the part: a gap for a key, paint for a stripe
    rows2, cols2 = _view_box(view, {band_dim: (max(0.0, lo - margin), min(1.0, hi + margin)), across: (0.0, 1.0)}, painting.size)
    wide = a[rows2[0]:rows2[1], cols2[0]:cols2[1]]
    widem = m[rows2[0]:rows2[1], cols2[0]:cols2[1]]
    if FRAMES[view][across][0] == 'row':
        wide, widem = wide.transpose(1, 0, 2), widem.T
    wide_same = (_same_paint(wide, colour) & widem).mean(0) if wide.size else None
    lab, n = ndimage.label(hot)
    out = []
    for i in range(1, n + 1):
        idx = np.nonzero(lab == i)[0]
        if len(idx) < 2:
            continue
        if wide_same is not None and len(wide_same) == len(hot):
            inside = same.mean(0)[idx].mean()
            around = (wide_same[idx].mean() * wide.shape[0] - inside * win.shape[0]) / max(1, wide.shape[0] - win.shape[0])
            if around > 0.6 * inside:
                continue
        u0, u1 = idx[0] / len(hot), (idx[-1] + 1) / len(hot)
        if FRAMES[view][across][1]:
            u0, u1 = 1 - u1, 1 - u0
        out.append(tuple(sorted((float(frame.to_body(across, u0)), float(frame.to_body(across, u1))))))
    return out


def match(paintings, masks, feats, frames, triple=PRIMARY):
    """Parts confirmed in all three views (see the module docstring, step 3)."""
    parts = []
    for s in triple:
        n = LOOKS_ALONG[s]
        others = [v for v in triple if v != s]
        for f in feats[s]:
            box = frames[s].box(f)
            reads = []
            for v in others:
                shared = [d for d in AXES[v] if d != n][0]
                runs = _runs(paintings[v], masks[v], v, frames[v], shared, box[shared], n, f['colour'])
                reads.append([r for r in runs if r[1] - r[0] <= MAX_RUN])
            if not all(reads):
                continue
            for r1 in reads[0]:
                for r2 in reads[1]:
                    if abs(r1[0] - r2[0]) <= TOL and abs(r1[1] - r2[1]) <= TOL:
                        part = dict(box)
                        part[n] = ((r1[0] + r2[0]) / 2, (r1[1] + r2[1]) / 2)
                        ext = [part[d][1] - part[d][0] for d in 'xyz']
                        if sum(e > 0.5 for e in ext) >= 2 or min(ext) < 0.01:
                            continue                 # most of the body, or a line: not a part
                        parts.append({'shape_view': s, 'feature': f['id'], 'axis': n,
                                      'box_body': {d: [round(part[d][0], 4), round(part[d][1], 4)] for d in 'xyz'},
                                      'fill': round(f['fill'], 3), 'arcs': f.get('arcs', 0),
                                      'colour': [int(c) for c in f['colour']]})
    # the same part found from two shape views: keep one (the one whose outline fills its box less,
    # i.e. shows the most shape)
    kept = []
    for p in sorted(parts, key=lambda p: p['fill']):
        b = p['box_body']
        if all(max(abs(b[d][i] - q['box_body'][d][i]) for d in 'xyz' for i in (0, 1)) > TOL for q in kept):
            kept.append(p)
    return kept


def _paint_share(painting, mask, view, frame, ranges, colour):
    """Share of a box (body coordinates on the view's two dims) painted in the colour."""
    a = np.asarray(painting.convert('RGB')).astype(float)
    m = np.asarray(mask, bool)
    box = {d: (float(frame.from_body(d, r[0])), float(frame.from_body(d, r[1]))) for d, r in ranges.items()}
    box = {d: (max(0.0, min(v)), min(1.0, max(v))) for d, v in box.items()}
    rows, cols = _view_box(view, box, painting.size)
    win, wm = a[rows[0]:rows[1], cols[0]:cols[1]], m[rows[0]:rows[1], cols[0]:cols[1]]
    if win.size == 0 or not wm.any():
        return 0.0
    return float((_same_paint(win, colour) & wm).sum() / max(1, wm.sum()))


def match_features(paintings, masks, feats, frames, min_paint=0.3, triple=PRIMARY):
    """Features traced in two views paired along their shared axis, the third view confirming.

    Front and top features pair on width, front and side on height, side and top on depth. The
    third view confirms with a traced feature agreeing on both its dims, or else with the pair's
    paint filling the box the pair defines there. Pairs are taken best first, each feature once."""
    pairs = []

    def part_like(f):
        x0, y0, x1, y1 = f['px_box']
        w, h = x1 - x0, y1 - y0
        return f['share'] <= 0.05 and max(w, h) / max(1, min(w, h)) <= 6 and f['fill'] >= 0.5
    F, S, T = triple
    boxes = {v: [(f, frames[v].box(f)) for f in feats[v] if part_like(f)] for v in triple}
    for a, b in ((F, T), (F, S), (S, T)):
        shared = [d for d in AXES[a] if d in AXES[b]][0]
        c = [v for v in triple if v not in (a, b)][0]
        for fa, ba in boxes[a]:
            for fb, bb in boxes[b]:
                ea = abs(ba[shared][0] - bb[shared][0]) + abs(ba[shared][1] - bb[shared][1])
                if ea > 2 * TOL or np.linalg.norm(fa['colour'] - fb['colour']) > 60:
                    continue
                part = {shared: ((ba[shared][0] + bb[shared][0]) / 2, (ba[shared][1] + bb[shared][1]) / 2)}
                for d in AXES[a]:
                    if d != shared:
                        part[d] = ba[d]
                for d in AXES[b]:
                    if d != shared:
                        part[d] = bb[d]
                ext = [part[d][1] - part[d][0] for d in 'xyz']
                if sum(e > 0.5 for e in ext) >= 2 or min(ext) < 0.01:
                    continue
                want = {d: part[d] for d in AXES[c]}
                conf, score = None, None
                for fc, bc in boxes[c]:
                    ec = sum(abs(bc[d][i] - want[d][i]) for d in AXES[c] for i in (0, 1))
                    if ec <= 4 * TOL and (score is None or ec < score):
                        conf, score = ('feature', fc['id']), ec
                if conf is None:
                    share = _paint_share(paintings[c], masks[c], c, frames[c], want, fa['colour'])
                    if share >= min_paint:
                        conf, score = ('paint', round(share, 2)), 4 * TOL + (1 - share)
                if conf is None:
                    continue
                pairs.append((ea + score, {'views': [a, b, c], 'features': [fa['id'], fb['id']],
                                           'confirmed_by': conf, 'axis': None,
                                           'shape_view': a if fa['fill'] <= fb['fill'] else b,
                                           'box_body': {d: [round(part[d][0], 4), round(part[d][1], 4)] for d in 'xyz'},
                                           'fill': round(min(fa['fill'], fb['fill']), 3),
                                           'colour': [int(x) for x in fa['colour']]}, (a, fa['id']), (b, fb['id'])))
    used, out = set(), []
    for cost, part, ka, kb in sorted(pairs, key=lambda t: t[0]):
        if ka in used or kb in used:
            continue
        used.add(ka)
        used.add(kb)
        out.append(part)
    return out


def complete_repeats(parts, feats, frames, min_group=6):
    """A repeated part (a row of keys): once an instance is confirmed in three views, the other traced
    instances of the same paint and size in the same row are the same part repeated.

    The row runs along the axis on which the instances line up: of the view's two axes, the one
    whose band (the confirmed instance's extent on that axis) catches the most instances is across
    the row. Each copy keeps its own place along the row and takes the confirmed band and depth."""
    out = list(parts)
    for v, fs in feats.items():
        if v not in frames:
            continue
        groups = []
        for f in fs:
            if f['share'] > 0.01:
                continue
            for g in groups:
                if np.linalg.norm(f['colour'] - g[0]['colour']) < 40 and 0.5 < f['share'] / g[0]['share'] < 2:
                    g.append(f)
                    break
            else:
                groups.append([f])
        for g in [g for g in groups if len(g) >= min_group]:
            ids = {f['id'] for f in g}
            boxes = [(f, frames[v].box(f)) for f in g]
            h, w = AXES[v]
            third = [d for d in 'xyz' if d not in AXES[v]][0]
            for p in parts:
                if v not in p.get('views', []) or not any(fid in ids for fid in p.get('features', [])):
                    continue
                pb = p['box_body']

                def in_band(b, axis):
                    mid = (b[axis][0] + b[axis][1]) / 2
                    return pb[axis][0] - TOL / 2 <= mid <= pb[axis][1] + TOL / 2
                counts = {ax: sum(in_band(b, ax) for _, b in boxes) for ax in (h, w)}
                band_axis = max(counts, key=counts.get)
                if counts[band_axis] < 3:
                    continue
                along = w if band_axis == h else h
                for f, b in boxes:
                    if not in_band(b, band_axis):
                        continue
                    new = {band_axis: list(pb[band_axis]), along: [round(b[along][0], 4), round(b[along][1], 4)],
                           third: list(pb[third])}
                    out.append({'views': [v], 'features': [f['id']], 'confirmed_by': ('repeat of', p['features']),
                                'shape_view': v, 'axis': None, 'box_body': new, 'fill': round(f['fill'], 3),
                                'colour': [int(x) for x in f['colour']], 'repeat': True})
    return out


def _iou3(a, b):
    inter, va, vb = 1.0, 1.0, 1.0
    for d in 'xyz':
        lo, hi = max(a[d][0], b[d][0]), min(a[d][1], b[d][1])
        inter *= max(0.0, hi - lo)
        va *= a[d][1] - a[d][0]
        vb *= b[d][1] - b[d][0]
    return inter / max(1e-12, min(va, vb))          # share of the smaller box inside the other


def _merge(parts, limit=0.5):
    """One part per place: of boxes overlapping by more than `limit`, the first (directly
    confirmed before repeated) stays."""
    kept = []
    for p in parts:
        if all(_iou3(p['box_body'], q['box_body']) <= limit for q in kept):
            kept.append(p)
    return kept


def analyse(paintings, masks, backend='auto'):
    """Features in every view, frames, and parts matched along projection lines. Each combination
    of opposite views (front or back, right or left, top or bottom) is read as its own set of three,
    so a part best seen from the left or from behind is confirmed there."""
    from itertools import product
    views = [v for v in ALL_VIEWS if v in paintings and v in masks]
    if not all(v in views for v in PRIMARY):
        return {'error': 'needs front, right and top views'}
    feats, backends = {}, {}
    for v in views:
        feats[v], backends[v] = trace(paintings[v], masks[v], backend)
    frames, registration = frames_for(paintings, masks, feats)
    paired, single = [], []
    for triple in product(('front', 'back'), ('right', 'left'), ('top', 'bottom')):
        if not all(v in views for v in triple):
            continue
        paired += match_features(paintings, masks, feats, frames, triple=triple)
        single += match(paintings, masks, feats, frames, triple=triple)
    parts = list(paired)
    for p in single:                      # parts only one view traces (a knob's circle) add to them
        if not (p.get('arcs', 0) > 0 and p['fill'] < 0.85):
            continue                         # paint alone confirms only a shape, never a rectangle
        parts.append(p)
    parts = _merge(complete_repeats(_merge(parts), feats, frames))
    return {'features': feats, 'frames': frames, 'parts': parts, 'backends': backends,
            'registration': registration, 'views': views}


def sheet(paintings, result, path, size_mm, px_per_mm=2.4, margin=0.12):
    """Third-angle sheet at true scale: top above the front, bottom below it, right side to its right,
    left side to its left, back beyond the right side; the 45-degree mitre between top and right.
    Every painting is warped through the same registration as the boxes, so what is drawn is what
    was matched. Grey: every traced feature outline. Coloured: each part, boxed in every view, with
    its projection lines."""
    from PIL import Image, ImageDraw
    frames, feats, parts = result['frames'], result['features'], result['parts']
    W, D, H = size_mm
    k = px_per_mm
    g = 30 + 2 * margin * max(W, D, H) * k
    L = {'x': W, 'y': D, 'z': H}
    # each view: (horizontal axis, horizontal increases to the right?, vertical axis, increases upward?)
    ORIENT = {'front': ('x', True, 'z', True), 'back': ('x', False, 'z', True),
              'right': ('y', True, 'z', True), 'left': ('y', False, 'z', True),
              'top': ('x', True, 'y', True), 'bottom': ('x', True, 'y', False)}
    fx, fy = g + D * k + g, g + D * k + g
    org = {'front': (fx, fy), 'top': (fx, fy - g - D * k), 'bottom': (fx, fy + H * k + g),
           'right': (fx + W * k + g, fy), 'left': (fx - g - D * k, fy),
           'back': (fx + W * k + g + D * k + g, fy)}
    views = [v for v in result.get('views', PRIMARY) if v in frames]
    Wt = int(org['back'][0] + W * k + g)
    Ht = int(org['bottom'][1] + D * k + g)
    out = Image.new('RGB', (Wt, Ht), 'white')
    dr = ImageDraw.Draw(out)

    def place(v, bh, bv):
        ha, hpos, va, vpos = ORIENT[v]
        ox, oy = org[v]
        x = ox + (bh if hpos else 1 - bh) * L[ha] * k
        y = oy + ((1 - bv) if vpos else bv) * L[va] * k
        return x, y

    for v in views:
        ha, hpos, va, vpos = ORIENT[v]
        fr = frames[v]
        p = np.asarray(paintings[v].convert('RGB'))
        Hh, Ww = p.shape[:2]
        mh, mv = margin * L[ha] * k, margin * L[va] * k
        nx, ny = int(L[ha] * k + 2 * mh), int(L[va] * k + 2 * mv)
        xs = (np.arange(nx) + 0.5 - mh) / (L[ha] * k)
        ys = (np.arange(ny) + 0.5 - mv) / (L[va] * k)
        bh = xs if hpos else 1 - xs
        bv = 1 - ys if vpos else ys
        uh, uv = fr.from_body(ha, bh), fr.from_body(va, bv)

        def pix(dim, u):
            axis, flip = FRAMES[v][dim]
            u = 1 - u if flip else u
            return u * (Ww if axis == 'col' else Hh), axis
        ph, ah = pix(ha, uh)
        pv, av = pix(va, uv)
        if ah == 'col':
            C, R = ph[None, :].repeat(ny, 0), pv[:, None].repeat(nx, 1)
        else:
            R, C = ph[None, :].repeat(ny, 0), pv[:, None].repeat(nx, 1)
        ok = (C >= 0) & (C < Ww) & (R >= 0) & (R < Hh)
        img = np.where(ok[..., None], p[np.clip(R.astype(int), 0, Hh - 1), np.clip(C.astype(int), 0, Ww - 1)], 235)
        tile = Image.blend(Image.fromarray(img.astype(np.uint8)), Image.new('RGB', (nx, ny), 'white'), 0.5)
        ox, oy = org[v]
        out.paste(tile, (int(ox - mh), int(oy - mv)))
        dr.rectangle([ox, oy, ox + L[ha] * k, oy + L[va] * k], outline=(170, 170, 170))
        dr.text((ox, oy - mv - 14), '%s VIEW  (%d x %d mm)' % (v.upper(), round(L[ha]), round(L[va])), fill=(0, 0, 0))
        for f in feats.get(v, []):
            if 'outline' not in f:
                continue
            pts = []
            for x, y, _ in f['outline']:
                wv = _world(v, paintings[v].size, x, y)
                pts.append(place(v, float(fr.to_body(ha, wv[ha])), float(fr.to_body(va, wv[va]))))
            if len(pts) > 2:
                dr.line(pts + [pts[0]], fill=(70, 70, 70), width=1)
    # mitre: the top view's depth turns into the right view's depth
    rx, ty = org['right'][0], org['top'][1]
    dr.line([(rx, ty + D * k), (rx + D * k, ty)], fill=(150, 150, 150), width=1)
    palette = [(220, 30, 30), (30, 110, 220), (20, 150, 60), (200, 110, 0), (150, 40, 180), (0, 150, 160)]

    def dash(p, q, col):
        p, q = np.array(p, float), np.array(q, float)
        n = max(2, int(np.linalg.norm(q - p) / 6))
        for t in range(0, n, 2):
            dr.line([tuple(p + (q - p) * t / n), tuple(p + (q - p) * min(n, t + 1) / n)], fill=col, width=1)
    for i, part in enumerate(parts):
        col = palette[i % len(palette)]
        b = part['box_body']
        for v in views:
            ha, _, va, _ = ORIENT[v]
            p0, p1 = place(v, b[ha][0], b[va][0]), place(v, b[ha][1], b[va][1])
            dr.rectangle([min(p0[0], p1[0]), min(p0[1], p1[1]), max(p0[0], p1[0]), max(p0[1], p1[1])], outline=col, width=2)
        cx, cy, cz = (float(np.mean(b[d])) for d in 'xyz')
        pf = place('front', cx, cz)
        dash(pf, place('top', cx, cy), col)
        dash(pf, place('right', cy, cz), col)
        pt, pr = place('top', cx, cy), place('right', cy, cz)
        turn = (pr[0], pt[1])
        dash(pt, turn, col)
        dash(turn, pr, col)
    dr.text((org['right'][0] + 10, org['top'][1] + 10),
            'Third-angle projection at true scale, %d x %d x %d mm (W x D x H)\n%d parts matched along projection lines.\n'
            'Grey: traced feature outlines. Coloured: one part in every view; dashed: projection lines.'
            % (round(W), round(D), round(H), len(parts)), fill=(0, 0, 0))
    out.save(path)
    return path


def _entity_points(verts, n_arc=12):
    """Closed CAD polyline (x, y, bulge) -> points, each arc sampled as an arc ending on its endpoint."""
    out = []
    V = np.asarray(verts, float)
    for i in range(len(V)):
        x0, y0, b = V[i]
        x1, y1 = V[(i + 1) % len(V)][:2]
        out.append((x0, y0))
        if abs(b) < 1e-9:
            continue
        dx, dy = x1 - x0, y1 - y0
        chord = math.hypot(dx, dy)
        if chord < 1e-9:
            continue
        theta = 4 * math.atan(b)
        h = (chord / 2) * (1 - b * b) / (2 * b)
        nx, ny = -dy / chord, dx / chord
        best = None
        for sgn in (1, -1):
            cx, cy = (x0 + x1) / 2 + sgn * nx * h, (y0 + y1) / 2 + sgn * ny * h
            r = math.hypot(x0 - cx, y0 - cy)
            a0 = math.atan2(y0 - cy, x0 - cx)
            for sw in (theta, -theta):
                err = math.hypot(cx + r * math.cos(a0 + sw) - x1, cy + r * math.sin(a0 + sw) - y1)
                if best is None or err < best[0]:
                    best = (err, cx, cy, r, a0, sw)
        _, cx, cy, r, a0, sw = best
        for t in np.linspace(0, 1, n_arc, endpoint=False)[1:]:
            out.append((cx + r * math.cos(a0 + sw * t), cy + r * math.sin(a0 + sw * t)))
    return out


def feature_images(paintings, feats, destination, scale=3):
    """Stage 2's check image per view: the painting with every traced feature outline (lines and
    arcs), repeated parts in blue, others in red."""
    from PIL import Image, ImageDraw
    from pathlib import Path
    paths = {}
    for v, fs in feats.items():
        img = paintings[v].convert('RGB')
        vis = Image.blend(img, Image.new('RGB', img.size, 'white'), 0.5).resize((img.width * scale, img.height * scale))
        d = ImageDraw.Draw(vis)
        small = [f for f in fs if f['share'] <= 0.01]
        for f in fs:
            if 'outline' not in f:
                continue
            pts = [(x * scale, y * scale) for x, y in _entity_points(f['outline'])]
            rep = f in small and sum(np.linalg.norm(f['colour'] - g['colour']) < 40 for g in small) >= 6
            if len(pts) > 2:
                d.line(pts + [pts[0]], fill=(30, 90, 220) if rep else (210, 30, 30), width=2)
        path = Path(destination) / ('features_%s.png' % v)
        vis.save(path)
        paths[v] = str(path)
    return paths


def summary(result):
    """JSON-safe record of the stage for drawing.json."""
    if 'error' in result:
        return {'error': result['error']}
    feats = result['features']
    return {'views': result['views'],
            'backend': {v: b.get('selected') for v, b in result['backends'].items()},
            'features': {v: [{'id': f['id'], 'share': round(f['share'], 5), 'fill': round(f['fill'], 3),
                              'arcs': f.get('arcs', 0), 'colour': [int(c) for c in f['colour']],
                              'outline_px': f.get('outline')} for f in fs] for v, fs in feats.items()},
            'registration': json_safe(result['registration']),
            'parts': json_safe(result['parts'])}


def json_safe(o):
    if isinstance(o, dict):
        return {str(k): json_safe(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [json_safe(v) for v in o]
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    return o


def rows(parts, tol=TOL, min_instances=4, max_band=0.1, width_ratio=1.5, colour_step=45):
    """Rows of a repeated part (a row of keys): four or more confirmed instances of similar width and
    paint, sharing one thin band on two axes (height and depth, each under max_band of the object)
    and lying apart along the third. Overlapping instances are one; overlapping rows are one (the one
    with more instances stays). Returns [{'along', 'band', 'instances'}] in body coordinates."""
    found = []
    for i, p in enumerate(parts):
        b = p['box_body']
        for along in 'xyz':
            band = [d for d in 'xyz' if d != along]
            if any(b[d][1] - b[d][0] > max_band for d in band):
                continue
            members = [q for q in parts
                       if all(abs(q['box_body'][d][0] - b[d][0]) <= tol and abs(q['box_body'][d][1] - b[d][1]) <= tol for d in band)
                       and np.linalg.norm(np.subtract(q['colour'], p['colour'])) < colour_step]
            widths = [q['box_body'][along][1] - q['box_body'][along][0] for q in members]
            w0 = float(np.median(widths)) if widths else 0
            members = [q for q, w in zip(members, widths) if w0 > 0 and 1 / width_ratio <= w / w0 <= width_ratio]
            # one instance per place along the row
            inst = []
            for q in sorted(members, key=lambda q: q['box_body'][along][0]):
                lo, hi = q['box_body'][along]
                if inst and lo < inst[-1][1] - 0.25 * (hi - lo):
                    inst[-1][1] = max(inst[-1][1], hi)
                else:
                    inst.append([lo, hi])
            if len(inst) < min_instances:
                continue
            lo_b = {d: min(q['box_body'][d][0] for q in members) for d in band}
            hi_b = {d: max(q['box_body'][d][1] for q in members) for d in band}
            if any(hi_b[d] - lo_b[d] > max_band for d in band):
                continue
            found.append({'along': along, 'band': {d: [round(lo_b[d], 4), round(hi_b[d], 4)] for d in band},
                          'instances': [[round(x0, 4), round(x1, 4)] for x0, x1 in inst]})
            break
    out = []
    for r in sorted(found, key=lambda r: -len(r['instances'])):
        def overlaps(q):
            if q['along'] != r['along']:
                return False
            return all(min(r['band'][d][1], q['band'][d][1]) > max(r['band'][d][0], q['band'][d][0]) for d in r['band'])
        if not any(overlaps(q) for q in out):
            out.append(r)
    return out


def row_has_gaps(row, paintings, masks, frames, colour, ratio=0.6, present=0.3, views=None):
    """A row of separate parts: (1) for each of the row's band directions, a view that sees the row
    along its length and across that direction shows the parts' paint on the instances (a key row's
    height in the front view, its depth in the top view); (2) at least one such view shows gaps, the
    paint between instances under `ratio` of the paint on them. A stripe or band fails one or both."""
    along = row['along']
    shown = {d: False for d in row['band']}
    gapped = False
    for v in (views if views is not None else ('front', 'top', 'right', 'back', 'bottom', 'left')):
        if v not in frames or along not in AXES[v]:
            continue
        band_dim = [d for d in AXES[v] if d != along][0]
        fr = frames[v]
        a = np.asarray(paintings[v].convert('RGB')).astype(float)
        m = np.asarray(masks[v], bool)
        lo, hi = row['band'][band_dim]
        blo, bhi = sorted((float(fr.from_body(band_dim, lo)), float(fr.from_body(band_dim, hi))))
        rows_, cols_ = _view_box(v, {band_dim: (max(0.0, blo), min(1.0, bhi)), along: (0.0, 1.0)}, paintings[v].size)
        win, wm = a[rows_[0]:rows_[1], cols_[0]:cols_[1]], m[rows_[0]:rows_[1], cols_[0]:cols_[1]]
        if win.size == 0:
            continue
        if FRAMES[v][along][0] == 'row':
            win, wm = win.transpose(1, 0, 2), wm.T
        prof = (_same_paint(win, colour) & wm).mean(0)
        if FRAMES[v][along][1]:
            prof = prof[::-1]
        n = len(prof)

        def idx(b):
            return int(np.clip(float(fr.from_body(along, b)) * n, 0, n - 1))
        inst = row['instances']
        inside = float(np.mean([prof[idx(x0):idx(x1) + 1].mean() for x0, x1 in inst]))
        if inside >= present:
            shown[band_dim] = True
        gaps = []
        for k in range(len(inst) - 1):
            g0, g1 = idx(inst[k][1]), idx(inst[k + 1][0])
            q = (g1 - g0) // 4                      # the middle half of the gap, away from blurred edges
            if g1 - g0 >= 2:
                gaps.append(prof[g0 + q:g1 - q + 1].mean())
        if gaps and inside >= present and np.mean(gaps) < ratio * inside:
            gapped = True
    return all(shown.values()) and gapped


def validated_rows(result, paintings, masks):
    """Rows of repeated parts that show gaps in every view that sees them along their length."""
    out = []
    hull = visual_hull(masks)
    for r in rows(result['parts']):
        members = [p for p in result['parts']
                   if all(r['band'][d][0] - TOL <= p['box_body'][d][0] and p['box_body'][d][1] <= r['band'][d][1] + TOL
                          for d in r['band'])]
        colour = np.median([p['colour'] for p in members], axis=0) if members else None
        box = dict(r['band'])
        box[r['along']] = [r['instances'][0][0], r['instances'][-1][1]]
        views = [v for v in ALL_VIEWS if v in result['frames'] and sees(v, box, hull)]   # views that can see it
        if colour is not None and row_has_gaps(r, paintings, masks, result['frames'], colour, views=views):
            fl = row_floor(r, paintings, masks, result['frames'], colour, hull)
            if fl is not None and fl < r['band']['z'][0]:
                r['floor'] = round(fl, 4)
            out.append(r)
    return out


# viewing direction of each view: (axis it looks along, the end it looks from: 0 low, 1 high)
VIEWER = {'front': ('y', 0), 'back': ('y', 1), 'right': ('x', 1), 'left': ('x', 0), 'top': ('z', 1), 'bottom': ('z', 0)}


def visual_hull(masks, res=96):
    """A coarse solid from the front, side and top outlines (where all three allow material)."""
    from .rounding import view_masks
    side = masks.get('right') if 'right' in masks else np.asarray(masks['left'])[:, ::-1]
    Fm, Sm, Tm = view_masks(np.asarray(masks['front'], bool), np.asarray(side, bool),
                            np.asarray(masks['top'], bool) if 'top' in masks else None, (res, res, res))
    return Fm[:, None, :] & Sm[None, :, :] & Tm[:, :, None]


def sees(view, box, hull, gap=0.03, limit=0.3):
    """Can this view see a part at box (body coordinates)? Not when material fills more than `limit`
    of the space between the view and the part's near face: the draftsman's visibility rule."""
    axis, end = VIEWER[view]
    n = hull.shape[0]
    idx = {'x': 0, 'y': 1, 'z': 2}
    sl = [slice(None)] * 3
    for d in 'xyz':
        if d == axis:
            continue
        lo, hi = box[d]
        sl[idx[d]] = slice(int(np.clip(lo, 0, 1) * n), max(int(np.clip(lo, 0, 1) * n) + 1, int(np.ceil(np.clip(hi, 0, 1) * n))))
    lo, hi = box[axis]
    if end == 0:
        sl[idx[axis]] = slice(0, max(0, int((np.clip(lo, 0, 1) - gap) * n)))
    else:
        sl[idx[axis]] = slice(min(n, int(np.ceil((np.clip(hi, 0, 1) + gap) * n))), n)
    region = hull[tuple(sl)]
    if region.size == 0:
        return True
    # material between view and part, per line of sight: a line is blocked if it meets material
    lines = region.any(axis=idx[axis])
    return lines.mean() <= limit


def row_floor(row, paintings, masks, frames, colour, hull):
    """How deep the gaps between a row's instances go, read in a view that sees the row along its
    length and across its vertical band (the front view for a key row): below the instances the gap
    columns show other paint (stems, a well) down to where the part's paint returns (the next row) or
    the outline ends. Returns the floor on the band's axis (body coordinates) or None."""
    along = row['along']
    for v in ('front', 'back', 'right', 'left'):
        if v not in frames or along not in AXES[v] or not sees(v, _row_box(row), hull):
            continue
        band_dim = [d for d in AXES[v] if d != along][0]
        if band_dim != 'z':
            continue
        fr = frames[v]
        a = np.asarray(paintings[v].convert('RGB')).astype(float)
        m = np.asarray(masks[v], bool)
        Wp, Hp = paintings[v].size
        same = _same_paint(a, colour) & m
        z0 = row['band']['z'][0]
        floors = []
        inst = row['instances']
        for k in range(len(inst) - 1):
            g0, g1 = inst[k][1], inst[k + 1][0]
            if g1 <= g0:
                continue
            u0, u1 = sorted((float(fr.from_body(along, g0)), float(fr.from_body(along, g1))))
            c0, c1 = int(u0 * Wp), int(np.ceil(u1 * Wp))
            c0, c1 = c0 + (c1 - c0) // 4, c1 - (c1 - c0) // 4        # the middle of the gap
            if c1 <= c0:
                continue
            r_start = int((1 - float(fr.from_body('z', z0))) * Hp)
            col_same = same[:, c0:c1].mean(1)
            col_in = m[:, c0:c1].mean(1)
            r = r_start
            while r < Hp - 1 and col_same[r] < 0.5 and col_in[r] > 0.5:
                r += 1
            floors.append(float(fr.to_body('z', 1 - r / Hp)))
        if floors:
            return float(np.median(floors))
    return None


def _row_box(row):
    box = dict(row['band'])
    box[row['along']] = [row['instances'][0][0], row['instances'][-1][1]]
    return box


def texture_maps(result, samples=141):
    """Where each body position lands in each view, for texture projection.

    Returns {view: {dim: [body positions, view positions]}}: positions normalised over the view's own
    outline box, in the world direction (curve_views' frame). Projecting through this instead of the
    box alone keeps views that are painted with different proportions, or that show a part sticking
    out further, from placing the same feature in two places (a key row or space bar painted twice)."""
    out = {}
    xs = np.linspace(-0.2, 1.2, samples)
    for v, fr in result.get('frames', {}).items():
        out[v] = {}
        for dim in AXES[v]:
            reg = fr.regs.get(dim)
            if reg is None:
                ns = xs
            else:
                c = np.clip(xs, 0, 1)
                ns = reg.to_b(c) + (xs - c)
            out[v][dim] = [[round(float(a), 5) for a in xs], [round(float(b), 5) for b in ns]]
    return out
