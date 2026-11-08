"""Architectural kit: doors, radiators, pipes, fixtures, stairs, and modular
facade bays for building streets. Facade bays tile side by side and stack by
storey, so a whole block is built from a handful of parts.
"""
import math
import random

import bmesh
import bpy

from propkit import prop
from propkit import labels as L
from propkit import mats as M
from propkit.core import PARTS, apply_mods, box, cyl, floor_box, lathe, link, planar_uv, rod, smooth, text, tube

R90 = (math.radians(90), 0, 0)
STOREY = 3.0


def brick(name="brick_red", col1=(0.42, 0.17, 0.11), col2=(0.3, 0.12, 0.08), mortar=(0.55, 0.52, 0.46)):
    if M._cached(name):
        return M._cached(name)
    m, nt, bsdf, out = M._new(name)
    br = nt.nodes.new("ShaderNodeTexBrick")
    br.inputs["Scale"].default_value = 1.0
    br.inputs["Brick Width"].default_value = 0.215
    br.inputs["Row Height"].default_value = 0.075
    br.inputs["Mortar Size"].default_value = 0.01
    br.inputs["Color1"].default_value = (*col1, 1)
    br.inputs["Color2"].default_value = (*col2, 1)
    br.inputs["Mortar"].default_value = (*mortar, 1)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    comb = nt.nodes.new("ShaderNodeCombineXYZ")
    nt.links.new(tc.outputs["Object"], sep.inputs[0])
    nt.links.new(M.m_(nt, "ADD", sep.outputs["X"], sep.outputs["Y"], clamp=False), comb.inputs[0])
    nt.links.new(sep.outputs["Z"], comb.inputs[1])
    nt.links.new(comb.outputs[0], br.inputs["Vector"])
    soot = M.m_(nt, "MULTIPLY", M.noise(nt, 1.5, detail=6), 0.6)
    col = M.mix(nt, soot, br.outputs["Color"], (0.12, 0.1, 0.09))
    return M.register(name, m, bsdf, out, M.weathered(nt, col, 0.1, 0.6, 0.2), 0.85, 0.0, M.bump(nt, br.outputs["Fac"], -0.4, 0.004))


@prop("radiator_column", tex=1024, tags=["arch", "heat"], kind="fixture")
def radiator_column():
    """A cast-iron column radiator, silver paint over rust, a valve and a pipe to the floor."""
    paint = M.paint((0.62, 0.6, 0.55), (0.35, 0.2, 0.12), chips=0.8, rough=0.5, name="radiator_paint")
    for i in range(14):
        x = -0.42 + i * 0.065
        for y in (-0.05, 0.05):
            cyl(0.022, 0.78, (x, y, 0.48), paint, 12, bevel=0.006)
        for z in (0.1, 0.86):
            box((0.05, 0.14, 0.05), (x, 0, z), paint, bevel=0.018)
    for x in (-0.42, 0.42):
        for y in (-0.05, 0.05):
            cyl(0.024, 0.08, (x, y, 0.04), paint, 12, bevel=0.006)
    rod((0.48, 0, 0.12), (0.56, 0, 0.12), 0.018, paint)
    rod((0.56, 0, 0.12), (0.56, 0, -0.02), 0.018, paint)
    cyl(0.03, 0.05, (0.5, 0, 0.12), M.brass(), 12, (0, math.radians(90), 0))
    cyl(0.04, 0.01, (0.5, 0, 0.18), M.plain((0.05, 0.05, 0.05), 0.5), 12, flutes=8)


def panel_door(w, h, t, mat, knob_mat, name, glass=False):
    floor_box((w, t, h), mat=mat, bevel=0.004)
    for z0, z1 in ((0.12, h * 0.42), (h * 0.5, h - 0.12)):
        for side in (-1, 1):
            box((w * 0.34, 0.012, z1 - z0), (side * w * 0.2, -t / 2 - 0.004, (z0 + z1) / 2), mat, bevel=0.008)
            box((w * 0.34, 0.012, z1 - z0), (side * w * 0.2, t / 2 + 0.004, (z0 + z1) / 2), mat, bevel=0.008)
    for y in (-1, 1):
        cyl(0.028, 0.06, (w / 2 - 0.07, y * (t / 2 + 0.03), 0.95), knob_mat, 20, R90, bevel=0.01)
        cyl(0.03, 0.006, (w / 2 - 0.07, y * (t / 2 + 0.003), 0.95), knob_mat, 16, R90)


@prop("door_interior", tex=1024, tags=["arch", "door"])
def door_interior():
    """A four-panel interior door, decades of paint, a glass knob."""
    paint = M.paint((0.85, 0.82, 0.72), (0.4, 0.3, 0.2), chips=0.6, name="door_paint")
    panel_door(0.76, 2.0, 0.035, paint, M.glass((0.7, 0.72, 0.68)), "door")


@prop("door_casing", tex=512, tags=["arch", "door"])
def door_casing():
    """Moulded door casing for a 0.8 m by 2.05 m opening (both faces), with a threshold."""
    paint = M.paint((0.88, 0.85, 0.76), (0.45, 0.35, 0.25), chips=0.4, name="trim_paint")
    for y in (-0.07, 0.07):
        for x in (-0.44, 0.44):
            floor_box((0.08, 0.02, 2.09), x=x, y=y, mat=paint, bevel=0.006)
        floor_box((0.96, 0.025, 0.1), y=y, z=2.05, mat=paint, bevel=0.008)
    floor_box((0.82, 0.16, 0.012), mat=M.wood("oak", "X"), bevel=0.004)


@prop("door_entry_4a", tex=1024, tags=["arch", "door", "entrance"], kind="fixture")
def door_entry_4a():
    """The steel-clad apartment door: police lock bar, deadbolt, chain, peephole, brass 4A."""
    entry_door("4A")


@prop("door_entry_4b", tex=1024, tags=["arch", "door", "hall"])
def door_entry_4b():
    """A neighbour's apartment door across the landing."""
    entry_door("4B", police_lock=False)


def entry_door(number, police_lock=True):
    paint = M.paint((0.28, 0.22, 0.18), (0.55, 0.5, 0.45), chips=0.5, rough=0.4, name="door_brown")
    brass, chrome, iron = M.brass(), M.chrome(), M.iron()
    w, h, t = 0.9, 2.04, 0.05
    floor_box((w, t, h), mat=paint, bevel=0.006)
    for z0, z1 in ((0.15, 0.9), (1.05, 1.9)):
        box((w * 0.75, 0.01, z1 - z0), (0, -t / 2 - 0.005, (z0 + z1) / 2), paint, bevel=0.01)
    for y, s in ((-t / 2, -1), (t / 2, 1)):
        cyl(0.03, 0.05, (w / 2 - 0.08, y + s * 0.025, 0.95), brass, 20, R90, bevel=0.01)
        box((0.06, 0.008, 0.2), (w / 2 - 0.08, y + s * 0.004, 0.95), brass, bevel=0.003)
    cyl(0.025, 0.02, (w / 2 - 0.08, t / 2 + 0.01, 1.25), brass, 20, R90, bevel=0.005)
    box((0.08, 0.03, 0.12), (w / 2 - 0.08, t / 2 + 0.02, 1.25), brass, bevel=0.008)
    cyl(0.01, 0.008, (0, -t / 2 - 0.006, 1.55), brass, 16, R90)
    cyl(0.012, 0.012, (0, t / 2 + 0.006, 1.55), brass, 16, R90)
    text(number, 0.08, (0, -t / 2 - 0.006, 1.68), brass)
    box((0.1, 0.03, 0.025), (w / 2 - 0.12, t / 2 + 0.02, 1.45), chrome, bevel=0.006)
    tube([(w / 2 - 0.08, t / 2 + 0.03, 1.45), (w / 2 + 0.02, t / 2 + 0.06, 1.38), (w / 2 + 0.12, t / 2 + 0.03, 1.44)], 0.0035, chrome, 4)
    if police_lock:
        box((0.12, 0.05, 0.16), (0, t / 2 + 0.025, 1.05), iron, bevel=0.012)
        rod((0, t / 2 + 0.04, 1.05), (0.05, t / 2 + 0.25, 0.0), 0.012, iron)
        floor_box((0.08, 0.06, 0.03), y=t / 2 + 0.26, mat=iron)
    floor_box((w, 0.03, 0.025), y=t / 2 + 0.01, z=0.0, mat=M.plain((0.2, 0.18, 0.16), 0.6))


@prop("pipe_riser", tex=512, tags=["arch"])
def pipe_riser():
    """Steam and water risers running floor to ceiling in the corner, painted over."""
    paint = M.paint((0.86, 0.82, 0.7), (0.35, 0.22, 0.14), chips=0.6, name="pipe_paint")
    for x, r in ((0.0, 0.03), (0.09, 0.018)):
        cyl(r, 2.75, (x, 0, 1.375), paint, 14)
        for z in (0.02, 0.9, 1.8, 2.73):
            cyl(r + 0.008, 0.05, (x, 0, z), paint, 14, bevel=0.004)
    for z in (0.5, 2.3):
        tube([(-0.04, 0.0, z), (-0.04, 0.05, z), (0.13, 0.05, z), (0.13, 0.0, z)], 0.006, M.iron(), 6)


@prop("light_globe", tex=256, tags=["arch", "light"], kind="fixture")
def light_globe():
    """A milk-glass ceiling globe on a brass fitter. Origin at the ceiling."""
    brass = M.brass()
    cyl(0.08, 0.03, (0, 0, -0.015), brass, 20, bevel=0.005)
    lathe([(0.05, -0.03), (0.12, -0.08), (0.13, -0.16), (0.09, -0.26), (0.0, -0.28)], mat=M.plain((0.92, 0.9, 0.85), 0.2, edge=0, grime=0.5), verts=28)
    cyl(0.012, 0.03, (0, 0, -0.29), brass, 10)


@prop("light_bulb_chain", tex=256, tags=["arch", "light", "closet"], kind="fixture")
def light_bulb_chain():
    """A bare bulb in a porcelain socket with a pull chain. Origin at the ceiling."""
    cyl(0.05, 0.05, (0, 0, -0.025), M.plain((0.9, 0.88, 0.82), 0.3), 16, bevel=0.01)
    cyl(0.02, 0.04, (0, 0, -0.07), M.metal((0.7, 0.68, 0.6), 0.4, name="socket"), 12)
    lathe([(0.012, -0.09), (0.03, -0.12), (0.032, -0.16), (0.0, -0.18)], mat=M.glass((0.85, 0.82, 0.7)), verts=16)
    tube([(0.03, 0, -0.06), (0.032, 0, -0.5)], 0.0015, M.metal((0.7, 0.6, 0.35), 0.3, name="chainbrass"), 4)


@prop("switch_plate", tex=128, tags=["arch", "small"], kind="fixture")
def switch_plate():
    """A brass toggle switch plate."""
    floor_box((0.07, 0.008, 0.115), y=-0.004, mat=M.brass(), bevel=0.003)
    box((0.008, 0.02, 0.016), (0, -0.014, 0.06), M.plain((0.05, 0.05, 0.05), 0.4), bevel=0.003, rot=(0.3, 0, 0))


@prop("outlet", tex=128, tags=["arch", "small"])
def outlet():
    """A two-prong duplex outlet, painted over."""
    floor_box((0.07, 0.006, 0.115), y=-0.003, mat=M.paint((0.86, 0.82, 0.7), name="pipe_paint"), bevel=0.003)
    for z in (0.035, 0.08):
        cyl(0.015, 0.006, (0, -0.007, z), M.plain((0.25, 0.18, 0.12), 0.3), 16, R90)


@prop("stair_flight", tex=2048, tags=["arch", "hall"])
def stair_flight():
    """A tenement stair flight going down, worn treads, a turned newel and balusters.
    Origin at the top of the flight; it descends toward +Y, one storey."""
    wood, tread = M.wood("mahogany", "X"), M.wood("floor", "X")
    iron = M.iron()
    n = 15
    rise, run, w = STOREY / n, 0.25, 1.0
    for i in range(n):
        z = -(i + 1) * rise
        floor_box((w, run + 0.02, 0.035), 0, (i + 0.5) * run, z + rise - 0.035, mat=tread, bevel=0.01)
        floor_box((w, 0.02, rise), 0, i * run + run, z, mat=M.paint((0.35, 0.3, 0.25), name="riser_paint"))
    floor_box((0.08, n * run, 0.25), 0.54, n * run / 2, -STOREY, mat=M.paint((0.35, 0.3, 0.25), name="riser_paint"), rot=(math.atan2(STOREY, n * run), 0, 0))
    for i in range(n):
        z = -(i + 1) * rise + rise
        rod((0.48, (i + 0.5) * run, z), (0.48, (i + 0.5) * run, z + 0.85), 0.012, iron, 8)
    top, bot = (0.48, 0.0, 0.9), (0.48, n * run, -STOREY + 0.9)
    rod(top, bot, 0.03, wood, 12)
    lathe([(0.0, 0.0), (0.06, 0.0), (0.05, 0.2), (0.04, 0.9), (0.06, 1.0), (0.0, 1.05)], (0.48, -0.05, 0), wood, 16)


@prop("facade_bay", tex=2048, tags=["exterior", "facade"])
def facade_bay():
    """One storey, one window bay of a brick tenement front: 1.8 m wide, 3 m tall,
    a dark double-hung window with brownstone lintel and sill. Tiles side by side."""
    W, H = 1.8, STOREY
    br, stone = brick(), M.plain((0.42, 0.3, 0.24), 0.8, edge=0.3, grime=0.6, name="brownstone")
    trim, glass = M.paint((0.2, 0.18, 0.16), (0.4, 0.38, 0.35), chips=0.5, name="sash_dark"), M.plain((0.04, 0.05, 0.06), 0.1, edge=0, grime=0.3, name="glass_dark")
    ww, wh, wz = 0.9, 1.55, 0.8
    floor_box((W, 0.3, wz), y=0.15, mat=br, bevel=0.0)
    floor_box((W, 0.3, H - wz - wh), y=0.15, z=wz + wh, mat=br, bevel=0.0)
    for x in (-(W + ww) / 4, (W + ww) / 4):
        floor_box(((W - ww) / 2, 0.3, wh), x=x, y=0.15, z=wz, mat=br, bevel=0.0)
    floor_box((ww + 0.2, 0.12, 0.08), y=-0.02, z=wz - 0.08, mat=stone, bevel=0.012)
    floor_box((ww + 0.24, 0.1, 0.22), y=-0.01, z=wz + wh, mat=stone, bevel=0.012)
    floor_box((ww, 0.02, wh), y=0.12, z=wz, mat=glass, bevel=0.0)
    for z in (wz + 0.02, wz + wh / 2, wz + wh - 0.02):
        floor_box((ww, 0.05, 0.04), y=0.1, z=z - 0.02, mat=trim)
    for x in (-ww / 2 + 0.02, ww / 2 - 0.02, 0.0):
        floor_box((0.04 if x else 0.02, 0.05, wh), x=x, y=0.1, z=wz, mat=trim)
    rnd = random.Random(1)
    if rnd.random() < 2:
        floor_box((ww * 0.42, 0.012, wh * 0.3), x=-ww * 0.22, y=0.105, z=wz + wh * 0.62, mat=M.plain((0.8, 0.75, 0.6), 0.9, name="shade"))


@prop("facade_cornice", tex=1024, tags=["exterior", "facade"])
def facade_cornice():
    """A pressed-metal cornice with brackets, 1.8 m wide, for the top of a tenement front."""
    tin = M.paint((0.3, 0.27, 0.24), (0.35, 0.22, 0.14), chips=0.6, name="cornice_paint")
    floor_box((1.8, 0.3, 0.2), y=0.15, mat=brick(), bevel=0)
    floor_box((1.84, 0.5, 0.12), y=0.0, z=0.45, mat=tin, bevel=0.02)
    floor_box((1.82, 0.4, 0.25), y=0.05, z=0.2, mat=tin, bevel=0.02)
    for x in (-0.6, 0.0, 0.6):
        floor_box((0.1, 0.35, 0.35), x=x, y=-0.1, z=0.12, mat=tin, bevel=0.03)
    for i in range(18):
        floor_box((0.05, 0.06, 0.05), x=-0.85 + i * 0.1, y=-0.22, z=0.38, mat=tin, bevel=0.01)


@prop("storefront", tex=2048, tags=["exterior", "facade"])
def storefront():
    """A ground-floor shopfront, 3.6 m wide: big dark window, recessed door, painted sign."""
    W, H = 3.6, 3.6
    trim = M.paint((0.15, 0.25, 0.2), (0.45, 0.42, 0.38), chips=0.6, name="shop_green")
    glass = M.plain((0.03, 0.04, 0.05), 0.08, edge=0, grime=0.4, name="glass_dark")
    floor_box((W, 0.3, 0.45), y=0.15, mat=trim, bevel=0.01)
    floor_box((2.3, 0.04, 2.1), x=-0.55, y=0.08, z=0.45, mat=glass, bevel=0)
    for x in (-1.72, 0.62):
        floor_box((0.08, 0.15, 2.1), x=x, y=0.05, z=0.45, mat=trim)
    floor_box((1.0, 0.04, 2.3), x=1.25, y=0.6, z=0.0, mat=M.paint((0.28, 0.22, 0.18), name="door_brown"))
    floor_box((0.6, 0.02, 0.9), x=1.25, y=0.57, z=1.2, mat=glass)
    floor_box((W, 0.3, 0.2), y=0.1, z=2.55, mat=trim, bevel=0.01)
    sign = L.box_art("sign_pork", "ROSSI & SONS", "PORK STORE - SALUMERIA", (25, 60, 45), (235, 215, 150), (25, 60, 45), 1024, 192)
    s = box((W - 0.2, 0.04, 0.7), (0, -0.02, 3.15), M.image(sign, 0.5, grime=0.6), bevel=0.01)
    planar_uv(s, 0, 2, W - 0.2, 0.7)
    floor_box((W, 0.3, 0.15), y=0.15, z=3.45, mat=trim)
    for i in range(10):
        x = -1.5 + i * 0.3
        rod((x, -0.3, 2.45), (x + 0.15, -0.9, 2.2), 0.006, M.iron(), 4)
    box((3.2, 0.7, 0.02), (-0.2, -0.6, 2.32), M.fabric((0.45, 0.12, 0.1), (0.85, 0.8, 0.7), "stripes", 4), bevel=0.004, rot=(math.radians(-25), 0, 0))


@prop("streetlamp", tex=512, tags=["exterior", "street"])
def streetlamp():
    """A cast-iron city lamppost with a cobra head, dark."""
    iron = M.paint((0.12, 0.16, 0.13), (0.3, 0.2, 0.12), chips=0.5, rough=0.5, name="lamp_green")
    lathe([(0.0, 0.0), (0.16, 0.0), (0.15, 0.3), (0.1, 0.5), (0.08, 0.9), (0.06, 1.0)], mat=iron, verts=16)
    cyl(0.055, 6.4, (0, 0, 4.1), iron, 12, r_top=0.04)
    tube([(0, 0, 7.2), (0.2, 0, 7.6), (1.0, 0, 7.75), (1.6, 0, 7.7)], 0.04, iron, 8)
    box((0.55, 0.28, 0.16), (1.75, 0, 7.62), M.plain((0.5, 0.5, 0.48), 0.4, name="lamp_head"), bevel=0.06)
    box((0.42, 0.2, 0.02), (1.75, 0, 7.53), M.plain((0.75, 0.72, 0.6), 0.2, edge=0), bevel=0.01)


@prop("fire_hydrant", tex=512, tags=["exterior", "street"])
def fire_hydrant():
    """A squat New York fire hydrant, red paint flaking."""
    red = M.paint((0.55, 0.1, 0.07), (0.35, 0.25, 0.18), chips=0.8, rough=0.5, name="hydrant_red")
    lathe([(0.0, 0.0), (0.16, 0.0), (0.16, 0.04), (0.11, 0.06), (0.11, 0.5), (0.14, 0.52), (0.12, 0.6), (0.06, 0.68), (0.0, 0.7)], mat=red, verts=24)
    for a in (0, math.pi):
        cyl(0.05, 0.12, (math.cos(a) * 0.14, math.sin(a) * 0.14, 0.42), red, 16, (0, math.radians(90), a), bevel=0.01)
        cyl(0.06, 0.03, (math.cos(a) * 0.2, math.sin(a) * 0.2, 0.42), red, 8, (0, math.radians(90), a))
    cyl(0.025, 0.04, (0, 0, 0.71), red, 5)


@prop("trash_can_metal", tex=512, tags=["exterior", "street", "junk"])
def trash_can_metal():
    """A dented galvanised trash can, lid askew, garbage piling up."""
    galv = M.metal((0.6, 0.6, 0.58), 0.5, name="galv")
    lathe([(0.0, 0.0), (0.22, 0.0), (0.25, 0.68), (0.243, 0.68), (0.213, 0.01), (0.0, 0.01)], mat=galv, verts=28)
    for z in (0.15, 0.45):
        cyl(0.24, 0.02, (0, 0, z), galv, 28)
    lathe([(0.0, 0.0), (0.27, 0.0), (0.26, 0.03), (0.1, 0.07), (0.0, 0.08)], (0.05, 0.0, 0.68), galv, 28, (0.25, 0, 0))
    tube([(-0.25, 0.0, 0.55), (-0.29, 0, 0.58), (-0.29, 0, 0.5), (-0.25, 0, 0.47)], 0.01, galv, 6)
