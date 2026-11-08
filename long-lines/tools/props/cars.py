"""Three generic mid-1970s American cars (no real makes): built from one shared
car() routine, so new variants are a few parameters each."""
import math

import bmesh

from propkit import prop
from propkit import mats as M
from propkit.core import apply_mods, box, cyl, floor_box, mesh_obj, rod, smooth, text

RX = (0, math.radians(90), 0)


def shaped(size, loc, mat, front_in=0.0, back_in=0.0, side_in=0.0, bevel=0.04):
    """A box whose top face is pulled in at the front (-Y), back and sides:
    windscreens, rear windows, tumblehome."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        x, y, z = v.co.x * size[0], v.co.y * size[1], v.co.z * size[2]
        if v.co.z > 0:
            y += front_in if v.co.y < 0 else -back_in
            x *= 1 - side_in
        v.co = (x, y, z)
    o = mesh_obj("shaped", bm)
    o.location = loc
    o.data.materials.append(mat)
    b = o.modifiers.new("b", "BEVEL")
    b.width, b.segments, b.limit_method = bevel, 3, "ANGLE"
    apply_mods(o)
    return smooth(o, 35)


def car(body_col, length=5.5, width=2.0, roof="body", wagon=False, taxi=False, whitewalls=False, quad_lamps=True):
    paint = M.paint(body_col, (0.45, 0.42, 0.38), chips=0.25, rough=0.35, name="carpaint_%.2f%.2f%.2f" % body_col)
    chrome, black = M.chrome(), M.plain((0.03, 0.03, 0.03), 0.6)
    glass = M.plain((0.06, 0.08, 0.09), 0.08, edge=0, grime=0.5, dust=0.6, name="car_glass")
    rubber = M.plain((0.04, 0.04, 0.04), 0.85, edge=0, dust=0.3, name="tire")
    L, W = length, width
    # Lower body: long hood, long deck.
    shaped((W, L, 0.62), (0, 0, 0.6), paint, front_in=0.06, back_in=0.04, bevel=0.07)
    # Cabin glass, then roof and pillars in body colour.
    cab_len = 2.6 if wagon else 2.2
    cab_y = 0.55 if wagon else 0.25
    shaped((W - 0.16, cab_len, 0.5), (0, cab_y, 1.16), glass, front_in=0.45, back_in=0.05 if wagon else 0.35, side_in=0.08, bevel=0.03)
    roof_len = cab_len - (0.5 if wagon else 0.85)
    roof_y = cab_y + (0.22 if wagon else 0.05)
    roof_mat = M.fabric((0.12, 0.07, 0.04), (0.08, 0.05, 0.03), "tweed", 30, rough=0.6, name="vinyl_roof") if roof == "vinyl" else paint
    shaped((W - 0.28, roof_len + 0.04, 0.06), (0, roof_y, 1.43), roof_mat, side_in=0.02, bevel=0.025)
    for side in (-1, 1):
        x = side * (W / 2 - 0.12)
        rod((x, cab_y - cab_len / 2 + 0.04, 0.93), (x * 0.94, roof_y - roof_len / 2, 1.42), 0.035, paint, 8)
        rod((x, cab_y - 0.05, 0.93), (x * 0.94, cab_y - 0.05, 1.42), 0.04, paint, 8)
        rod((x, cab_y + cab_len / 2 - 0.04, 0.93), (x * 0.94, roof_y + roof_len / 2, 1.42), 0.05 if not wagon else 0.035, paint, 8)
        if wagon:
            rod((x, cab_y + 0.75, 0.93), (x * 0.94, cab_y + 0.75, 1.42), 0.035, paint, 8)
        # Wheels
        for y in (-L / 2 + 0.95, L / 2 - 1.05):
            wx = side * (W / 2 - 0.12)
            cyl(0.36, 0.23, (wx, y, 0.36), rubber, 28, RX, bevel=0.05)
            if whitewalls:
                cyl(0.27, 0.235, (wx, y, 0.36), M.plain((0.86, 0.85, 0.8), 0.6, dust=0.4, name="whitewall"), 28, RX)
            cyl(0.19, 0.24, (wx, y, 0.36), chrome, 24, RX, bevel=0.03)
            cyl(0.05, 0.25, (wx, y, 0.36), black, 12, RX)
        # Side trim and door seams
        box((0.01, L - 0.5, 0.03), (side * (W / 2 + 0.002), 0.0, 0.78), chrome, bevel=0.005)
        for y in (cab_y - 0.05, cab_y - cab_len / 2 + 0.02, cab_y + 0.95 if not wagon else cab_y + 0.75):
            box((0.008, 0.008, 0.55), (side * (W / 2 + 0.001), y, 0.62), black, bevel=0.002)
        box((0.03, 0.08, 0.025), (side * (W / 2 - 0.02), cab_y - 0.05 - 0.25, 0.86), chrome, bevel=0.006)
        box((0.06, 0.08, 0.06), (side * (W / 2 + 0.03), cab_y - cab_len / 2 + 0.1, 1.0), chrome, bevel=0.015)
        if wagon:
            box((0.012, 3.6, 0.38), (side * (W / 2 + 0.004), 0.45, 0.6), M.wood("oak", "Y", name="wagon_wood"), bevel=0.004)
            box((0.016, 3.62, 0.03), (side * (W / 2 + 0.008), 0.45, 0.8), M.plain((0.75, 0.68, 0.5), 0.5), bevel=0.004)
            box((0.016, 3.62, 0.03), (side * (W / 2 + 0.008), 0.45, 0.4), M.plain((0.75, 0.68, 0.5), 0.5), bevel=0.004)
            rod((side * 0.7, roof_y - roof_len / 2 + 0.1, 1.5), (side * 0.7, roof_y + roof_len / 2 - 0.05, 1.5), 0.015, chrome)
    # Front: grille, lamps, bumper.
    fy = -L / 2
    box((W - 0.5, 0.05, 0.26), (0, fy - 0.005, 0.68), black, bevel=0.01)
    for i in range(10):
        box((0.01, 0.06, 0.24), (-0.7 + i * 0.155, fy - 0.01, 0.68), chrome, bevel=0.003)
    box((W - 0.48, 0.06, 0.03), (0, fy - 0.01, 0.82), chrome, bevel=0.01)
    lamps = (-0.82, -0.62, 0.62, 0.82) if quad_lamps else (-0.75, 0.75)
    for x in lamps:
        cyl(0.085, 0.04, (x, fy - 0.01, 0.7), chrome, 20, (math.radians(90), 0, 0))
        cyl(0.07, 0.045, (x, fy - 0.012, 0.7), M.plain((0.85, 0.85, 0.78), 0.1, edge=0, name="lamp_glass"), 20, (math.radians(90), 0, 0))
    box((W + 0.04, 0.16, 0.16), (0, fy - 0.06, 0.45), chrome, bevel=0.05)
    box((0.22, 0.02, 0.11), (0, fy - 0.145, 0.45), M.plain((0.9, 0.88, 0.8), 0.5), bevel=0.004)
    # Back: lamps, bumper, plate.
    by = L / 2
    for x in (-0.75, 0.75):
        box((0.42, 0.04, 0.16), (x, by + 0.005, 0.72), M.plain((0.45, 0.04, 0.03), 0.2, edge=0.2, name="taillight"), bevel=0.01)
    box((W + 0.04, 0.16, 0.16), (0, by + 0.06, 0.45), chrome, bevel=0.05)
    box((0.32, 0.02, 0.16), (0, by + 0.145, 0.62), M.plain((0.92, 0.75, 0.2), 0.5, name="plate_ny"), bevel=0.004)
    text("8B-4471" if not taxi else "4R27", 0.07, (0, by + 0.158, 0.59), M.plain((0.08, 0.08, 0.2), 0.5), rot=(math.radians(90), 0, math.radians(180)))
    if taxi:
        box((0.6, 0.25, 0.16), (0, roof_y, 1.54), M.plain((0.92, 0.88, 0.7), 0.3, name="taxi_sign"), bevel=0.04)
        text("TAXI", 0.11, (0, roof_y - 0.13, 1.5), M.plain((0.1, 0.08, 0.05), 0.4), )
        for side in (-1, 1):
            text("4R27", 0.12, (side * (W / 2 + 0.006), cab_y + 0.4, 0.62), M.plain((0.08, 0.08, 0.08), 0.5),
                 rot=(math.radians(90), 0, math.radians(-90 * side)))
            box((0.006, 1.6, 0.06), (side * (W / 2 + 0.004), cab_y, 0.68), M.plain((0.06, 0.06, 0.06), 0.5), bevel=0.002)


@prop("car_sedan", tex=2048, tags=["exterior", "car"])
def car_sedan():
    """A full-size 1970s four-door sedan in copper brown with a vinyl roof and whitewalls."""
    car((0.32, 0.17, 0.08), roof="vinyl", whitewalls=True)


@prop("car_taxi", tex=2048, tags=["exterior", "car"])
def car_taxi():
    """A yellow city taxi with a roof light and medallion number."""
    car((0.85, 0.62, 0.1), length=5.3, quad_lamps=False, taxi=True)


@prop("car_wagon", tex=2048, tags=["exterior", "car"])
def car_wagon():
    """An avocado-green station wagon with woodgrain sides and a roof rack."""
    car((0.3, 0.36, 0.15), length=5.6, wagon=True, whitewalls=True)
