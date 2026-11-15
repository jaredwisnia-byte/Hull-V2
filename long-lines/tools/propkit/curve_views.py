"""Seen first: curves that agree across orthographic views decide the construction.

Design: docs/CURVE_RECONSTRUCTION.md, "Seen first, crutch second". Each view is traced
by propkit/curves.py. Here the curves meet:

1. Frames. Every view is normalised to the object's box (its outline's bounding box), using the
   view convention of propkit/hull.py (front: u -> X, v -> 1 - Z; right: u -> Y; top: v -> 1 - Y;
   back and left mirrored). Two views share an axis: front and right share height Z, front and
   top share width X, right and top share depth Y; opposite views share both.
2. Registration and tolerance, measured, never guessed. On a shared axis, the outlines' abrupt
   width changes (breakpoints) are the same steps seen in both views. Matched ones anchor a
   monotone piecewise-linear map between the two views (painted views disagree in proportion
   unevenly), and every comparison happens after that map. The tolerance is the 95th percentile
   of the leave-one-out disagreement left after it (floored at 1.5 pixels of the coarser view);
   with too few anchors, or no gain, the views stay registered by their boxes alone.
3. Agreement. A curve is *consistent* when another view shows a curve with the same extent on
   the shared axis (both ends within tolerance), or, for a curve that is a single coordinate on
   that axis (a line across it), a line across it at the same coordinate. Otherwise it is *seen
   once*: a proposal that cannot decide geometry by itself (paint, or a crease only one view shows).
4. Constructions, each a fact of orthographic projection (not a rule about any kind of object):
   - through: the same curve in opposite views (one mirrored) means nothing changes through
     the depth between them: an extrusion along that direction;
   - cylinder: a circle in one view with two lines along its viewing axis at the circle's
     extreme coordinates in a perpendicular view: a cylinder, hole or boss on that axis;
   - plane: lines across a shared axis at the same coordinate in two views: a face or step at
     that coordinate.
   Every construction lists the curves that decided it.
5. Chance. With hundreds of curves per view and tolerances of a few percent, almost anything
   finds a partner. Every agreement and construction carries the probability that it happened
   by coincidence (n candidates x window, the a-contrario test of propkit/curves.py applied
   across views); only those at or below ALPHA count. A curve whose only partners are likely
   coincidences is 'coincidental', not 'consistent'.

Nothing here reads brightness or guesses what no view shows.
"""

import numpy as np

from . import curves as _curves

# view -> (world axis of u, flip u, world axis of v, flip v, viewing axis); matches hull.py sampling
VIEWS = {
    'front': ('x', False, 'z', True, 'y'),
    'back': ('x', True, 'z', True, 'y'),
    'right': ('y', False, 'z', True, 'x'),
    'left': ('y', True, 'z', True, 'x'),
    'top': ('x', False, 'y', True, 'z'),
    'bottom': ('x', False, 'y', False, 'z'),
}
OPPOSITE = (('front', 'back'), ('right', 'left'), ('top', 'bottom'))
TOL_FLOOR_PX = 1.5
ACROSS = 0.25        # a curve spanning less than this many tolerances on an axis is a coordinate there
MERGE_SAMPLES = 4    # breakpoints this close (of 200 samples) with the same sense are one step
ALPHA = 0.05         # largest chance probability at which an agreement still counts as evidence


def chance(n, t, ends=1):
    """Probability that a random coordinate (ends=1) or interval (ends=2) on a unit axis falls
    within tolerance t of one of n candidates by coincidence: the a-contrario test applied to
    agreement between views. A cluttered view or a loose tolerance makes agreement worthless."""
    return float(min(1.0, n * (2 * t) ** ends))


def axes(view):
    u, _, v, _, _ = VIEWS[view]
    return u, v


def to_world(view, bbox, points):
    """Pixel points of `view` -> dict of normalised world coordinates on the view's two axes."""
    u_axis, u_flip, v_axis, v_flip, _ = VIEWS[view]
    x0, y0, x1, y1 = bbox
    p = np.asarray(points, np.float64)
    u = (p[:, 0] - x0) / max(x1 - x0, 1)
    v = (p[:, 1] - y0) / max(y1 - y0, 1)
    return {u_axis: 1 - u if u_flip else u, v_axis: 1 - v if v_flip else v}


def _profile(mask, bbox, view, axis, samples=200):
    """Outline width perpendicular to `axis` at each normalised position along it."""
    u_axis, u_flip, v_axis, v_flip, _ = VIEWS[view]
    x0, y0, x1, y1 = bbox
    crop = mask[y0:y1, x0:x1]
    if axis == u_axis:
        width = crop.sum(0).astype(float) / max(crop.shape[0], 1)
        flip = u_flip
    else:
        width = crop.sum(1).astype(float) / max(crop.shape[1], 1)
        flip = v_flip
    if flip:
        width = width[::-1]
    pos = (np.arange(len(width)) + 0.5) / len(width)
    s = (np.arange(samples) + 0.5) / samples
    return s, np.interp(s, pos, width)


def breakpoints(s, width, signed=False):
    """Positions where the outline width changes abruptly (local maxima of the change). With
    `signed`, also the sign of each change (+1 the outline widens, -1 it narrows)."""
    dg = np.gradient(width, s)
    g = np.abs(dg)
    level = max(3 * float(np.median(g)), 0.5)
    peaks = [i for i in range(1, len(g) - 1) if g[i] >= level and g[i] >= g[i - 1] and g[i] >= g[i + 1]]
    # one step can show as two neighbouring peaks (a step two pixel rows tall): keep the stronger
    kept = []
    for i in peaks:
        if kept and i - kept[-1] <= MERGE_SAMPLES and np.sign(dg[i]) == np.sign(dg[kept[-1]]):
            if g[i] > g[kept[-1]]:
                kept[-1] = i
        else:
            kept.append(i)
    peaks = kept
    if signed:
        return s[peaks], np.sign(dg[peaks])
    return s[peaks]


MATCH_WINDOW = 0.1   # largest normalised disagreement at which two breakpoints can be one feature
SLOPE = (0.5, 2.0)   # a view's stretch between anchors stays within this (no folding, no collapse)


def match_breakpoints(pa, sa, pb, sb, window=MATCH_WINDOW):
    """Order-preserving one-to-one matches between breakpoints of two views on a shared axis.

    A pair counts only if both change the outline the same way (both widen or both narrow) and
    each is the other's nearest such breakpoint (mutual nearest neighbours, within `window`).
    The matches are then made monotone (the longest chain increasing in both views) so that one
    stray pair cannot fold the map. Returns [(position in a, position in b), ...] sorted."""
    pairs = []
    for i, (x, s) in enumerate(zip(pa, sa)):
        cand = [j for j in range(len(pb)) if sb[j] == s]
        if not cand:
            continue
        j = min(cand, key=lambda j: abs(pb[j] - x))
        if abs(pb[j] - x) > window:
            continue
        back = [k for k in range(len(pa)) if sa[k] == sb[j]]
        if min(back, key=lambda k: abs(pa[k] - pb[j])) == i:
            pairs.append((float(x), float(pb[j])))
    pairs.sort()
    # longest chain increasing in b (pairs are already increasing in a); O(n^2) is fine here
    best, prev = [1] * len(pairs), [-1] * len(pairs)
    for i in range(len(pairs)):
        for k in range(i):
            if pairs[k][1] < pairs[i][1] and pairs[k][0] < pairs[i][0] and best[k] + 1 > best[i]:
                best[i], prev[i] = best[k] + 1, k
    if not pairs:
        return []
    i = int(np.argmax(best))
    chain = []
    while i >= 0:
        chain.append(pairs[i])
        i = prev[i]
    return chain[::-1]


def _anchors(pairs):
    """Monotone anchors (b -> a) including the box ends, keeping each stretch within SLOPE."""
    xs_b, xs_a = [0.0], [0.0]
    for xa, xb in pairs:
        if not (xs_b[-1] < xb < 1 and xs_a[-1] < xa < 1):
            continue
        slope = (xa - xs_a[-1]) / (xb - xs_b[-1])
        if SLOPE[0] <= slope <= SLOPE[1]:
            xs_b.append(xb)
            xs_a.append(xa)
    xs_b.append(1.0)
    xs_a.append(1.0)
    # the last stretch must also respect SLOPE; drop interior anchors from the end until it does
    while len(xs_b) > 2:
        slope = (xs_a[-1] - xs_a[-2]) / (xs_b[-1] - xs_b[-2])
        if SLOPE[0] <= slope <= SLOPE[1]:
            break
        del xs_b[-2], xs_a[-2]
    return xs_b, xs_a


class Registration:
    """Map between two views on one shared axis: b's normalised coordinate -> a's.

    The views are painted, not photographed through one lens, so their proportions disagree along
    an axis by a few percent, unevenly (the camera's views by 9-15 %). Normalising each view to
    its outline box aligns only the ends. Matched outline breakpoints (the same step in the
    outline, seen in both views) are anchors of a monotone piecewise-linear map, the same idea as
    the drawing stage's view reconciliation. The tolerance is what is left after the map,
    measured honestly: each anchor is predicted from a map built without it (leave-one-out), so
    a map that only memorises its anchors does not look precise."""

    def __init__(self, pairs, floor, rigid_tolerance):
        self.pairs = pairs
        self.xs_b, self.xs_a = _anchors(pairs)
        self.floor = floor
        residuals = []
        for xa, xb in pairs:
            rest = [p for p in pairs if p != (xa, xb)]
            fb, fa = _anchors(rest)
            residuals.append(abs(float(np.interp(xb, fb, fa)) - xa))
        self.residuals = residuals
        learned = (max(floor, float(np.percentile(residuals, 95)))
                   if len(self.xs_b) - 2 >= 2 and len(residuals) >= 3 else None)
        if learned is not None and learned < rigid_tolerance:
            self.tolerance = learned
            self.piecewise = True
        else:                                  # too few anchors, or no better than rigid: stay rigid                                  # too few anchors to learn a map: stay rigid
            self.xs_b, self.xs_a = [0.0, 1.0], [0.0, 1.0]
            self.tolerance = rigid_tolerance
            self.piecewise = False

    def to_a(self, values):
        return np.interp(np.asarray(values, np.float64), self.xs_b, self.xs_a)

    def to_b(self, values):
        return np.interp(np.asarray(values, np.float64), self.xs_a, self.xs_b)

    def summary(self):
        return {'tolerance': round(self.tolerance, 5), 'floor': round(self.floor, 5),
                'piecewise': self.piecewise, 'anchors': len(self.xs_b) - 2,
                'matched_breakpoints': len(self.pairs)}


def registration(traces, masks, a, b, axis):
    """Register views a and b on their shared `axis`; returns a Registration (b -> a)."""
    pa, sa = breakpoints(*_profile(masks[a], traces[a]['bbox'], a, axis), signed=True)
    pb, sb = breakpoints(*_profile(masks[b], traces[b]['bbox'], b, axis), signed=True)
    px = []
    for v in (a, b):
        x0, y0, x1, y1 = traces[v]['bbox']
        u_axis, _, _, _, _ = VIEWS[v]
        px.append((x1 - x0) if axis == u_axis else (y1 - y0))
    floor = TOL_FLOOR_PX / max(min(px), 1)
    # rigid tolerance, as before: nearest breakpoint disagreement with only the box ends aligned
    d = [float(np.min(np.abs(pb - x))) for x in pa if len(pb)]
    d = [x for x in d if x <= MATCH_WINDOW]
    rigid = max(floor, float(np.percentile(d, 95))) if d else max(floor, 0.02)
    reg = Registration(match_breakpoints(pa, sa, pb, sb), floor, rigid)
    reg.rigid_tolerance = rigid
    return reg


def analyse(images):
    """images: {view: RGB array}. Returns traces, tolerances, per-curve agreement, constructions."""
    traces, masks, world = {}, {}, {}
    for view, image in sorted(images.items()):
        if view not in VIEWS:
            continue
        traces[view] = _curves.trace(image)
        masks[view] = _curves.object_mask(image)
        world[view] = [to_world(view, traces[view]['bbox'], c['points']) for c in traces[view]['curves']]
    names = sorted(traces)
    regs = {}
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            for axis in sorted(set(axes(a)) & set(axes(b))):
                regs[(a, b, axis)] = registration(traces, masks, a, b, axis)
    tol, into = _registered(regs)
    rigid = {k: r.rigid_tolerance for k, r in regs.items()}
    tolerances = {k: dict(r.summary(), rigid_tolerance=round(rigid[k], 5)) for k, r in regs.items()}

    # candidates per view and axis, for the chance of a coincidental match
    def is_across(view, m, axis, t):
        w = world[view][m][axis]
        return float(np.ptp(w)) < ACROSS * 4 * t
    # 3. agreement
    for a in names:
        for k, c in enumerate(traces[a]['curves']):
            support = []
            for axis in axes(a):
                ca = world[a][k][axis]
                lo, hi = float(ca.min()), float(ca.max())
                for b in names:
                    if b == a or axis not in axes(b):
                        continue
                    t = tol(a, b, axis)
                    n_across = sum(is_across(b, m, axis, t) for m in range(len(traces[b]['curves'])))
                    n_extent = len(traces[b]['curves']) - n_across
                    p_coord, p_ext = chance(n_across, t), chance(n_extent, t, ends=2)
                    for m, d in enumerate(traces[b]['curves']):
                        cb = into(a, b, axis, world[b][m][axis])
                        blo, bhi = float(cb.min()), float(cb.max())
                        if hi - lo < ACROSS * 4 * t:          # a coordinate on this axis
                            if bhi - blo < ACROSS * 4 * t and abs((lo + hi) / 2 - (blo + bhi) / 2) <= t:
                                support.append({'view': b, 'curve': m, 'axis': axis, 'as': 'coordinate',
                                                'residual_tol': round(abs((lo + hi - blo - bhi) / 2) / t, 3),
                                                'p_chance': round(p_coord, 4)})
                        elif lo <= t and hi >= 1 - t:
                            continue                      # spans the whole object: says nothing
                        elif abs(lo - blo) <= t and abs(hi - bhi) <= t:
                            support.append({'view': b, 'curve': m, 'axis': axis, 'as': 'extent',
                                            'residual_tol': round(max(abs(lo - blo), abs(hi - bhi)) / t, 3),
                                            'p_chance': round(p_ext, 4)})
            evidence = [x for x in support if x['p_chance'] <= ALPHA]
            c['support'] = support
            c['support_views'] = sorted({x['view'] for x in evidence})
            c['tier'] = 'consistent' if evidence else ('coincidental' if support else 'seen_once')
            if c['kind'] in ('interior', 'closed'):
                c['reading'] = (('part_boundary' if c['closed'] else 'crease') if evidence
                                else 'decoration_or_unconfirmed')
            else:
                c['reading'] = 'outline'
    constructions = (_through(traces, world, tol, into) + _cylinders(traces, world, tol, into)
                     + _planes(traces, world, tol, into))
    return {'traces': traces,
            'tolerances': {'%s|%s|%s' % k: v for k, v in sorted(tolerances.items())},
            'constructions': constructions,
            'counts': {v: {'curves': len(traces[v]['curves']),
                           'consistent': sum(c['tier'] == 'consistent' for c in traces[v]['curves']),
                       'coincidental': sum(c['tier'] == 'coincidental' for c in traces[v]['curves'])}
                       for v in names}}


def _registered(regs):
    """tol(a, b, axis) and into(a, b, axis, values): b's coordinates in a's frame."""
    def tol(a, b, axis):
        return (regs.get((a, b, axis)) or regs[(b, a, axis)]).tolerance

    def into(a, b, axis, values):
        if (a, b, axis) in regs:
            return regs[(a, b, axis)].to_a(values)
        return regs[(b, a, axis)].to_b(values)
    return tol, into


def _identity_into(a, b, axis, values):
    return np.asarray(values, np.float64)


def _through(traces, world, tol, into=_identity_into, max_mean=1.0):
    """Same curve in opposite views (the far view mirrored by its frame): nothing changes in between."""
    out = []
    for a, b in OPPOSITE:
        if a not in traces or b not in traces:
            continue
        ua, va = axes(a)
        ta, tb = tol(a, b, ua), tol(a, b, va)
        n_b = sum(d['kind'] != 'outline' for d in traces[b]['curves'])
        p = float(min(1.0, n_b * (2 * ta) * (2 * tb)))    # a random curve start lands on one by chance
        if p > ALPHA:
            continue
        for k, c in enumerate(traces[a]['curves']):
            if c['kind'] == 'outline':
                continue
            pa = np.column_stack([world[a][k][ua], world[a][k][va]])
            best = None
            for m, d in enumerate(traces[b]['curves']):
                if d['kind'] == 'outline':
                    continue
                pb = np.column_stack([into(a, b, ua, world[b][m][ua]), into(a, b, va, world[b][m][va])])
                if abs(pa[:, 0].min() - pb[:, 0].min()) > ta or abs(pa[:, 1].min() - pb[:, 1].min()) > tb:
                    continue
                dist = np.hypot((pa[:, None, 0] - pb[None, :, 0]) / ta, (pa[:, None, 1] - pb[None, :, 1]) / tb)
                mean = float(np.mean(dist.min(1)))
                if mean <= max_mean and (best is None or mean < best[0]):
                    best = (mean, m)
            if best is not None:
                out.append({'construction': 'through', 'direction': VIEWS[a][4], 'views': [a, b],
                            'curves': [[a, k], [b, best[1]]], 'mean_residual_tol': round(best[0], 3),
                            'curve_type': c['type'], 'p_chance': round(p, 4)})
    return out


def _cylinders(traces, world, tol, into=_identity_into):
    """A circle in one view and two lines along its viewing axis at its extreme coordinates."""
    out = []
    for a in traces:
        n = VIEWS[a][4]
        for k, c in enumerate(traces[a]['curves']):
            round_ = c['type'] == 'circle' or (c['type'] == 'ellipse' and min(c['axes']) / max(c['axes']) >= 0.85)
            if not round_:
                continue
            for s in axes(a):
                lo, hi = float(world[a][k][s].min()), float(world[a][k][s].max())
                for b in traces:
                    if b == a or s not in axes(b) or n not in axes(b):
                        continue
                    t = tol(a, b, s)
                    edges, along = {}, 0
                    for m, d in enumerate(traces[b]['curves']):
                        if d['type'] != 'line':
                            continue
                        ws, wn = into(a, b, s, world[b][m][s]), world[b][m][n]
                        if np.ptp(ws) > ACROSS * 4 * t or np.ptp(wn) < 4 * t:
                            continue                      # must run along the viewing axis n
                        along += 1
                        x = float(ws.mean())
                        for side, target in (('low', lo), ('high', hi)):
                            if abs(x - target) <= t:
                                edges.setdefault(side, []).append((m, float(wn.min()), float(wn.max())))
                    p = chance(along, t) ** 2                 # both edges placed by coincidence
                    if 'low' in edges and 'high' in edges and p <= ALPHA:
                        (m1, a1, b1), (m2, a2, b2) = edges['low'][0], edges['high'][0]
                        out.append({'construction': 'cylinder', 'axis': n, 'views': [a, b], 'p_chance': round(p, 4),
                                    'curves': [[a, k], [b, m1], [b, m2]],
                                    'center_' + s: round((lo + hi) / 2, 4), 'diameter_' + s: round(hi - lo, 4),
                                    'extent_' + n: [round(max(a1, a2), 4), round(min(b1, b2), 4)]})
    return out


def _planes(traces, world, tol, into=_identity_into):
    """Lines across a shared axis at the same coordinate in two views: a face or step there."""
    out, seen = [], set()
    names = sorted(traces)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            for s in sorted(set(axes(a)) & set(axes(b))):
                t = tol(a, b, s)
                n_b = sum(d['type'] == 'line' and d['kind'] != 'outline' and
                          float(np.ptp(world[b][m][s])) <= ACROSS * 4 * t
                          for m, d in enumerate(traces[b]['curves']))
                p = chance(n_b, t)
                if p > ALPHA:
                    continue
                for k, c in enumerate(traces[a]['curves']):
                    if c['type'] != 'line' or c['kind'] == 'outline':
                        continue
                    wa = world[a][k][s]
                    if np.ptp(wa) > ACROSS * 4 * t:
                        continue
                    for m, d in enumerate(traces[b]['curves']):
                        if d['type'] != 'line' or d['kind'] == 'outline':
                            continue
                        wb = into(a, b, s, world[b][m][s])
                        if np.ptp(wb) > ACROSS * 4 * t or abs(float(wa.mean() - wb.mean())) > t:
                            continue
                        key = (s, round(float(wa.mean()) / t))
                        if key in seen:
                            continue
                        seen.add(key)
                        out.append({'construction': 'plane', 'axis': s, 'at': round(float((wa.mean() + wb.mean()) / 2), 4),
                                    'views': [a, b], 'curves': [[a, k], [b, m]], 'p_chance': round(p, 4)})
    return out


def overlay(images, result, path, height=320):
    """One row of views: consistent curves green, seen-once grey, curves that decided a
    construction thick blue."""
    from PIL import Image, ImageDraw
    decided = {(v, k) for c in result['constructions'] for v, k in c['curves']}
    tiles = []
    for view in sorted(result['traces']):
        base = Image.fromarray(np.asarray(images[view])[..., :3].astype(np.uint8)).convert('RGB')
        scale = height / base.height
        im = base.resize((max(1, int(base.width * scale)), height))
        im = Image.blend(im, Image.new('RGB', im.size, (255, 255, 255)), 0.5)
        d = ImageDraw.Draw(im)
        for k, c in enumerate(result['traces'][view]['curves']):
            pts = [tuple(np.multiply(p, scale)) for p in c['points']]
            if (view, k) in decided:
                d.line(pts, fill=(30, 80, 220), width=4)
            elif c.get('tier') == 'consistent':
                d.line(pts, fill=(20, 150, 60), width=2)
            else:
                d.line(pts, fill=(150, 150, 150), width=1)
        d.text((4, 4), view, fill=(0, 0, 0))
        tiles.append(im)
    w = sum(t.width for t in tiles) + 8 * (len(tiles) - 1)
    sheet = Image.new('RGB', (w, height), 'white')
    x = 0
    for t in tiles:
        sheet.paste(t, (x, 0))
        x += t.width + 8
    sheet.save(path)
