"""Engineering export: a true CAD solid built from the drawing, and a factory drawing of it.

Open source, OpenCascade through build123d. The solid is made the way a CAD designer would
make it from three orthographic sketches: each drawn profile (its lines and arcs exactly) is
extruded through the part along its view axis and the three extrusions are intersected; where
the drawing found a round end view, the part inside that circle is replaced by a loft of
ellipses sized at stations along the axis from the other two profiles. The result is a B-rep
(exact surfaces, not triangles) that any CAD package opens: STEP for tooling, STL for printing.

The drawing of that solid is a real hidden-line projection (OpenCascade HLR): visible edges
continuous, hidden edges dashed, an isometric view, sections through the middle with hatching,
overall and feature dimensions, and the measured physical properties (volume, surface area,
centre of mass, mass for a stated material) in the title block.

The sizes are the drawing stage's: estimates at intake's scale, stated on every sheet. Wall
thickness, internals and tolerances cannot be seen on a reference sheet and are marked as such.
"""
import datetime
import json
import math
from pathlib import Path

import numpy as np

MATERIALS = {'ABS': 1.04, 'PP': 0.90, 'steel': 7.85, 'aluminium': 2.70, 'wood': 0.60}
SPAN = {'front': ('width', 'height'), 'back': ('width', 'height'), 'right': ('depth', 'height'),
        'left': ('depth', 'height'), 'top': ('width', 'depth'), 'bottom': ('width', 'depth')}


def _profile_mm(record, view, vertices=None):
    """(u, v, bulge) in mm in the view's drawing plane (v up), bulge sign for v up."""
    prof = record['profiles'][view]
    w, h = prof['image_px']
    size = {k: v * 1000 for k, v in record['size_m'].items()}
    su, sv = size[SPAN[view][0]] / w, size[SPAN[view][1]] / h
    if vertices is None:
        vertices = prof['vertices_px']
    return [(x * su, (h - y) * sv, -b) for x, y, b in vertices]


def _to3d(view, u, v, size):
    W, D, H = size['width'], size['depth'], size['height']
    return {'front': (u, 0.0, v), 'back': (W - u, 0.0, v), 'right': (0.0, u, v), 'left': (0.0, D - u, v),
            'top': (u, v, 0.0), 'bottom': (u, D - v, 0.0)}[view]


def _profile_wire(record, view, size, vertices):
    from build123d import Edge, Wire, Vector
    pts = _profile_mm(record, view, vertices)
    edges = []
    n = len(pts)
    for i in range(n):
        u0, v0, b = pts[i]
        u1, v1, _ = pts[(i + 1) % n]
        if math.hypot(u1 - u0, v1 - v0) < 1e-4:
            continue
        p0, p1 = Vector(*_to3d(view, u0, v0, size)), Vector(*_to3d(view, u1, v1, size))
        if abs(b) < 1e-6:
            edges.append(Edge.make_line(p0, p1))
        else:
            sweep = 4 * math.atan(b)
            chord = np.array([u1 - u0, v1 - v0])
            L = np.linalg.norm(chord)
            r = L / (2 * math.sin(abs(sweep) / 2))
            mid = np.array([(u0 + u1) / 2, (v0 + v1) / 2])
            nrm = np.array([-chord[1], chord[0]]) / L
            # the arc's middle point: sagitta from the chord, on the side the bulge says
            sag = r - r * math.cos(abs(sweep) / 2)
            pm = mid - nrm * sag * (1 if sweep > 0 else -1)
            edges.append(Edge.make_three_point_arc(p0, Vector(*_to3d(view, pm[0], pm[1], size)), p1))
    return Wire(edges)


def _face(record, view, size):
    from build123d import Face
    profile = record['profiles'][view]
    outer = _profile_wire(record, view, size, profile['vertices_px'])
    inner = [_profile_wire(record, view, size, vertices) for vertices in profile.get('openings', [])]
    return Face(outer, inner)


def _extents(mask, along_cols, lo, hi, stations):
    """For each station (0..1 along the mask's columns, or rows), the [min, max] (0..1) of the
    mask across it, limited to [lo, hi] (0..1); NaN where empty."""
    m = mask if along_cols else mask.T
    h, w = m.shape
    out = np.full((len(stations), 2), np.nan)
    for k, t in enumerate(stations):
        c = min(w - 1, max(0, int(t * w)))
        rows = np.nonzero(m[:, c])[0] / h
        rows = rows[(rows >= lo) & (rows <= hi)]
        if len(rows):
            out[k] = rows.min(), rows.max() + 1.0 / h
    return out


def build_solid(record, masks):
    """The CAD solid (build123d Part) in mm, frame: x right, y front->back, z up, corner at 0."""
    from build123d import extrude, Vector, Solid, Wire, Plane, Cylinder, Location, Axis
    size = {k: v * 1000 for k, v in record['size_m'].items()}
    W, D, H = size['width'], size['depth'], size['height']
    picks = [('front', 'back', (0, 1, 0), D), ('right', 'left', (1, 0, 0), W), ('top', 'bottom', (0, 0, 1), H)]
    solid = None
    used = []
    bodies = {}
    for a, b, direction, depth in picks:
        view = a if a in record['profiles'] else (b if b in record['profiles'] else None)
        if view is None:
            continue
        f = _face(record, view, size)
        body = extrude(f, amount=depth, dir=direction)
        bodies[a] = body
        solid = body if solid is None else solid & body
        used.append(view)
    report = {'profiles_used': used, 'round_lofts': [], 'opposite_profiles': []}
    # Opposed profiles carry independent traced constraints. A contradiction is
    # reported rather than silently sacrificing an already supported outline.
    for a, b, direction, depth in picks:
        if a not in record['profiles'] or b not in record['profiles']:
            continue
        body = extrude(_face(record, b, size), amount=depth, dir=direction)
        candidate = solid & body
        accepted, detail = _replacement_check(solid, candidate, record)
        item = {'view': b, **detail}
        if accepted:
            solid = candidate
            bodies[a] = bodies[a] & body
            used.append(b)
        else:
            item['skipped'] = 'opposed traced profiles conflict: ' + detail['reason']
        report['opposite_profiles'].append(item)
    extruded = solid
    measured_axes = {axis for axis, parts in
                     ((record.get('roundness') or {}).get('exponents') or {}).items() if parts}
    for rs in record.get('round_sections', []):
        if rs['axis'] in measured_axes:
            report['round_lofts'].append({'axis': rs['axis'],
                'skipped': 'measured sections supersede the circular end-view approximation'})
            continue
        if rs['axis'] != 'y' or 'top' not in masks or not ({'right', 'left'} & set(masks)):
            continue
        cu, cz = rs['center_m'][0] * 1000, rs['center_m'][1] * 1000
        r = rs['radius_m'] * 1000
        side = masks['right'] if 'right' in masks else masks['left'][:, ::-1]
        top = masks['top']
        st = np.linspace(0.0, 1.0, 41)
        # side view: columns = y (front->back), rows = z (top->bottom)
        zext = _extents(side, True, 1 - (cz + r) / H, 1 - (cz - r) / H, st)
        # top view: rows = y (back at row 0), columns = x
        xext = _extents(top[::-1, :], False, (cu - r) / W, (cu + r) / W, st)
        sections = []
        for k, t in enumerate(st):
            if np.isnan(zext[k, 0]) or np.isnan(xext[k, 0]):
                continue
            z0, z1 = (1 - zext[k, 1]) * H, (1 - zext[k, 0]) * H
            x0, x1 = xext[k, 0] * W, xext[k, 1] * W
            rx, rz = (x1 - x0) / 2, (z1 - z0) / 2
            if rx < 0.5 or rz < 0.5:
                continue
            sections.append((t * D, (x0 + x1) / 2, (z0 + z1) / 2, rx, rz))
        if len(sections) < 3:
            continue
        # smooth the stations so the lofted surface is fair (no painted wobble)
        arr = np.array(sections)
        from scipy.ndimage import gaussian_filter1d
        arr[:, 1:] = gaussian_filter1d(arr[:, 1:], 1.2, axis=0, mode='nearest')
        wires = []
        keep = list(range(0, len(arr), 2)) + ([len(arr) - 1] if (len(arr) - 1) % 2 else [])
        for y, xc, zc, rx, rz in arr[keep]:
            # one orientation for every station, so the loft's seam runs straight along the part
            pl = Plane(origin=(xc, y, zc), x_dir=(1, 0, 0), z_dir=(0, 1, 0))
            wires.append(Wire.make_ellipse(rx, rz, pl))
        try:
            loft = Solid.make_loft(wires, ruled=False)
            y0, y1 = arr[0, 0], arr[-1, 0]
            cyl = Cylinder(r * 1.03, y1 - y0, rotation=(90, 0, 0)).moved(Location((cu, (y0 + y1) / 2, cz)))
            # inside the circle the loft replaces the plan-view extrusion it encodes; only the
            # front and side profiles still trim it (no slivers where two encodings disagree)
            trim = bodies.get('front')
            if 'right' in bodies:
                trim = bodies['right'] if trim is None else trim & bodies['right']
            inside = (trim & cyl & loft) if trim is not None else (cyl & loft)
            candidate = (solid - cyl) + inside
            accepted, detail = _replacement_check(solid, candidate, record)
            item = {'axis': 'y', 'stations': len(wires), 'radius_mm': round(r, 1), **detail}
            if accepted:
                solid = candidate
            else:
                item['skipped'] = detail['reason']
            report['round_lofts'].append(item)
        except Exception as exc:          # a failed loft keeps the extruded solid, and says so
            report['round_lofts'].append({'axis': 'y', 'failed': str(exc)})
    # measured round parts (propkit/rounding.py): each part is lofted through superellipse
    # sections at its own stations and replaces the square-cornered extrusion inside its box
    section_cell = _section_cell_mm(record)
    for axis, parts in ((record.get('roundness') or {}).get('exponents') or {}).items():
        for part in parts or []:
            try:
                lofted = _round_part(axis, part, size, section_cell)
            except Exception as exc:
                report.setdefault('round_parts', []).append({'axis': axis, 'n': part['n'],
                    'box': part['box'], 'failed': str(exc)})
                continue
            if lofted is None:
                report.setdefault('round_parts', []).append({'axis': axis, 'n': part['n'],
                    'skipped': 'fewer than three valid section stations'})
                continue
            slab, loft, prism_volume = lofted
            try:
                here = solid & slab
                if here.volume <= 1e-6:
                    report.setdefault('round_parts', []).append({'axis': axis, 'n': part['n'],
                        'skipped': 'no solid material in the measured section slab'})
                    continue
                # only a part that is alone in its box is replaced (other material in the box
                # would be cut by the loft); otherwise the extrusion stands and says so
                if here.volume > 1.3 * prism_volume:
                    report.setdefault('round_parts', []).append({
                        'axis': axis, 'n': part['n'], 'skipped': 'other material inside its box'})
                    continue
                inside = here & loft
                if inside.volume <= 1e-6:
                    report.setdefault('round_parts', []).append({'axis': axis, 'n': part['n'],
                        'skipped': 'measured loft does not intersect local material'})
                    continue
                candidate = ((solid - slab) + inside).clean()
                accepted, detail = _replacement_check(solid, candidate, record)
                removed = float(solid.volume - candidate.volume)
                epsilon = max(1e-6, abs(float(solid.volume)) * 1e-9)
                detail.update(volume_removed_mm3=removed, volume_epsilon_mm3=epsilon)
                if removed <= epsilon:
                    report.setdefault('round_parts', []).append({
                        'axis': axis, 'n': part['n'], 'box': part['box'], **detail,
                        'skipped': ('no measurable volume removed' if removed >= -epsilon else
                                    'subtractive round part would add material')})
                    continue
                if not accepted:
                    report.setdefault('round_parts', []).append({
                        'axis': axis, 'n': part['n'], 'skipped': detail['reason'], **detail})
                    continue
                sections = _mid_slab_sections(here, inside, slab, axis)
                solid = candidate
                report.setdefault('round_parts', []).append({'axis': axis, 'n': part['n'],
                    'box': [round(v, 3) for v in part['box']],
                    'section_cell_mm': section_cell, 'mid_slab_section': sections, **detail})
            except Exception as exc:
                report.setdefault('round_parts', []).append({'axis': axis, 'n': part['n'],
                    'box': part['box'], 'failed': str(exc)})
    # local features (propkit/features.py): a bump is as wide as the painting shows it
    from build123d import Box, Location
    scale = {'x': W, 'y': D, 'z': H}
    for f in record.get('features', []):
        if not f.get('keep'):
            continue
        along_dim = {'z': 'z', 'x': 'x', 'y': 'y'}[f['axis']]
        rng = {d: (0.0, scale[d]) for d in 'xyz'}
        rng[along_dim] = (f['along'][0] * scale[along_dim], f['along'][1] * scale[along_dim])
        bd = f['bump_dim']
        cut = f['cut'] * scale[bd]
        beyond = (cut, scale[bd]) if f['outward'] > 0 else (0.0, cut)
        keep_lo, keep_hi = f['keep'][0] * scale[f['width_dim']], f['keep'][1] * scale[f['width_dim']]

        def box(r):
            dims = [max(0.05, r[d][1] - r[d][0]) for d in 'xyz']
            return Box(*dims).moved(Location(tuple((r[d][0] + r[d][1]) / 2 for d in 'xyz')))
        try:
            band = dict(rng, **{bd: beyond})
            bump = extruded & box(dict(band, **{f['width_dim']: (keep_lo, keep_hi)}))
            cutters = [box(dict(band, **{f['width_dim']: (0.0, keep_lo)})),
                       box(dict(band, **{f['width_dim']: (keep_hi, scale[f['width_dim']])}))]
            candidate = solid
            for c in cutters:
                candidate = candidate - c
            candidate = candidate + bump
            accepted, detail = _replacement_check(solid, candidate, record)
            if not accepted:
                report.setdefault('features', []).append({'edge': f['edge'],
                    'skipped': detail['reason'], **detail})
                continue
            solid = candidate
            report.setdefault('features', []).append({'edge': f['edge'], 'axis': f['axis'],
                'width_mm': round(keep_hi - keep_lo, 1), **detail})
        except Exception as exc:
            report.setdefault('features', []).append({'edge': f['edge'], 'failed': str(exc)})
    # boolean slivers (a fin where two profiles barely overlap) are not part of the object
    pieces = solid.solids()
    if len(pieces) > 1:
        from build123d import Compound
        vmax = max(p.volume for p in pieces)
        keep = [p for p in pieces if p.volume >= 0.01 * vmax]
        report['slivers_removed'] = len(pieces) - len(keep)
        solid = keep[0] if len(keep) == 1 else Compound(keep)
    return solid, report


def drawing_floor_mm(record, view):
    """Resolvable outline displacement: mm, shared by construction and later QA.

    Use the coarser of the two source axes. A dense QA raster cannot recover
    information absent from the original sheet's pixels.
    """
    from .drawing_qa import GRID_MM
    profile = record['profiles'][view]
    source_mm = [record['size_m'][key] * 1000 / pixels
                 for key, pixels in zip(SPAN[view], profile['image_px'])]
    return max(1.0, 2 * GRID_MM, 1.5 * max(source_mm))


def _construction_tolerance_m(record):
    """Use the order's existing game-prop screen budget, without importing Blender."""
    from .simplification import screen_tolerance
    standards = json.loads((Path(__file__).resolve().parents[2] /
                            'factory/standards.json').read_text(encoding='utf-8'))
    tolerance = screen_tolerance(standards, record.get('kind', 'static'),
                                 record.get('view_distance_m'))
    if tolerance is None or tolerance <= 0:
        raise ValueError('CAD construction requires a positive screen tolerance')
    return tolerance


def _replacement_check(before, candidate, record):
    """Judge each candidate against traced evidence in mm, retaining every gauge.

    The old solid is only a non-regression check; it is not the drawing. Final
    drawing QA retains its existing thresholds independently of this guard.
    """
    from OCP.BRepCheck import BRepCheck_Analyzer
    from .drawing_qa import GRID_MM
    if candidate is None or not candidate.solids():
        return False, {'reason': 'construction produced no solid', 'guard_pass': False}
    if not BRepCheck_Analyzer(candidate.wrapped).IsValid():
        return False, {'reason': 'construction produced an invalid B-rep', 'guard_pass': False}
    old, new = _outline_metrics(before, record), _outline_metrics(candidate, record)
    tolerance = _construction_tolerance_m(record)
    deltas, measurements, reasons = {}, {}, []
    for view in old:
        floor = drawing_floor_mm(record, view)
        limit = max(2 * tolerance * 1000, floor)
        p0, p1 = old[view]['outline_p95_mm'], new[view]['outline_p95_mm']
        delta = new[view]['iou'] - old[view]['iou']
        deltas[view] = round(delta, 6)
        measurements[view] = {'before': old[view], 'after': new[view],
                              'floor_mm': floor, 'limit_mm': limit,
                              'p95_growth_mm': round(p1 - p0, 6),
                              'iou_delta': round(delta, 6)}
        if p1 > limit + 1e-9:
            reasons.append('%s p95 %.2f mm exceeds drawing limit %.2f mm' % (view, p1, limit))
        if p1 - p0 > GRID_MM + 1e-9:
            reasons.append('%s p95 grows %.2f mm (limit %.2f mm)' % (view, p1 - p0, GRID_MM))
        if delta < -0.02 - 1e-9:
            reasons.append('%s IoU drops %.3f (limit 0.020)' % (view, -delta))
    b0, b1 = before.bounding_box(), candidate.bounding_box()
    size_change = max(abs(a - b) for a, b in zip(b0.size, b1.size))
    counts = [len(before.solids()), len(candidate.solids())]
    if size_change > 1.0:
        reasons.append('bounding size changes by %.3f mm' % size_change)
    if counts[1] > counts[0]:
        reasons.append('solid count increases from %d to %d' % tuple(counts))
    return not reasons, {
        'reason': '; '.join(reasons) if reasons else 'drawing distance, regression, size and connectivity guards passed',
        'guard_pass': not reasons, 'views': measurements, 'tolerance_m': tolerance,
        'old_iou_guard_would_reject': min(deltas.values(), default=0) < -0.003,
        'outline_iou_delta': deltas, 'size_change_mm': round(size_change, 4),
        'solid_counts': counts}


def _outline_metrics(solid, record):
    """The unchanged drawing gauge, at the established 0.4 mm tessellation."""
    from .drawing_qa import against_drawing
    verts, tris = solid.tessellate(0.4)
    V = np.array([(v.X, v.Y, v.Z) for v in verts]) / 1000.0
    m, _ = against_drawing(V, np.array(tris), record)
    return m.get('views', {})


def _outline_iou(solid, record):
    return {view: values['iou'] for view, values in _outline_metrics(solid, record).items()}


def _mid_slab_sections(before, after, slab, axis):
    """Diagnostic local B-rep sections in mm; no image-derived geometry is added."""
    from build123d import Plane, section
    box = slab.bounding_box()
    coordinate = {'x': 0, 'y': 1, 'z': 2}[axis]
    level = list(box.center())[coordinate]
    plane, axes = {'x': (Plane.YZ.offset(level), (1, 2)),
                   'y': (Plane.XZ.offset(-level), (0, 2)),
                   'z': (Plane.XY.offset(level), (0, 1))}[axis]

    def paths(shape):
        result = []
        for face in section(shape, section_by=plane).faces():
            for index, wire in enumerate([face.outer_wire(), *face.inner_wires()]):
                points = [list(wire.position_at(t)) for t in np.linspace(0, 1, 257)]
                result.append({'hole': index > 0,
                               'points_mm': [[p[a] for a in axes] for p in points]})
        if not result:
            raise ValueError('no mid-slab section at %.4f mm on %s' % (level, axis))
        return result

    return {'axis': axis, 'level_mm': level, 'plane_axes': list(axes), 'units': 'mm',
            'bounds_mm': [[list(box.min)[a], list(box.max)[a]] for a in axes],
            'before': paths(before), 'after': paths(after)}


def _superellipse_points(ca, cb, ra, rb, n, count=40):
    pts = []
    for k in range(count):
        t = 2 * math.pi * k / count
        c, si = math.cos(t), math.sin(t)
        pts.append((ca + ra * math.copysign(abs(c) ** (2 / n), c), cb + rb * math.copysign(abs(si) ** (2 / n), si)))
    return pts


def _section_cell_mm(record):
    """Recover the section writer's grid, not a shape-specific rounding margin.

    Legacy drawings omit ``roundness.grid``. For those, use the same producer's
    declared default resolution and aspect-ratio rule. These are sampled cells,
    not exact edge locations; rounding._cells already allows half-cell slack.
    """
    import inspect
    from . import rounding
    sizes = [1000 * record['size_m'][k] for k in ('width', 'depth', 'height')]
    grid = (record.get('roundness') or {}).get('grid')
    if grid is None:
        resolution = inspect.signature(rounding.estimate).parameters['res'].default
        grid = [max(8, int(round(resolution * s / max(sizes)))) for s in sizes]
    return {k: s / count for k, s, count in zip(('width', 'depth', 'height'), sizes, grid)}


def _section_wire(axis, along, ca, cb, ra, rb, n, slack_a=0.0, slack_b=0.0):
    """Closed section in mm, with the producer's axis-aligned half-cell offset.

    rounding._cells tests (max(abs(u-ca)-slack_a, 0)/ra)**n +
    (max(abs(v-cb)-slack_b, 0)/rb)**n <= 1. This is the Minkowski sum
    of a superellipse and a rectangle, not a superellipse with larger radii.
    Four translated quadrants and their tangent straight joins encode that sum.
    The eventual intersection with the original solid keeps traced boundaries.
    """
    from build123d import Edge, Wire, Vector

    def point(u, v, position=along):
        return Vector(*{'z': (u, v, position), 'x': (position, u, v),
                        'y': (u, position, v)}[axis])

    if not slack_a and not slack_b:
        return Wire([Edge.make_spline(
            [point(u, v) for u, v in _superellipse_points(ca, cb, ra, rb, n)], periodic=True)])
    signs = ((1, 1), (-1, 1), (-1, -1), (1, -1))
    tangents = ((0, 1), (-1, 0), (0, -1), (1, 0))
    quadrants = []
    for q, (sa, sb) in enumerate(signs):
        points = []
        for t in np.linspace(q * math.pi / 2, (q + 1) * math.pi / 2, 21):
            c, s = math.cos(t), math.sin(t)
            c = 0.0 if abs(c) < 1e-12 else c
            s = 0.0 if abs(s) < 1e-12 else s
            u = ca + ra * math.copysign(abs(c) ** (2 / n), c) + sa * slack_a
            v = cb + rb * math.copysign(abs(s) ** (2 / n), s) + sb * slack_b
            points.append(point(u, v))
        directions = [point(*tangents[q], position=0),
                      point(*tangents[(q + 1) % 4], position=0)]
        quadrants.append((points, Edge.make_spline(points, tangents=directions)))
    edges = []
    for q, (points, curve) in enumerate(quadrants):
        edges.append(curve)
        following = quadrants[(q + 1) % 4][0][0]
        if (points[-1] - following).length > 1e-7:
            edges.append(Edge.make_line(points[-1], following))
    return Wire(edges)


def _round_part(axis, part, size, cell_mm=None):
    """(slab, loft) for one measured round part, or None. Stations are normalised
    (along, a0, a1, b0, b1); axis z: a = x, b = y; axis x: a = y, b = z; axis y: a = x, b = z."""
    from build123d import Edge, Wire, Solid, Box, Location, Vector
    W, D, H = size['width'], size['depth'], size['height']
    span = {'z': (H, W, D), 'x': (W, D, H), 'y': (D, W, H)}[axis]
    keys = {'z': ('height', 'width', 'depth'), 'x': ('width', 'depth', 'height'),
            'y': ('depth', 'width', 'height')}[axis]
    slack = [0.5 * (cell_mm or {}).get(k, 0.0) for k in keys]
    by_station = {}
    for st in part.get('stations', []):
        key = round(st[0], 6)
        area = (st[2] - st[1]) * (st[4] - st[3])
        if key not in by_station or area > by_station[key][0]:
            by_station[key] = (area, st)
    stations = [v[1] for _, v in sorted(by_station.items())]
    if len(stations) < 3:
        return None
    # These stations already summarize traced profiles. Smoothing or discarding
    # extrema here shrinks feet and caps before the outline guard can inspect them.
    # Ruled spans preserve their bounds and avoid unconstrained longitudinal ringing.
    chosen = list(stations)
    # Overrun both slab ends before clipping to local material. Adjacent slabs
    # then meet on a stable interior section rather than an interpolated loft cap.
    if slack[0]:
        first_cap, last_cap = list(stations[0]), list(stations[-1])
        first_cap[0] -= slack[0] / span[0]
        last_cap[0] += slack[0] / span[0]
        chosen = [first_cap, *chosen, last_cap]
    n = float(part['n'])

    def to3d(along, a, b):
        return {'z': (a, b, along), 'x': (along, a, b), 'y': (a, along, b)}[axis]
    wires = []
    for along, a0, a1, b0, b1 in chosen:
        L, A, B = along * span[0], (a0 + a1) / 2 * span[1], (b0 + b1) / 2 * span[2]
        ra, rb = (a1 - a0) / 2 * span[1], (b1 - b0) / 2 * span[2]
        if ra + slack[1] < 0.3 or rb + slack[2] < 0.3:
            continue
        wires.append(_section_wire(axis, L, A, B, ra, rb, n, slack[1], slack[2]))
    if len(wires) < 3:
        return None
    loft = Solid.make_loft(wires, ruled=True)
    k0, k1, a0, a1, b0, b1 = part['box']
    lo = to3d(k0 * span[0], a0 * span[1], b0 * span[2])
    hi = to3d(k1 * span[0], a1 * span[1], b1 * span[2])
    dims = [max(0.5, h - l) for l, h in zip(lo, hi)]
    centre = [(l + h) / 2 for l, h in zip(lo, hi)]
    # the slab spans the part's own stations only, so the loft (which starts and ends there)
    # replaces exactly what it covers
    first, last = stations[0][0] * span[0], stations[-1][0] * span[0]
    ax = {'z': 2, 'x': 0, 'y': 1}[axis]
    dims[ax] = max(0.5, last - first)
    centre[ax] = (first + last) / 2
    slab = Box(*dims).moved(Location(tuple(centre)))
    # the part's own volume if it were square-cornered: its station rectangles times spacing
    step_len = (last - first) / max(1, len(stations) - 1)
    prism = sum((st[2] - st[1]) * span[1] * (st[4] - st[3]) * span[2] for st in stations) * step_len
    return slab, loft, prism


def properties(solid, material='ABS'):
    bb = solid.bounding_box()
    vol = solid.volume
    com = solid.center()
    return {'volume_cm3': round(vol / 1000, 1), 'surface_area_cm2': round(solid.area / 100, 1),
            'bounding_box_mm': [round(bb.size.X, 1), round(bb.size.Y, 1), round(bb.size.Z, 1)],
            'centre_of_mass_mm': [round(com.X, 1), round(com.Y, 1), round(com.Z, 1)],
            'material_assumed': material,
            'mass_if_solid_g': round(vol / 1000 * MATERIALS[material], 1),
            'note': 'mass as a solid body; real moulded parts are shells (wall thickness not observable)'}


def export(record, masks, destination, name, material='ABS'):
    """STEP + STL of the CAD solid and the engineering drawing (DXF + PNG). Returns a report."""
    from build123d import export_step, export_stl
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    solid, rep = build_solid(record, masks)
    if solid is None:
        return {'cad_failure': 'no profiles to build from'}
    step = destination / (name + '.step')
    stl = destination / (name + '_cad.stl')
    export_step(solid, str(step))
    export_stl(solid, str(stl), tolerance=0.05, angular_tolerance=0.1)
    props = properties(solid, material)
    rep.update(props)
    dxf, png = drawing(solid, record, destination, name, props)
    rep.update({'step': str(step), 'stl': str(stl), 'drawing_dxf': dxf, 'drawing_png': png})
    (destination / (name + '_cad.json')).write_text(json.dumps(rep, indent=1))
    return rep


def _edges_2d(edges, n=48):
    """Projected edges as 2D point lists (the projection lies in the viewport's XY)."""
    out = []
    for e in edges:
        try:
            pts = [e.position_at(t) for t in np.linspace(0, 1, n if e.geom_type != 'LINE' else 2)]
        except Exception:
            continue
        out.append([(p.X, p.Y) for p in pts])
    return out


def _hatch(msp, P, spacing):
    """ANSI31 section hatching (45 degree lines) as plain lines clipped to the section."""
    from shapely.geometry import Polygon, LineString
    poly = Polygon(P).buffer(0)
    if poly.is_empty:
        return
    x0, y0, x1, y1 = poly.bounds
    span = (x1 - x0) + (y1 - y0)
    t = -span
    while t < span:
        line = LineString([(x0 + t, y0), (x0 + t + span, y0 + span)])
        cut = poly.intersection(line)
        for seg in getattr(cut, 'geoms', [cut]):
            if seg.geom_type == 'LineString' and seg.length > 0:
                msp.add_line(seg.coords[0], seg.coords[-1], dxfattribs={'layer': 'HATCH'})
        t += spacing


def drawing(solid, record, destination, name, props):
    """Hidden-line orthographic views + isometric + sections, dimensioned, as DXF and PNG."""
    import ezdxf
    from ezdxf.enums import TextEntityAlignment
    from build123d import Plane, section
    size = {k: v * 1000 for k, v in record['size_m'].items()}
    W, D, H = size['width'], size['depth'], size['height']
    big = max(W, D, H)
    th = max(2.5, round(0.022 * big, 1))
    c = solid.center()
    far = big * 10
    views = {   # name: (viewport origin, up)
        'FRONT': ((c.X, c.Y - far, c.Z), (0, 0, 1)),
        'TOP': ((c.X, c.Y, c.Z + far), (0, 1, 0)),
        'RIGHT': ((c.X + far, c.Y, c.Z), (0, 0, 1)),
        'ISOMETRIC': ((c.X + far, c.Y - far, c.Z + far), (0, 0, 1)),
    }
    doc = ezdxf.new('R2018', setup=True)
    doc.units = ezdxf.units.MM
    for lname, color, ltype, lw in (('VISIBLE', 7, 'CONTINUOUS', 50), ('HIDDEN', 8, 'DASHED', 25),
                                    ('CENTER', 1, 'CENTER', 18), ('DIMENSIONS', 3, 'CONTINUOUS', 18),
                                    ('SECTION', 7, 'CONTINUOUS', 50), ('HATCH', 8, 'CONTINUOUS', 13),
                                    ('NOTES', 7, 'CONTINUOUS', 18), ('BORDER', 7, 'CONTINUOUS', 35)):
        doc.layers.add(lname, color=color, linetype=ltype, lineweight=lw)
    ds = doc.dimstyles.duplicate_entry('EZDXF', 'HULL')
    for k, v in (('dimtxt', th), ('dimasz', th * 0.9), ('dimexo', th * 0.4), ('dimexe', th * 0.6),
                 ('dimgap', th * 0.3), ('dimdec', 1), ('dimlunit', 2), ('dimdsep', ord('.')), ('dimzin', 8),
                 ('dimlfac', 1.0), ('dimblk', ''), ('dimtxsty', 'Standard'), ('dimtih', 0), ('dimtoh', 0)):
        ds.dxf.set(k, v)
    msp = doc.modelspace()
    g = 0.45 * big + 30
    place = {'FRONT': (0, 0), 'TOP': (0, H + g), 'RIGHT': (W + g, 0), 'ISOMETRIC': (W + g + D + g, H + g * 0.5)}
    boxes = {}
    for vname, (origin, up) in views.items():
        vis, hid = solid.project_to_viewport(origin, viewport_up=up, look_at=(c.X, c.Y, c.Z))
        lv, lh = _edges_2d(vis), _edges_2d(hid)
        # a boolean can leave a degenerate edge that projects far outside the part: drop any
        # edge that leaves the part's own extent (half its largest size around its middle)
        allp = np.array([p for e in lv + lh for p in e]) if lv + lh else np.zeros((1, 2))
        mid = np.median(allp, 0)
        inside = lambda e: np.all(np.abs(np.asarray(e) - mid) <= 0.75 * big)
        lv, lh = [e for e in lv if inside(e)], [e for e in lh if inside(e)]
        allp = np.array([p for e in lv + lh for p in e]) if lv + lh else np.zeros((1, 2))
        lo, hi = allp.min(0), allp.max(0)
        ox, oy = place[vname]
        sh = np.array([ox, oy]) - lo
        for layer, edges in (('VISIBLE', lv), ('HIDDEN', lh if vname != 'ISOMETRIC' else [])):
            for e in edges:
                msp.add_lwpolyline([tuple(np.array(p) + sh) for p in e], dxfattribs={'layer': layer})
        boxes[vname] = (ox, oy, ox + hi[0] - lo[0], oy + hi[1] - lo[1])
        msp.add_text(vname + (' VIEW' if vname != 'ISOMETRIC' else ' (FOR REFERENCE)'), height=th * 1.1,
                     dxfattribs={'layer': 'NOTES'}).set_placement(
            ((boxes[vname][0] + boxes[vname][2]) / 2, oy - th * 4.2), align=TextEntityAlignment.TOP_CENTER)
    # sections through the middle: A-A across the depth (seen from the front), B-B across the width
    sec_place = {'A-A': (-(W + g), 0), 'B-B': (W + g, -(H + g))}
    bc = solid.bounding_box().center()
    for sname, plane, axes, (ox, oy) in (('A-A', Plane.XZ.offset(-bc.Y), (0, 2), sec_place['A-A']),
                                         ('B-B', Plane.YZ.offset(bc.X), (1, 2), sec_place['B-B'])):
        try:
            faces = section(solid, section_by=plane).faces()
        except Exception:
            continue
        for f in faces:
            for wi, wire in enumerate([f.outer_wire()] + list(f.inner_wires())):
                pts = []
                for e in wire.edges():
                    pts += [(p.X, p.Y, p.Z) for p in (e.position_at(t) for t in np.linspace(0, 1, 24))]
                P = np.array(pts)[:, list(axes)]
                if sname == 'A-A':
                    P[:, 0] = P[:, 0]
                P = P + np.array([ox, oy])
                msp.add_lwpolyline([tuple(p) for p in P], close=True, dxfattribs={'layer': 'SECTION'})
                if wi == 0:
                    _hatch(msp, P, max(1.5, big / 60))
        msp.add_text('SECTION ' + sname, height=th * 1.1, dxfattribs={'layer': 'NOTES'}).set_placement(
            (ox + (D if sname == 'B-B' else W) / 2, oy - th * 4.2), align=TextEntityAlignment.TOP_CENTER)
    # cutting-plane lines on the front (B-B) and top (A-A) views
    fx0, fy0, fx1, fy1 = boxes['FRONT']
    msp.add_line((fx0 + bc.X, fy0 - th), (fx0 + bc.X, fy1 + th), dxfattribs={'layer': 'CENTER'})
    msp.add_text('B', height=th, dxfattribs={'layer': 'NOTES'}).set_placement((fx0 + bc.X + th * 0.5, fy1 + th))
    tx0, ty0, tx1, ty1 = boxes['TOP']
    msp.add_line((tx0 - th, ty0 + bc.Y), (tx1 + th, ty0 + bc.Y), dxfattribs={'layer': 'CENTER'})
    msp.add_text('A', height=th, dxfattribs={'layer': 'NOTES'}).set_placement((tx1 + th, ty0 + bc.Y + th * 0.5))
    dim = lambda p1, p2, base, angle=0: msp.add_linear_dim(
        base=base, p1=p1, p2=p2, angle=angle, dimstyle='HULL', dxfattribs={'layer': 'DIMENSIONS'}).render()
    dim((fx0, fy0), (fx1, fy0), (fx0, fy0 - th * 2.2))
    dim((fx0, fy0), (fx0, fy1), (fx0 - th * 2.5, fy0), angle=90)
    rx0, ry0, rx1, ry1 = boxes['RIGHT']
    dim((rx0, ry0), (rx1, ry0), (rx0, ry0 - th * 2.2))
    dim((tx0, ty0), (tx0, ty1), (tx0 - th * 2.5, ty0), angle=90)
    # features from the drawing stage: circles in the front view, with their diameters
    prof = record['profiles'].get('front')
    if prof:
        w, h = prof['image_px']
        su, sv = W / w, H / h
        for circ in record['circles'].get('front', []):
            cx, cy = fx0 + circ['center_px'][0] * su, fy0 + (h - circ['center_px'][1]) * sv
            r = circ['radius_px'] * (su + sv) / 2
            msp.add_circle((cx, cy), r, dxfattribs={'layer': 'VISIBLE'})
            msp.add_line((cx - r * 1.2, cy), (cx + r * 1.2, cy), dxfattribs={'layer': 'CENTER'})
            msp.add_line((cx, cy - r * 1.2), (cx, cy + r * 1.2), dxfattribs={'layer': 'CENTER'})
            msp.add_diameter_dim(center=(cx, cy), radius=r, angle=45, dimstyle='HULL',
                                 dxfattribs={'layer': 'DIMENSIONS'}).render()
    for rs in record.get('round_sections', []):
        if rs['axis'] == 'y':
            cx, cy = fx0 + rs['center_m'][0] * 1000, fy0 + rs['center_m'][1] * 1000
            msp.add_line((cx - big * 0.04, cy), (cx + big * 0.04, cy), dxfattribs={'layer': 'CENTER'})
    # border + title block + properties
    ext = [boxes[k] for k in boxes] + [(sec_place['A-A'][0], 0, sec_place['A-A'][0] + W, H),
                                        (sec_place['B-B'][0], sec_place['B-B'][1], sec_place['B-B'][0] + D,
                                         sec_place['B-B'][1] + H)]
    x0 = min(b[0] for b in ext) - g * 0.5
    x1 = max(b[2] for b in ext) + g * 0.5
    y1 = max(b[3] for b in ext) + g * 0.5
    y0 = min(b[1] for b in ext) - g * 0.5 - th * 4
    tb_h = th * 22
    y0 = min(y0, -(H + g) - th * 6) - tb_h
    msp.add_lwpolyline([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], close=True, dxfattribs={'layer': 'BORDER'})
    tb_w = max(th * 70, (x1 - x0) * 0.45)
    tbx = x1 - tb_w
    msp.add_lwpolyline([(tbx, y0), (x1, y0), (x1, y0 + tb_h), (tbx, y0 + tb_h)], close=True,
                       dxfattribs={'layer': 'BORDER'})
    rows = [('TITLE', name.replace('_', ' ').upper()),
            ('DRAWING', 'GENERAL ARRANGEMENT - CAD SOLID (STEP: %s.step)' % name),
            ('SIZE W x D x H', '%.1f x %.1f x %.1f mm' % tuple(props['bounding_box_mm'])),
            ('VOLUME / AREA', '%.1f cm3 / %.1f cm2' % (props['volume_cm3'], props['surface_area_cm2'])),
            ('CENTRE OF MASS', 'x %.1f  y %.1f  z %.1f mm (from front-left-bottom corner)' % tuple(props['centre_of_mass_mm'])),
            ('MASS', '%.0f g if solid %s; real part is a shell (wall not observable)' % (
                props['mass_if_solid_g'], props['material_assumed'])),
            ('UNITS / SCALE', 'mm, 1:1 model space'),
            ('PROJECTION', 'THIRD ANGLE; hidden edges dashed'),
            ('TOLERANCE', 'sizes estimated from a reference sheet: verify before tooling'),
            ('DATE / BY', '%s  Hull CAD export (OpenCascade)' % datetime.date.today().isoformat())]
    for i, (k, v) in enumerate(rows):
        y = y0 + tb_h - th * (1.9 + 2.0 * i)
        msp.add_text(k, height=th * 0.8, dxfattribs={'layer': 'NOTES'}).set_placement((tbx + th, y))
        msp.add_text(v[:90], height=th * 0.85, dxfattribs={'layer': 'NOTES'}).set_placement((tbx + th * 17, y))
    notes = ['NOTES:', '1. ' + (record.get('scale_note') or 'Scale estimated from the sheet.'),
             '2. Unseen: wall thickness, internal parts, fasteners, draft angles, parting line.',
             '3. Solid = drawn front, side and top profiles extruded and intersected; round where the end view is round.']
    for i, d in enumerate(record.get('decisions', [])[:4]):
        notes.append('%d. %s' % (i + 4, d))
    for i, t in enumerate(notes):
        msp.add_text(t[:150], height=th * 0.75, dxfattribs={'layer': 'NOTES'}).set_placement(
            (x0 + th, y0 + tb_h - th * (1.8 + 1.5 * i)))
    dxf_path = Path(destination) / (name + '_cad_drawing.dxf')
    doc.saveas(dxf_path)
    png_path = Path(destination) / (name + '_cad_drawing.png')
    from .drawing_cad import _render_png
    _render_png(doc, png_path, (x1 - x0) / (y1 - y0))
    return str(dxf_path), str(png_path)
