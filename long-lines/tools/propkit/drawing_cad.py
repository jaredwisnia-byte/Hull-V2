"""Writes the drawing stage's record as an AutoCAD drawing (DXF, via ezdxf) and a PNG of it.

Model space is in millimetres at full size. Views are laid out in third-angle projection
(top above the front, right side to its right, left side to its left, back beyond the right
side, bottom below the front) and aligned, so a dimension read in one view lines up in the
next. Layers: OUTLINE (visible profile), CENTER (centre and symmetry lines), DIMENSIONS,
NOTES, BORDER. Every dimension is an associative DIMENSION entity an engineer can edit.
"""
import datetime
import math
from pathlib import Path

import numpy as np

SPAN = {'front': ('width', 'height'), 'back': ('width', 'height'), 'right': ('depth', 'height'),
        'left': ('depth', 'height'), 'top': ('width', 'depth'), 'bottom': ('width', 'depth')}


def layout(size_mm):
    """Lower-left corner of each view in model space (mm)."""
    W, D, H = size_mm['width'], size_mm['depth'], size_mm['height']
    g = 0.35 * max(W, D, H) + 25
    return {'front': (0, 0), 'top': (0, H + g), 'bottom': (0, -(D + g)),
            'right': (W + g, 0), 'left': (-(D + g), 0), 'back': (W + g + D + g, 0)}, g


def write(record, masks, destination, name):
    import ezdxf
    from ezdxf.enums import TextEntityAlignment
    size = {k: v * 1000 for k, v in record['size_m'].items()}
    W, D, H = size['width'], size['depth'], size['height']
    big = max(W, D, H)
    th = max(2.5, round(0.022 * big, 1))         # text height, mm
    doc = ezdxf.new('R2018', setup=True)
    doc.units = ezdxf.units.MM
    doc.header['$INSUNITS'] = 4
    doc.header['$MEASUREMENT'] = 1
    for lname, color, ltype, lw in (('OUTLINE', 7, 'CONTINUOUS', 50), ('CENTER', 1, 'CENTER', 18),
                                    ('DIMENSIONS', 3, 'CONTINUOUS', 18), ('NOTES', 7, 'CONTINUOUS', 18),
                                    ('BORDER', 7, 'CONTINUOUS', 35), ('FEATURES', 5, 'CONTINUOUS', 35)):
        doc.layers.add(lname, color=color, linetype=ltype, lineweight=lw)
    ds = doc.dimstyles.duplicate_entry('EZDXF', 'HULL')
    ds.dxf.dimtxt = th
    ds.dxf.dimasz = th * 0.9
    ds.dxf.dimexo = th * 0.4
    ds.dxf.dimexe = th * 0.6
    ds.dxf.dimgap = th * 0.3
    ds.dxf.dimdec = 1
    ds.dxf.dimlunit = 2
    ds.dxf.dimdsep = ord('.')
    ds.dxf.dimlfac = 1.0          # model space is mm: dimensions read true size
    ds.dxf.dimblk = ''            # closed filled arrows (engineering, not architectural ticks)
    ds.dxf.dimtxsty = 'Standard'
    ds.dxf.dimtih = 0
    ds.dxf.dimtoh = 0
    ds.dxf.dimzin = 8
    msp = doc.modelspace()
    origin, gap = layout(size)

    def to_mm(view, x, y):
        """View pixel -> model space mm (image y runs down, drawing y runs up)."""
        w, h = record['profiles'][view]['image_px']
        su, sv = size[SPAN[view][0]] / w, size[SPAN[view][1]] / h
        ox, oy = origin[view]
        return ox + x * su, oy + (h - y) * sv, (su + sv) / 2

    dim = lambda p1, p2, base, angle=0: msp.add_linear_dim(
        base=base, p1=p1, p2=p2, angle=angle, dimstyle='HULL', dxfattribs={'layer': 'DIMENSIONS'}).render()
    for view, prof in record['profiles'].items():
        ox, oy = origin[view]
        sw, sh = size[SPAN[view][0]], size[SPAN[view][1]]
        pts = [(*to_mm(view, x, y)[:2], -b) for x, y, b in prof['vertices_px']]   # y flip reverses arcs
        msp.add_lwpolyline(pts, format='xyb', close=True, dxfattribs={'layer': 'OUTLINE'})
        msp.add_text(view.upper() + ' VIEW', height=th * 1.1, dxfattribs={'layer': 'NOTES'}).set_placement(
            (ox + sw / 2, oy - th * 4.2), align=TextEntityAlignment.TOP_CENTER)
        sym = record['symmetry'].get(view)
        if sym:
            cx = to_mm(view, sym['axis_col_px'], 0)[0]
            msp.add_line((cx, oy - th), (cx, oy + sh + th), dxfattribs={'layer': 'CENTER'})
        for c in record['circles'].get(view, []):
            cx, cy, s = to_mm(view, *c['center_px'])
            r = c['radius_px'] * s
            msp.add_circle((cx, cy), r, dxfattribs={'layer': 'FEATURES'})
            e = r * 1.2
            msp.add_line((cx - e, cy), (cx + e, cy), dxfattribs={'layer': 'CENTER'})
            msp.add_line((cx, cy - e), (cx, cy + e), dxfattribs={'layer': 'CENTER'})
            msp.add_diameter_dim(center=(cx, cy), radius=r, angle=45, dimstyle='HULL',
                                 dxfattribs={'layer': 'DIMENSIONS'}).render()
        # large outline arcs get their radius (the four largest by length, to keep it legible)
        arcs = []
        for i, (x, y, b) in enumerate(prof['vertices_px']):
            if abs(b) < 1e-9:
                continue
            x2, y2, _ = prof['vertices_px'][(i + 1) % len(prof['vertices_px'])]
            p0, p1 = np.array(to_mm(view, x, y)[:2]), np.array(to_mm(view, x2, y2)[:2])
            sweep = 4 * math.atan(abs(b))
            L = np.linalg.norm(p1 - p0)
            if L < 1e-6 or sweep < math.radians(40):
                continue
            r = L / (2 * math.sin(sweep / 2))
            if r < 0.04 * big or r > 2 * big:
                continue
            arcs.append((r * sweep, p0, p1, -b, r))
        for _, p0, p1, b, r in sorted(arcs, key=lambda a: -a[0])[:2]:
            chord = p1 - p0
            mid = (p0 + p1) / 2
            nrm = np.array([-chord[1], chord[0]]) / np.linalg.norm(chord)
            sweep = 4 * math.atan(b)
            h = r * math.cos(abs(sweep) / 2) * (1 if sweep > 0 else -1)
            c = mid + nrm * h
            a_mid = math.degrees(math.atan2(*(mid - c)[::-1]))
            msp.add_radius_dim(center=tuple(c), radius=r, angle=a_mid, dimstyle='HULL',
                               dxfattribs={'layer': 'DIMENSIONS'}).render()
    # overall dimensions, aligned across views
    ox, oy = origin['front']
    dim((ox, oy), (ox + W, oy), (ox, oy - th * 2.2))
    dim((ox, oy), (ox, oy + H), (ox - th * 2.5, oy), angle=90)
    if 'right' in record['profiles']:
        rx, ry = origin['right']
        dim((rx, ry), (rx + D, ry), (rx, ry - th * 2.2))
    if 'top' in record['profiles']:
        tx, ty = origin['top']
        dim((tx, ty), (tx, ty + D), (tx - th * 2.5, ty), angle=90)
    for rs in record['round_sections']:
        v = rs['end_view']
        cu, cz = (c * 1000 for c in rs['center_m'])
        span = size[SPAN[v][0]]
        if v in ('back', 'left'):
            cu = span - cu
        cx, cy = origin[v][0] + cu, origin[v][1] + cz
        r = rs['radius_m'] * 1000
        msp.add_circle((cx, cy), r, dxfattribs={'layer': 'CENTER'})
    # border, title block, notes
    xs = [origin[v][0] for v in record['profiles']] + [origin[v][0] + size[SPAN[v][0]] for v in record['profiles']]
    ys = [origin[v][1] for v in record['profiles']] + [origin[v][1] + size[SPAN[v][1]] for v in record['profiles']]
    x0, x1 = min(xs) - gap * 0.6, max(xs) + gap * 0.6
    y0, y1 = min(ys) - gap * 0.6 - th * 18, max(ys) + gap * 0.6
    msp.add_lwpolyline([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], close=True, dxfattribs={'layer': 'BORDER'})
    tb_w = max(th * 60, (x1 - x0) * 0.42)
    tb_h = th * 16
    tbx, tby = x1 - tb_w, y0
    msp.add_lwpolyline([(tbx, tby), (x1, tby), (x1, tby + tb_h), (tbx, tby + tb_h)], close=True,
                       dxfattribs={'layer': 'BORDER'})
    lines = [('TITLE', name.replace('_', ' ').upper()),
             ('SIZE (W x D x H)', '%.1f x %.1f x %.1f mm' % (W, D, H)),
             ('UNITS / SCALE', 'mm, model space 1:1'),
             ('PROJECTION', 'THIRD ANGLE'),
             ('TOLERANCE', 'outline fit %.1f px; sizes estimated, verify before tooling' % 1.0),
             ('SOURCE', 'painted reference sheet (Hull drawing stage)'),
             ('DATE', datetime.date.today().isoformat())]
    for i, (k, v) in enumerate(lines):
        y = tby + tb_h - th * (1.9 + 2.0 * i)
        msp.add_text(k, height=th * 0.8, dxfattribs={'layer': 'NOTES'}).set_placement((tbx + th, y))
        msp.add_text(v, height=th * 0.9, dxfattribs={'layer': 'NOTES'}).set_placement((tbx + th * 16, y))
    notes = ['NOTES:', '1. ' + (record.get('scale_note') or 'Scale estimated from the sheet.')]
    for i, d in enumerate(record['decisions'][:6]):
        notes.append('%d. %s' % (i + 2, d))
    for i, t in enumerate(notes):
        msp.add_text(t[:160], height=th * 0.75, dxfattribs={'layer': 'NOTES'}).set_placement(
            (x0 + th, y0 + tb_h - th * (1.8 + 1.5 * i)))
    destination = Path(destination)
    dxf_path = destination / (name + '.dxf')
    doc.saveas(dxf_path)
    png_path = destination / (name + '_drawing.png')
    _render_png(doc, png_path, (x1 - x0) / (y1 - y0))
    return str(dxf_path), str(png_path)


def _render_png(doc, path, aspect):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from ezdxf.addons.drawing import Frontend, RenderContext
    from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
    from ezdxf.addons.drawing.config import Configuration, BackgroundPolicy, ColorPolicy, LineweightPolicy
    fig = plt.figure(figsize=(16, 16 / max(0.3, aspect)))
    ax = fig.add_axes([0, 0, 1, 1])
    cfg = Configuration(background_policy=BackgroundPolicy.WHITE, color_policy=ColorPolicy.BLACK,
                        lineweight_policy=LineweightPolicy.ABSOLUTE, lineweight_scaling=1.6)
    Frontend(RenderContext(doc), MatplotlibBackend(ax), config=cfg).draw_layout(doc.modelspace(), finalize=True)
    fig.set_size_inches(18, 18 / max(0.3, aspect))
    fig.savefig(path, dpi=150, facecolor='white')
    plt.close(fig)
