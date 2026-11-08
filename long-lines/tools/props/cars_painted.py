"""Cars textured from a painted car sheet (assets/source_textures/<name>/).

painted_car() traces the body silhouette from the painted side view, extrudes the
lower body and a narrower greenhouse, and maps every face to the matching part of
the sheet by its direction: sides, front, rear, hood, roof, trunk, windscreens.
A new car is a new sheet plus one @prop line.
"""
import math
import os

import bmesh
import bpy
import numpy as np
from PIL import Image

from propkit import prop
from propkit import mats as M
from propkit.core import apply_mods, cyl, link, planar_uv, smooth, box, tube, wrap_uv
from propkit.parts import wheel

SRC = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "assets", "source_textures"))


def _largest_blob(mask):
    """Keeps only the biggest connected shape (drops swatches and loose parts)."""
    h, w = mask.shape
    lab = np.zeros(mask.shape, dtype=np.int32)
    best, best_n, cur = 0, 0, 0
    for sy in range(0, h, 3):
        for sx in range(0, w, 3):
            if not mask[sy, sx] or lab[sy, sx]:
                continue
            cur += 1
            stack, n = [(sy, sx)], 0
            lab[sy, sx] = cur
            while stack:
                y, x = stack.pop()
                n += 1
                for yy, xx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
                    if 0 <= yy < h and 0 <= xx < w and mask[yy, xx] and not lab[yy, xx]:
                        lab[yy, xx] = cur
                        stack.append((yy, xx))
            if n > best_n:
                best, best_n = cur, n
    return lab == best


def _mask(path):
    a = np.asarray(Image.open(path).convert("RGB")).astype(int)
    bg = np.median(np.concatenate([a[:, 0], a[:, -1]]), axis=0)
    return _largest_blob(np.abs(a - bg).sum(2) > 45)


def _span(mask):
    cols = np.nonzero(mask.any(0))[0]
    return int(cols[0]), int(cols[-1])


def _profile(left_path, right_path, step=4):
    """Car outline from the two painted side views: the roofline from the upper
    view (nothing above it on the sheet) and the rocker and wheel arches from the
    lower view (nothing below it), mirrored onto the upper view's columns."""
    ml, mr = _mask(left_path), _mask(right_path)
    l0, l1 = _span(ml)
    r0, r1 = _span(mr)
    cols = list(range(l0, l1 + 1, step))
    top, bot = {}, {}
    hr = mr.shape[0]
    for x in cols:
        top[x] = int(np.argmax(ml[:, x]))
        t = (x - l0) / max(l1 - l0, 1)
        xr = int(round(r1 - t * (r1 - r0)))
        col = mr[:, xr]
        # lower view measured from its own bottom, rescaled to the upper view
        lowest = hr - 1 - int(np.argmax(col[::-1])) if col.any() else hr - 1
        bot[x] = lowest
    rr = max(bot.values())
    scale = (l1 - l0) / max(r1 - r0, 1)
    rocker_l = max(top.values()) if False else None
    # Place the lower view's rocker on the upper view's lowest body row.
    lrock = int(np.nonzero(ml.any(1))[0][-1])
    lrock = min(lrock, ml.shape[0] - 1)
    for x in cols:
        bot[x] = int(round(lrock - (rr - bot[x]) * scale))
    return cols, top, bot, ml.shape


def _uvs(obj, rules):
    """Assigns material slots and face-corner label coordinates by face direction.
    rules(center, normal) -> (slot, (u, v) function of a vertex)."""
    me = obj.data
    attr = me.color_attributes.new("label_uv", "FLOAT_COLOR", "CORNER")
    for poly in me.polygons:
        slot, fn = rules(poly.center, poly.normal)
        poly.material_index = slot
        for li in poly.loop_indices:
            u, v = fn(me.vertices[me.loops[li].vertex_index].co)
            attr.data[li].color = (u, v, 0, 1)


def _extrude(poly_yz, x0, x1, taper=0.0):
    bm = bmesh.new()
    vs = [bm.verts.new((x0, y, z)) for y, z in poly_yz]
    f = bm.faces.new(vs)
    ext = bmesh.ops.extrude_face_region(bm, geom=[f])
    zmin = min(z for _, z in poly_yz)
    zmax = max(z for _, z in poly_yz)
    for v in [e for e in ext["geom"] if isinstance(e, bmesh.types.BMVert)]:
        v.co.x = x1
    if taper:
        for v in bm.verts:
            k = (v.co.z - zmin) / max(zmax - zmin, 1e-6)
            v.co.x *= 1.0 - taper * k
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new("body")
    bm.to_mesh(me)
    bm.free()
    return link(bpy.data.objects.new("body", me))


def painted_car(name, body="car_coupe", length=5.3, width=1.98, cabin_width=1.62, clearance=0.2, belt=0.47):
    """body: the sheet whose side views define the shape. Repaints of the same car
    (rusted, burnt, other colours) reuse one clean reference outline, because wrecks
    and loose trim pieces on a sheet make outlines unreliable."""
    d = os.path.join(SRC, name)
    shape = os.path.join(SRC, body)
    T = lambda part, rough=0.45, rep="EXTEND": M.image(os.path.join(d, part + ".png"), rough, 0.25, 0.02, name="%s_%s" % (name, part), extension=rep)
    cols, top, bot, (hpx, wpx) = _profile(os.path.join(shape, "side_l.png"), os.path.join(shape, "side_r.png"))
    x0p, x1p = cols[0], cols[-1]
    s = length / (x1p - x0p)
    rocker = max(bot.values())
    Y = lambda xp: -length / 2 + (xp - x0p) * s
    Z = lambda yp: (rocker - yp) * s + clearance
    belt_px = min(top.values()) + belt * (rocker - min(top.values()))
    # Lower body: silhouette clipped at the beltline. Greenhouse: what's above it.
    low = [(Y(x), Z(max(top[x], belt_px))) for x in cols] + [(Y(x), Z(bot[x])) for x in reversed(cols)]
    # Greenhouse: the one continuous run of columns around the roof's highest point
    # that rises above the beltline (bumper ends near the beltline don't count).
    peak = cols.index(min(cols, key=lambda x: top[x]))
    lo = hi = peak
    while lo > 0 and top[cols[lo - 1]] < belt_px - 2:
        lo -= 1
    while hi < len(cols) - 1 and top[cols[hi + 1]] < belt_px - 2:
        hi += 1
    gcols = cols[lo:hi + 1]
    green = [(Y(x), Z(top[x])) for x in gcols] + [(Y(gcols[-1]), Z(belt_px)), (Y(gcols[0]), Z(belt_px))]
    hgt = Z(min(top.values()))
    y_ws, y_rw = Y(gcols[0]), Y(gcols[-1])
    # Side views: map each by its own measured outline (car spans x0..x1, rocker row).
    mr = _mask(os.path.join(shape, "side_r.png"))
    r0, r1 = _span(mr)
    hr, wr = mr.shape
    rrock = int(np.nonzero(mr.any(1))[0][-1])
    sr = length / (r1 - r0)
    side_l_uv = lambda v: ((x0p + (v.y + length / 2) / s) / wpx, 1 - (rocker - (v.z - clearance) / s) / hpx)
    side_r_uv = lambda v: ((r1 - (v.y + length / 2) / sr) / wr, 1 - (rrock - (v.z - clearance) / sr) / hr)
    roof_y0, roof_y1 = Y(min(gcols, key=lambda x: top[x] if x < (x0p + x1p) / 2 else 1e9)), y_rw
    mats_ = [T("side_l"), T("side_r"), T("front"), T("rear"), T("hood"), T("roof", 0.6), T("trunk"), T("windshield", 0.1), T("rear_glass", 0.1)]

    def rules(c, n):
        if n.x > 0.55:
            return 0, side_l_uv
        if n.x < -0.55:
            return 1, side_r_uv
        if c.z > Z(belt_px) + 0.02:  # greenhouse
            if n.y < -0.35:
                return 7, lambda v: (v.x / cabin_width + 0.5, (v.z - Z(belt_px)) / (hgt - Z(belt_px)))
            if n.y > 0.35:
                return 8, lambda v: (0.5 - v.x / cabin_width, (v.z - Z(belt_px)) / (hgt - Z(belt_px)))
            return 5, lambda v: (v.x / cabin_width + 0.5, (v.y - y_ws) / (y_rw - y_ws))
        if n.y < -0.5:
            return 2, lambda v: (v.x / width + 0.5, (v.z - clearance) / (Z(belt_px) - clearance))
        if n.y > 0.5:
            return 3, lambda v: (0.5 - v.x / width, (v.z - clearance) / (Z(belt_px) - clearance))
        if c.y < y_ws:
            return 4, lambda v: (v.x / width + 0.5, 1 - (v.y + length / 2) / max(y_ws + length / 2, 0.1))
        return 6, lambda v: (v.x / width + 0.5, 1 - (v.y - y_rw) / max(length / 2 - y_rw, 0.1))

    for poly, (wa, wb, taper) in ((low, (width, width, 0.0)), (green, (cabin_width, cabin_width, 0.12))):
        o = _extrude(poly, -wa / 2, wa / 2, taper)
        for m in mats_:
            o.data.materials.append(m)
        _uvs(o, rules)
        b = o.modifiers.new("bev", "BEVEL")
        b.width, b.segments, b.limit_method, b.angle_limit = 0.045, 3, "ANGLE", math.radians(35)
        apply_mods(o)
        smooth(o, 35)
    # Bumpers
    for part, y, flip in (("front_bumper", -length / 2 - 0.05, False), ("rear_bumper", length / 2 + 0.05, True)):
        bb = box((width + 0.04, 0.16, 0.2), (0, y, clearance + 0.12), T(part, 0.3), bevel=0.04)
        planar_uv(bb, 0, 2, width + 0.04, 0.2, flip_u=flip)
    # Wheels where the arches are.
    arch = [x for x in cols if bot[x] < rocker - 0.3 * (rocker - belt_px)]
    groups, cur = [], [arch[0]]
    for x in arch[1:]:
        if x - cur[-1] > 12:
            groups.append(cur)
            cur = []
        cur.append(x)
    groups.append(cur)
    # Real arches are inside the body, not at the bumper ends: keep the two widest.
    groups = [g for g in groups if g[0] > cols[2] and g[-1] < cols[-3]]
    groups = sorted(sorted(groups, key=len, reverse=True)[:2])
    tire, tread = T("tire", 0.8), T("tread", 0.9, "REPEAT")
    for g in groups[:2]:
        yc = Y((g[0] + g[-1]) / 2)
        for side in (-1, 1):
            wheel(side * (width / 2 - 0.13), yc, 0.355, 0.22, tread, tire, outer_sign=side)
    # Shadowed underside so the gap above the road isn't see-through.
    box((width - 0.2, length - 1.0, 0.12), (0, 0, clearance + 0.06), M.plain((0.04, 0.04, 0.04), 0.9, edge=0), bevel=0.02)


# Every painted car sheet with the car_v1 layout becomes a prop here: prepare the
# sheet with tools/prepare_sheet.py IMAGE car_v1 NAME, then add one line.
# name -> (description, reference body sheet)
CARS = {
    "car_coupe": ("A 1972 'Statesman' two-door hardtop in faded green with a cream vinyl roof, rusting.", "car_coupe"),
    "car_coupe_yellow": ("A 'Statesman' hardtop in sun-faded harvest gold, rust bubbling through, brown vinyl roof.", "car_coupe"),
    "car_coupe_burnt": ("A burnt-out 'Statesman' hardtop: blistered paint, rust, glass gone, seats charred.", "car_coupe"),
}


def _register(name, desc, body):
    prop(name, tex=2048, tags=["exterior", "car"], desc=desc)(lambda: painted_car(name, body))


for _n, (_d, _b) in CARS.items():
    _register(_n, _d, _b)
