"""Seen first: curves that agree across orthographic views decide the construction.

Design: long-lines/docs/CURVE_RECONSTRUCTION.md, "Seen first, crutch second". Each view is traced
by propkit/curves.py. Here the curves meet:

1. Frames. Every view is normalised to the object's box (its outline's bounding box), using the
   view convention of propkit/hull.py (front: u -> X, v -> 1 - Z; right: u -> Y; top: v -> 1 - Y;
   back and left mirrored). Two views share an axis: front and right share height Z, front and
   top share width X, right and top share depth Y; opposite views share both.
2. Tolerance, measured, never guessed. On a shared axis, the outlines' abrupt width changes
   (breakpoints) must coincide in both views. The 95th percentile of their disagreement is the
   registration tolerance for that pair of views (floored at 1.5 pixels of the coarser view).
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


def breakpoints(s, width):
    """Positions where the outline width changes abruptly (local maxima of the change)."""
    g = np.abs(np.gradient(width, s))
    level = max(3 * float(np.median(g)), 0.5)
    peaks = [i for i in range(1, len(g) - 1) if g[i] >= level and g[i] >= g[i - 1] and g[i] >= g[i + 1]]
    return s[peaks]


def registration(traces, masks, a, b, axis):
    """Measured tolerance (normalised) between views a and b on their shared `axis`."""
    pa = breakpoints(*_profile(masks[a], traces[a]['bbox'], a, axis))
    pb = breakpoints(*_profile(masks[b], traces[b]['bbox'], b, axis))
    px = []
    for v in (a, b):
        x0, y0, x1, y1 = traces[v]['bbox']
        u_axis, _, _, _, _ = VIEWS[v]
        px.append((x1 - x0) if axis == u_axis else (y1 - y0))
    floor = TOL_FLOOR_PX / max(min(px), 1)
    d = [float(np.min(np.abs(pb - x))) for x in pa if len(pb)]
    d = [x for x in d if x <= 0.1]
    tol = max(floor, float(np.percentile(d, 95))) if d else max(floor, 0.02)
    return {'tolerance': round(tol, 5), 'matched_breakpoints': len(d), 'floor': round(floor, 5)}


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
    tolerances = {}
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            for axis in sorted(set(axes(a)) & set(axes(b))):
                tolerances[(a, b, axis)] = registration(traces, masks, a, b, axis)

    def tol(a, b, axis):
        key = (a, b, axis) if (a, b, axis) in tolerances else (b, a, axis)
        return tolerances[key]['tolerance']

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
                        cb = world[b][m][axis]
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
    constructions = _through(traces, world, tol) + _cylinders(traces, world, tol) + _planes(traces, world, tol)
    return {'traces': traces,
            'tolerances': {'%s|%s|%s' % k: v for k, v in sorted(tolerances.items())},
            'constructions': constructions,
            'counts': {v: {'curves': len(traces[v]['curves']),
                           'consistent': sum(c['tier'] == 'consistent' for c in traces[v]['curves']),
                       'coincidental': sum(c['tier'] == 'coincidental' for c in traces[v]['curves'])}
                       for v in names}}


def _through(traces, world, tol, max_mean=1.0):
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
                pb = np.column_stack([world[b][m][ua], world[b][m][va]])
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


def _cylinders(traces, world, tol):
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
                        ws, wn = world[b][m][s], world[b][m][n]
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


def _planes(traces, world, tol):
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
                        wb = world[b][m][s]
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
