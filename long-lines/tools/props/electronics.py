"""Electronics and appliances small enough to carry."""
import math

from propkit import prop
from propkit import labels as L
from propkit import mats as M
from propkit.core import box, cyl, floor_box, label_card, lathe, planar_uv, rod, round_y_edges, smooth, squircle, text, tube, mesh_obj, PARTS

import bmesh
import bpy

R90 = (math.radians(90), 0, 0)


def crt(w, h, loc, mat, bulge=0.016, nx=28, nz=22):
    """A curved rounded-rectangle CRT face, facing -Y."""
    bm = bmesh.new()
    grid = []
    for j in range(nz + 1):
        row = []
        for i in range(nx + 1):
            su, sw = squircle(i / nx * 2 - 1, j / nz * 2 - 1, 5.0)
            b = bulge * (1 - min(1.0, (su * su + sw * sw) * 0.9))
            row.append(bm.verts.new((su * w / 2, -b, sw * h / 2)))
        grid.append(row)
    for j in range(nz):
        for i in range(nx):
            bm.faces.new((grid[j][i], grid[j + 1][i], grid[j + 1][i + 1], grid[j][i + 1]))
    o = mesh_obj("crt", bm)
    o.location = loc
    o.data.materials.append(mat)
    return smooth(o, 80)


def frame_ring(w, h, depth, border, loc, mat, r_out=0.03, r_in=0.022):
    """A rounded rectangular frame (outer minus inner), facing -Y."""
    outer = box((w + border * 2, depth, h + border * 2), loc, mat, bevel=0)
    cut = box((w, depth * 4, h), loc, mat, bevel=0)
    round_y_edges(outer, r_out)
    round_y_edges(cut, r_in)
    b = outer.modifiers.new("cut", "BOOLEAN")
    b.object, b.operation, b.solver = cut, "DIFFERENCE", "EXACT"
    from propkit.core import apply_mods
    apply_mods(outer)
    bpy.data.objects.remove(cut)
    PARTS.remove(cut)
    m = outer.modifiers.new("soft", "BEVEL")
    m.width, m.segments, m.limit_method = 0.004, 2, "ANGLE"
    apply_mods(outer)
    return smooth(outer)


def dead_screen(name="screen"):
    """Green-grey dead CRT glass with a painted window reflection."""
    if M._cached(name):
        return M._cached(name)
    m, nt, bsdf, out = M._new(name)
    x = M.m_(nt, "MULTIPLY", M.axis_part(nt, "X"), 4.5, clamp=False)
    z = M.m_(nt, "MULTIPLY", M.axis_part(nt, "Z"), 5.5, clamp=False)
    rr = M.m_(nt, "ADD", M.m_(nt, "MULTIPLY", x, x, clamp=False), M.m_(nt, "MULTIPLY", z, z, clamp=False), clamp=False)
    base = M.mix(nt, M.m_(nt, "SUBTRACT", 1.0, rr), (0.035, 0.045, 0.042), (0.10, 0.125, 0.115))
    diag = M.m_(nt, "ADD", M.axis_part(nt, "X"), M.m_(nt, "MULTIPLY", M.axis_part(nt, "Z"), 0.8, clamp=False), clamp=False)
    band = M.m_(nt, "MULTIPLY", M.m_(nt, "GREATER_THAN", diag, -0.02), M.m_(nt, "LESS_THAN", diag, 0.05))
    band = M.m_(nt, "MULTIPLY", M.m_(nt, "MULTIPLY", band, M.m_(nt, "GREATER_THAN", M.axis_part(nt, "Z"), 0.03)), 0.35)
    col = M.mix(nt, band, base, (0.42, 0.48, 0.47))
    return M.register(name, m, bsdf, out, col, 0.06, 0.0)


@prop("tv", tex=2048, tags=["electronics", "living"], kind="fixture")
def tv():
    """1975 19-inch 'Westbury' colour TV on a tapered-leg stand, with rabbit ears and a doily."""
    walnut, alu, chrome, brass = M.wood("walnut"), M.metal((0.62, 0.62, 0.6), 0.38, True, name="alu"), M.chrome(), M.brass()
    black = M.plain((0.025, 0.024, 0.023), 0.45, edge=0.12)
    bezel = M.plain((0.07, 0.065, 0.06), 0.35, edge=0.04, grime=0.3)
    grille = M.plain((0.11, 0.075, 0.05), 0.85, edge=0, grime=0.6, dust=0.4)
    hard = M.plain((0.17, 0.12, 0.08), 0.85, edge=0.05)
    rubber = M.plain((0.02, 0.02, 0.02), 0.8, edge=0)
    lamp = M.plain((0.35, 0.03, 0.02), 0.2, edge=0, grime=0, dust=0)
    dial = M.image(L.wrap_label("tv_dial_dummy", "", "", (196, 192, 180), (196, 192, 180), (120, 116, 108), w=256, h=256))
    top_z = 0.43
    floor_box((0.74, 0.46, 0.03), z=top_z - 0.03, mat=walnut, bevel=0.008)
    floor_box((0.68, 0.40, 0.06), z=top_z - 0.09, mat=walnut)
    floor_box((0.62, 0.34, 0.018), z=0.121, mat=walnut)
    from mathutils import Euler, Vector
    for sx in (-1, 1):
        for sy in (-1, 1):
            rot = (-sy * math.radians(4.2), sx * math.radians(7), 0)
            ax = Euler(rot).to_matrix() @ Vector((0, 0, 1))
            top = Vector((sx * 0.3, sy * 0.17, top_z - 0.06))
            cyl(0.012, 0.37, tuple(top - ax * 0.185), walnut, 16, rot, r_top=0.021, bevel=0.002)
            cyl(0.0128, 0.03, tuple(top - ax * 0.358), brass, 16, rot, bevel=0.0015)
    W, D, H, Z0 = 0.68, 0.46, 0.50, top_z + 0.008
    for sx in (-1, 1):
        for sy in (-1, 1):
            cyl(0.016, 0.01, (sx * 0.28, sy * 0.18, top_z + 0.005), rubber, 12)
    box((W, D, H), (0, 0, Z0 + H / 2), walnut, bevel=0.028, segments=5)
    F = -D / 2
    box((0.62, 0.02, 0.44), (0, F - 0.009, Z0 + 0.25), bezel, bevel=0.006)
    F -= 0.019
    sw, sh, sx_, sz = 0.405, 0.315, -0.075, Z0 + 0.265
    frame_ring(sw, sh, 0.026, 0.025, (sx_, F - 0.013, sz), black)
    crt(sw, sh, (sx_, F - 0.002, sz), dead_screen())
    text("Westbury", 0.034, (sx_ - sw / 2 - 0.005, F - 0.001, Z0 + 0.034), chrome, align="LEFT")
    px = 0.225
    box((0.125, 0.012, 0.415), (px, F - 0.004, Z0 + 0.25), alu)
    cyl(0.045, 0.008, (px, F - 0.014, Z0 + 0.38), M.plain((0.75, 0.73, 0.68), 0.5), 48, R90, bevel=0.0015)
    for i in range(12):
        a = i * math.pi / 6
        box((0.003, 0.002, 0.008), (px + math.cos(a) * 0.036, F - 0.019, Z0 + 0.38 + math.sin(a) * 0.036), black, bevel=0.0005, rot=(0, -a, 0))
    cyl(0.024, 0.032, (px, F - 0.032, Z0 + 0.38), black, 40, R90, bevel=0.003, flutes=20)
    box((0.004, 0.006, 0.02), (px, F - 0.049, Z0 + 0.39), alu, bevel=0.0008)
    cyl(0.03, 0.006, (px, F - 0.012, Z0 + 0.275), chrome, 40, R90, bevel=0.0012)
    cyl(0.018, 0.026, (px, F - 0.026, Z0 + 0.275), black, 32, R90, bevel=0.002, flutes=16)
    for z in (0.195, 0.155, 0.115):
        cyl(0.0115, 0.02, (px - 0.02, F - 0.018, Z0 + z), black, 24, R90, bevel=0.0015, flutes=12)
        box((0.006, 0.004, 0.0015), (px + 0.012, F - 0.011, Z0 + z), chrome, bevel=0.0004)
    cyl(0.004, 0.006, (px + 0.035, F - 0.012, Z0 + 0.195), lamp, 12, R90)
    for i in range(9):
        box((0.105, 0.006, 0.0045), (px, F - 0.011, Z0 + 0.045 + i * 0.0075), grille, bevel=0.001)
    box((W - 0.07, 0.01, H - 0.07), (0, D / 2 + 0.002, Z0 + H / 2), hard, bevel=0.002)
    for i in range(7):
        box((0.36, 0.012, 0.012), (0, D / 2 + 0.004, Z0 + H - 0.1 - i * 0.028), black, bevel=0.002)
    tops = Z0 + H
    doily = cyl(0.135, 0.002, (-0.12, -0.04, tops + 0.001), M.fabric((0.86, 0.83, 0.74), (0.5, 0.45, 0.38), "floral", 60, name="lace"), 72)
    ax, ay = 0.16, 0.06
    cyl(0.055, 0.03, (ax, ay, tops + 0.015), walnut, 32, r_top=0.04, bevel=0.006)
    cyl(0.03, 0.02, (ax, ay, tops + 0.038), chrome, 24, bevel=0.004)
    for side in (-1, 1):
        d = Vector((math.sin(math.radians(32) * side), math.sin(math.radians(14)), math.cos(math.radians(32)))).normalized()
        s = Vector((ax + side * 0.012, ay, tops + 0.045))
        t = 0.0
        for r, l in ((0.0042, 0.2), (0.0034, 0.2), (0.0026, 0.18)):
            rod(s + d * t, s + d * (t + l), r, chrome, 10)
            t += l - 0.01
        cyl(0.006, 0.012, tuple(s + d * (t + 0.008)), chrome, 12)
    pts = [(ax + math.cos(a) * 0.07, ay - 0.03, tops + 0.1 + math.sin(a) * 0.07) for a in [i * math.pi / 20 for i in range(41)]]
    tube(pts, 0.0028, chrome)
    box((0.006, 0.006, 0.04), (ax, ay - 0.03, tops + 0.02), chrome, bevel=0.002)


@prop("radio_transistor", tex=512, tags=["electronics", "carry"], kind="carry")
def radio_transistor():
    """A battery transistor radio in a teal leatherette case with a chrome grille."""
    case = M.plain((0.13, 0.27, 0.28), 0.55, edge=0.3)
    chrome, black = M.chrome(), M.plain((0.03, 0.03, 0.03), 0.4)
    box((0.24, 0.07, 0.15), (0, 0, 0.075), case, bevel=0.018, segments=4)
    box((0.12, 0.004, 0.11), (-0.05, -0.036, 0.075), M.metal((0.7, 0.7, 0.68), 0.35, True, name="alu"), bevel=0.003)
    for i in range(9):
        box((0.1, 0.006, 0.003), (-0.05, -0.039, 0.033 + i * 0.0105), black, bevel=0.0008)
    box((0.08, 0.004, 0.04), (0.065, -0.036, 0.1), M.plain((0.85, 0.8, 0.66), 0.4), bevel=0.003)
    for i in range(7):
        box((0.0015, 0.002, 0.012), (0.035 + i * 0.01, -0.039, 0.1), black, bevel=0.0003)
    cyl(0.018, 0.016, (0.065, -0.042, 0.042), chrome, 24, R90, bevel=0.002, flutes=14)
    tube([(-0.1, 0.0, 0.15), (-0.1, 0.0, 0.19), (0.1, 0.0, 0.19), (0.1, 0.0, 0.15)], 0.005, chrome)
    text("SKYLINER", 0.012, (0.065, -0.039, 0.125), chrome)


@prop("record_player", tex=1024, tags=["electronics", "living"], kind="fixture")
def record_player():
    """A portable suitcase record player, lid up, a record on the platter."""
    case = M.fabric((0.55, 0.12, 0.1), (0.45, 0.1, 0.08), "tweed", 30)
    cream, chrome, black = M.plain((0.86, 0.82, 0.7), 0.4), M.chrome(), M.plain((0.03, 0.03, 0.03), 0.3)
    floor_box((0.38, 0.3, 0.11), mat=case, bevel=0.012)
    floor_box((0.36, 0.28, 0.008), z=0.11, mat=cream, bevel=0.003)
    cyl(0.135, 0.008, (-0.04, 0.0, 0.122), M.plain((0.2, 0.2, 0.2), 0.5), 48)
    cyl(0.152, 0.003, (-0.04, 0.0, 0.128), black, 64)
    cyl(0.045, 0.0035, (-0.04, 0.0, 0.13), M.plain((0.8, 0.25, 0.15), 0.6), 32)
    cyl(0.003, 0.018, (-0.04, 0.0, 0.135), chrome, 8)
    rod((0.15, 0.1, 0.13), (0.03, -0.06, 0.135), 0.004, chrome)
    box((0.02, 0.03, 0.012), (0.03, -0.065, 0.135), black, bevel=0.003)
    cyl(0.015, 0.02, (0.15, 0.1, 0.125), chrome, 16)
    box((0.38, 0.05, 0.3), (0, 0.17, 0.25), case, bevel=0.012, rot=(math.radians(-12), 0, 0))
    cyl(0.012, 0.012, (0.14, -0.1, 0.12), black, 16, bevel=0.002, flutes=10)


@prop("phone_desk", tex=512, tags=["electronics", "office"], kind="fixture")
def phone_desk():
    """A black rotary desk telephone."""
    body = M.plain((0.03, 0.03, 0.032), 0.25, edge=0.2)
    chrome = M.chrome()
    lathe([(0.11, 0.0), (0.105, 0.03), (0.08, 0.075), (0.0, 0.08)], mat=body, verts=40).scale = (1, 0.85, 1)
    cyl(0.045, 0.012, (0, -0.07, 0.065), chrome, 32, (math.radians(60), 0, 0))
    cyl(0.025, 0.014, (0, -0.072, 0.067), M.plain((0.9, 0.88, 0.8), 0.3), 24, (math.radians(60), 0, 0))
    for side in (-1, 1):
        box((0.03, 0.03, 0.03), (side * 0.07, 0, 0.085), body, bevel=0.01)
    hs = box((0.2, 0.035, 0.03), (0, 0.0, 0.105), body, bevel=0.012)
    for side in (-1, 1):
        cyl(0.028, 0.035, (side * 0.095, 0, 0.1), body, 20, bevel=0.008)
    tube([(0.11, 0.03, 0.03), (0.15, 0.06, 0.01), (0.2, 0.05, 0.004)], 0.004, body)


@prop("typewriter", tex=1024, tags=["office"], kind="fixture")
def typewriter():
    """A heavy office manual typewriter, a half-typed letter in the roller."""
    body = M.plain((0.12, 0.16, 0.14), 0.4, edge=0.35)
    black, chrome = M.plain((0.03, 0.03, 0.03), 0.35), M.chrome()
    box((0.42, 0.34, 0.1), (0, 0, 0.05), body, bevel=0.03, segments=4)
    box((0.38, 0.14, 0.06), (0, 0.06, 0.13), body, bevel=0.025, segments=4)
    cyl(0.025, 0.46, (0, 0.1, 0.18), black, 24, (0, math.radians(90), 0), bevel=0.004)
    for side in (-1, 1):
        cyl(0.018, 0.02, (side * 0.24, 0.1, 0.18), chrome, 20, (0, math.radians(90), 0), bevel=0.003, flutes=12)
    paper = box((0.2, 0.002, 0.16), (0, 0.12, 0.26), M.image(L.newspaper("typed_letter", "Dear Terry,", masthead="", sub="I keep meaning to call...")), bevel=0)
    planar_uv(paper, 0, 2, 0.2, 0.16)
    for row in range(4):
        for i in range(11 - (row % 2)):
            x = -0.15 + i * 0.03 + (row % 2) * 0.015
            cyl(0.0095, 0.012, (x, -0.1 + row * 0.03, 0.105 + row * 0.012), black, 12, (math.radians(-15), 0, 0))
            cyl(0.008, 0.002, (x, -0.1 + row * 0.03, 0.112 + row * 0.012), M.plain((0.85, 0.83, 0.75), 0.3), 12, (math.radians(-15), 0, 0))
    box((0.2, 0.025, 0.012), (0, -0.16, 0.09), black, bevel=0.005)
    rod((-0.2, 0.06, 0.17), (-0.26, -0.02, 0.2), 0.004, chrome)


@prop("desk_fan", tex=512, tags=["office", "electronics"], kind="carry")
def desk_fan():
    """An oscillating desk fan with a chrome cage."""
    green, chrome = M.plain((0.36, 0.45, 0.4), 0.4, edge=0.3), M.chrome()
    cyl(0.09, 0.03, (0, 0, 0.015), green, 32, bevel=0.01)
    cyl(0.012, 0.16, (0, 0, 0.11), chrome, 12)
    box((0.08, 0.1, 0.08), (0, 0.02, 0.21), green, bevel=0.03)
    for a in range(16):
        ang = a * math.pi / 8
        tube([(math.cos(ang) * 0.13 * t, -0.05 - math.sin(t * math.pi) * 0.025, 0.21 + math.sin(ang) * 0.13 * t) for t in (0.1, 0.5, 1.0)] , 0.0015, chrome, 4)
    for r in (0.13, 0.07):
        tube([(math.cos(i * math.pi / 16) * r, -0.05, 0.21 + math.sin(i * math.pi / 16) * r) for i in range(33)], 0.002, chrome, 4)
    for b in range(3):
        box((0.045, 0.004, 0.09), (0, -0.04, 0.21), M.plain((0.4, 0.5, 0.45), 0.4), bevel=0.01, rot=(0, b * 2.094, 0))


@prop("alarm_clock", tex=512, tags=["bedroom", "carry"], kind="carry")
def alarm_clock():
    """A wind-up twin-bell alarm clock, stopped."""
    chrome, face = M.chrome(), M.image(L.painting("clock_face_img", "landscape", 256, 256, seed=9))
    red = M.plain((0.6, 0.1, 0.08), 0.35, edge=0.3)
    cyl(0.055, 0.035, (0, 0, 0.07), red, 32, R90, bevel=0.006)
    c = cyl(0.046, 0.002, (0, -0.0185, 0.07), M.plain((0.92, 0.9, 0.82), 0.3), 32, R90)
    for i in range(12):
        a = i * math.pi / 6
        box((0.002, 0.001, 0.006), (math.cos(a) * 0.038, -0.02, 0.07 + math.sin(a) * 0.038), M.plain((0.05, 0.05, 0.05), 0.4), bevel=0, rot=(0, -a, 0))
    box((0.002, 0.001, 0.03), (0.005, -0.021, 0.08), M.plain((0.05, 0.05, 0.05), 0.4), bevel=0, rot=(0, -0.4, 0))
    for side in (-1, 1):
        lathe([(0.0, 0.0), (0.028, 0.0), (0.024, 0.018), (0.0, 0.022)], (side * 0.04, 0, 0.12), chrome, 24, (0, side * 0.5, 0))
        rod((side * 0.04, 0, 0.03), (side * 0.035, 0, 0.0), 0.004, chrome)
    rod((-0.04, 0.0, 0.13), (0.04, 0.0, 0.13), 0.002, chrome)
