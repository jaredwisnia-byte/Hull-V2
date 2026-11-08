"""Kitchen and bathroom fixtures and wares."""
import math
import random

from propkit import prop
from propkit import labels as L
from propkit import mats as M
from propkit.core import box, cushion, cyl, floor_box, jitter, lathe, planar_uv, rod, round_y_edges, sag, tube, wrap_uv

R90 = (math.radians(90), 0, 0)
ENAMEL = lambda: M.plain((0.9, 0.87, 0.78), 0.3, edge=0.25, grime=0.45, name="enamel")
CREAM = lambda: M.plain((0.88, 0.83, 0.68), 0.3, edge=0.25, grime=0.45, name="enamel_cream")


@prop("fridge_50s", tex=1024, tags=["kitchen", "appliance"], kind="container")
def fridge_50s():
    """A round-shouldered 1950s refrigerator, cream enamel gone yellow, chrome lever handle."""
    e, chrome, black = CREAM(), M.chrome(), M.plain((0.04, 0.04, 0.04), 0.5)
    b = box((0.72, 0.66, 1.5), (0, 0, 0.82), e, bevel=0.09, segments=6)
    box((0.68, 0.01, 0.012), (0, -0.333, 1.17), black, bevel=0.004)
    box((0.05, 0.05, 0.3), (0.27, -0.35, 0.95), chrome, bevel=0.02)
    box((0.09, 0.06, 0.05), (0.27, -0.36, 1.11), chrome, bevel=0.02)
    box((0.18, 0.012, 0.035), (0, -0.335, 1.45), chrome, bevel=0.006)
    box((0.62, 0.04, 0.07), (0, -0.315, 0.06), M.plain((0.1, 0.1, 0.1), 0.6), bevel=0.01)
    for x in (-0.28, 0.28):
        cyl(0.025, 0.06, (x, -0.25, 0.03), M.iron(), 12)


@prop("gas_range", tex=1024, tags=["kitchen", "appliance"], kind="fixture")
def gas_range():
    """A 1950s apartment gas range with a clock in the back panel and a towel on the oven door."""
    e, chrome, black, iron = ENAMEL(), M.chrome(), M.plain((0.03, 0.03, 0.03), 0.4), M.iron()
    floor_box((0.76, 0.62, 0.86), z=0.02, mat=e, bevel=0.025)
    floor_box((0.74, 0.6, 0.03), z=0.87, mat=e, bevel=0.008)
    box((0.76, 0.07, 0.32), (0, 0.275, 1.08), e, bevel=0.025)
    box((0.7, 0.02, 0.025), (0, 0.235, 1.22), chrome, bevel=0.008)
    cyl(0.055, 0.02, (0, 0.235, 1.08), M.plain((0.95, 0.93, 0.86), 0.3), 24, R90)
    box((0.74, 0.02, 0.1), (0, -0.31, 0.79), chrome, bevel=0.006)
    for i in range(5):
        cyl(0.022, 0.03, (-0.28 + i * 0.14, -0.33, 0.79), black, 16, R90, bevel=0.004, flutes=10)
    box((0.62, 0.02, 0.42), (0, -0.315, 0.5), e, bevel=0.015)
    box((0.34, 0.01, 0.16), (0, -0.327, 0.52), black, bevel=0.01)
    box((0.5, 0.035, 0.025), (0, -0.345, 0.69), chrome, bevel=0.01)
    box((0.62, 0.02, 0.14), (0, -0.315, 0.17), e, bevel=0.012)
    box((0.2, 0.03, 0.025), (0, -0.335, 0.2), chrome, bevel=0.01)
    floor_box((0.76, 0.6, 0.04), mat=black, bevel=0.01)
    towel = M.fabric((0.92, 0.9, 0.84), (0.7, 0.2, 0.15), "stripes", 30)
    t = box((0.22, 0.012, 0.28), (-0.12, -0.36, 0.56), towel, bevel=0.004)
    jitter(t, 0.003, 2)
    cushion((0.22, 0.05, 0.05), (-0.12, -0.35, 0.69), towel, puff=0.2)
    for x in (-0.18, 0.18):
        for y in (-0.12, 0.15):
            cyl(0.09, 0.01, (x, y, 0.905), chrome, 20)
            cyl(0.035, 0.016, (x, y, 0.91), iron, 12)
            box((0.2, 0.018, 0.016), (x, y, 0.92), iron, bevel=0.005)
            box((0.018, 0.2, 0.016), (x, y, 0.92), iron, bevel=0.005)


@prop("percolator", tex=512, tags=["kitchen", "carry"], kind="carry")
def percolator():
    """An aluminium stovetop percolator with a glass knob."""
    alu = M.metal((0.7, 0.7, 0.68), 0.35, name="alu_pot")
    lathe([(0.0, 0), (0.06, 0), (0.065, 0.02), (0.055, 0.2), (0.045, 0.22), (0.0, 0.225)], mat=alu, verts=24)
    lathe([(0.0, 0.22), (0.016, 0.22), (0.016, 0.25), (0.0, 0.26)], mat=M.glass((0.5, 0.45, 0.3)), verts=12)
    tube([(0.055, 0, 0.18), (0.09, 0, 0.17), (0.09, 0, 0.05), (0.056, 0, 0.04)], 0.009, M.plain((0.05, 0.05, 0.05), 0.5), 8)
    rod((-0.05, 0, 0.12), (-0.09, 0, 0.19), 0.008, alu)


@prop("toaster", tex=512, tags=["kitchen", "appliance"])
def toaster():
    """A rounded chrome two-slice toaster."""
    chrome, black = M.chrome(), M.plain((0.03, 0.03, 0.03), 0.4)
    box((0.28, 0.16, 0.18), (0, 0, 0.1), chrome, bevel=0.06, segments=6)
    for x in (-0.05, 0.05):
        box((0.03, 0.12, 0.01), (x, 0, 0.19), black, bevel=0.004)
    box((0.02, 0.03, 0.05), (0.15, 0, 0.12), black, bevel=0.008)
    floor_box((0.3, 0.17, 0.02), mat=black, bevel=0.006)


@prop("dish_rack", tex=1024, tags=["kitchen"])
def dish_rack():
    """A coated-wire dish rack with plates, a cup and a glass drying."""
    wire, plate = M.plain((0.85, 0.85, 0.82), 0.3, edge=0), M.plain((0.92, 0.9, 0.84), 0.2, edge=0.2, name="china")
    for x in (-0.2, 0.2):
        tube([(x, -0.15, 0.01), (x, -0.15, 0.1), (x, 0.15, 0.1), (x, 0.15, 0.01)], 0.003, wire, 4)
    for i in range(9):
        y = -0.14 + i * 0.035
        rod((-0.2, y, 0.02), (0.2, y, 0.02), 0.0025, wire, 4)
        tube([(-0.12, y, 0.02), (-0.12, y, 0.08)], 0.0025, wire, 4)
    for i in range(5):
        cyl(0.11, 0.012, (-0.02, -0.1 + i * 0.04, 0.12), plate, 32, (math.radians(80), 0, 0))
    lathe([(0, 0), (0.035, 0), (0.042, 0.08), (0.038, 0.08), (0.03, 0.005), (0, 0.005)], (0.15, 0.05, 0.03), M.glass((0.5, 0.55, 0.5)), 16)


@prop("pot", tex=512, tags=["kitchen", "carry"], kind="carry")
def pot():
    """A dented aluminium saucepan with a black handle."""
    alu = M.metal((0.68, 0.68, 0.66), 0.4, name="alu_pot")
    lathe([(0.0, 0.002), (0.09, 0.0), (0.095, 0.01), (0.095, 0.11), (0.1, 0.115), (0.093, 0.115), (0.088, 0.012), (0.0, 0.012)], mat=alu, verts=32)
    box((0.16, 0.025, 0.018), (0.17, 0, 0.1), M.plain((0.04, 0.03, 0.03), 0.5), bevel=0.008)


@prop("frying_pan", tex=512, tags=["kitchen", "carry"], kind="carry")
def frying_pan():
    """A black cast-iron skillet."""
    iron = M.iron()
    lathe([(0.0, 0.0), (0.12, 0.0), (0.135, 0.04), (0.128, 0.042), (0.115, 0.006), (0.0, 0.006)], mat=iron, verts=32)
    box((0.15, 0.03, 0.02), (0.2, 0, 0.035), iron, bevel=0.008, rot=(0, -0.15, 0))


@prop("mug", tex=256, tags=["kitchen", "carry", "small"], kind="carry")
def mug():
    """A diner mug, coffee ring inside."""
    c = M.plain((0.9, 0.88, 0.8), 0.2, edge=0.2, name="china")
    lathe([(0, 0), (0.038, 0), (0.042, 0.095), (0.037, 0.095), (0.033, 0.008), (0, 0.008)], mat=c, verts=24)
    cyl(0.034, 0.002, (0, 0, 0.012), M.plain((0.18, 0.1, 0.05), 0.2, edge=0), 24)
    tube([(0.04, 0, 0.075), (0.065, 0, 0.07), (0.065, 0, 0.03), (0.04, 0, 0.025)], 0.007, c, 8)


@prop("plate_stack", tex=256, tags=["kitchen", "small"])
def plate_stack():
    """A stack of everyday plates."""
    c = M.plain((0.92, 0.9, 0.84), 0.2, edge=0.2, name="china")
    for i in range(6):
        lathe([(0, 0), (0.07, 0), (0.12, 0.018), (0.12, 0.02), (0, 0.02)], (0.002 * (i % 2), 0, i * 0.016), c, 32)


@prop("canisters", tex=512, tags=["kitchen"])
def canisters():
    """A set of tin canisters: flour, sugar, coffee, tea."""
    for i, (r, h) in enumerate(((0.07, 0.2), (0.062, 0.17), (0.055, 0.14), (0.048, 0.11))):
        tin = M.paint((0.62, 0.12, 0.08), (0.7, 0.7, 0.68), chips=0.7, rough=0.35, name="tin_red")
        x = -0.2 + sum((0.14, 0.124, 0.11, 0.096)[:i]) + r
        cyl(r, h, (x, 0, h / 2), tin, 28, bevel=0.003)
        cyl(r * 0.98, 0.02, (x, 0, h + 0.008), M.chrome(), 28, bevel=0.003)
        cyl(0.012, 0.012, (x, 0, h + 0.022), M.plain((0.05, 0.05, 0.05), 0.4), 12)
        box((r * 1.1, 0.002, h * 0.25), (x, -r + 0.001, h * 0.55), M.paper((0.9, 0.86, 0.74)), bevel=0.0005)


@prop("sink_cabinet", tex=1024, tags=["kitchen"], kind="fixture")
def sink_cabinet():
    """A painted base cabinet with an enamel top and sink, gooseneck faucet, dishes in the basin."""
    paint, e, chrome = M.paint((0.86, 0.84, 0.76), chips=0.5, name="cabinet_paint"), ENAMEL(), M.chrome()
    floor_box((0.96, 0.56, 0.84), y=0.02, z=0.05, mat=paint, bevel=0.012)
    floor_box((0.9, 0.5, 0.06), y=0.04, mat=M.plain((0.05, 0.05, 0.05), 0.6))
    for x in (-0.235, 0.235):
        box((0.44, 0.025, 0.52), (x, -0.265, 0.38), paint, bevel=0.01)
        box((0.34, 0.012, 0.42), (x, -0.28, 0.38), paint, bevel=0.006)
        box((0.02, 0.03, 0.07), (x + (0.17 if x < 0 else -0.17), -0.29, 0.52), chrome, bevel=0.008)
    box((0.9, 0.025, 0.12), (0, -0.265, 0.74), paint, bevel=0.01)
    floor_box((1.0, 0.6, 0.045), z=0.87, mat=e, bevel=0.015)
    floor_box((0.96, 0.03, 0.12), y=0.285, z=0.91, mat=e, bevel=0.01)
    floor_box((0.5, 0.36, 0.012), 0.05, -0.03, 0.905, mat=chrome, bevel=0.03)
    floor_box((0.44, 0.3, 0.01), 0.05, -0.03, 0.909, mat=M.plain((0.12, 0.12, 0.12), 0.3))
    cyl(0.016, 0.22, (0.05, 0.22, 1.02), chrome, 10)
    tube([(0.05, 0.22, 1.12), (0.05, 0.2, 1.16), (0.05, 0.12, 1.15), (0.05, 0.08, 1.1)], 0.012, chrome, 10)
    for x in (-0.08, 0.18):
        cyl(0.02, 0.05, (x, 0.22, 0.94), chrome, 8)
        box((0.07, 0.015, 0.012), (x, 0.22, 0.97), chrome, bevel=0.005)
    c = M.plain((0.92, 0.9, 0.84), 0.2, edge=0.2, name="china")
    for i in range(3):
        cyl(0.1, 0.012, (0.02 + i * 0.01, -0.05, 0.925 + i * 0.013), c, 28, (0.15, 0.1 * i, 0))
    lathe([(0, 0), (0.038, 0), (0.042, 0.095), (0.037, 0.095), (0.033, 0.008), (0, 0.008)], (0.15, 0.03, 0.915), c, 20, (1.3, 0, 0.4))


@prop("wall_cabinet", tex=1024, tags=["kitchen"], kind="container")
def wall_cabinet():
    """Painted wooden wall cabinets, three doors with raised panels."""
    paint, chrome = M.paint((0.86, 0.84, 0.76), chips=0.5, name="cabinet_paint"), M.chrome()
    floor_box((1.6, 0.32, 0.72), mat=paint, bevel=0.01)
    floor_box((1.66, 0.36, 0.05), y=-0.01, z=0.72, mat=paint, bevel=0.012)
    for i in range(3):
        x = -0.53 + i * 0.53
        box((0.5, 0.02, 0.66), (x, -0.17, 0.36), paint, bevel=0.008)
        box((0.38, 0.012, 0.52), (x, -0.183, 0.36), paint, bevel=0.006)
        box((0.02, 0.03, 0.07), (x + 0.19, -0.195, 0.12), chrome, bevel=0.008)


@prop("tub_claw", tex=1024, tags=["kitchen", "bath"], kind="fixture")
def tub_claw():
    """The kitchen bathtub on claw feet, with a board lid that serves as a counter."""
    e, iron, wood = ENAMEL(), M.iron(), M.wood("pine", "X")
    box((1.6, 0.74, 0.5), (0, 0, 0.36), e, bevel=0.12, segments=6)
    floor_box((1.64, 0.78, 0.05), z=0.58, mat=e, bevel=0.025)
    for x in (-0.66, 0.66):
        for y in (-0.26, 0.26):
            lathe([(0.0, 0.0), (0.05, 0.0), (0.035, 0.05), (0.045, 0.12), (0.03, 0.14)], (x, y, 0), iron, 12)
            for k in range(3):
                a = k * 2.1
                cyl(0.012, 0.03, (x + math.cos(a) * 0.04, y + math.sin(a) * 0.04, 0.012), iron, 8)
    for i in range(4):
        floor_box((1.66, 0.195, 0.035), y=-0.3 + i * 0.2, z=0.63, mat=wood, bevel=0.008)
    for x in (-0.6, 0.6):
        floor_box((0.05, 0.76, 0.02), x=x, z=0.665, mat=M.wood("oak", "Y"))


@prop("dinette_table", tex=1024, tags=["kitchen", "furniture"], kind="container")
def dinette_table():
    """A yellow formica and chrome dinette table with a cutlery drawer."""
    top, chrome = M.plain((0.86, 0.74, 0.36), 0.35, edge=0.3, name="formica"), M.chrome()
    floor_box((1.0, 0.7, 0.035), z=0.725, mat=top, bevel=0.025)
    floor_box((1.01, 0.71, 0.03), z=0.705, mat=chrome, bevel=0.012)
    floor_box((0.9, 0.6, 0.08), z=0.63, mat=chrome, bevel=0.01)
    box((0.36, 0.012, 0.06), (0, -0.305, 0.67), top, bevel=0.005)
    for x in (-0.44, 0.44):
        for y in (-0.29, 0.29):
            cyl(0.017, 0.72, (x, y, 0.36), chrome, 12)
            cyl(0.024, 0.02, (x, y, 0.01), M.plain((0.03, 0.03, 0.03), 0.6), 12)


@prop("dinette_chair", tex=512, tags=["kitchen", "furniture"])
def dinette_chair():
    """A chrome dinette chair, red vinyl seat split and taped."""
    vinyl, chrome = M.plain((0.55, 0.1, 0.08), 0.3, edge=0.5, name="vinyl_red"), M.chrome()
    sag(cushion((0.42, 0.42, 0.07), (0, 0, 0.47), vinyl, puff=0.15), 0.01)
    cushion((0.42, 0.06, 0.24), (0, 0.2, 0.78), vinyl, puff=0.15)
    box((0.12, 0.004, 0.03), (0.05, -0.05, 0.505), M.plain((0.6, 0.55, 0.45), 0.6), bevel=0.001, rot=(0, 0, 0.3))
    for x in (-0.18, 0.18):
        for y in (-0.18, 0.18):
            cyl(0.012, 0.44, (x, y, 0.22), chrome, 8)
        tube([(x, 0.18, 0.44), (x, 0.21, 0.66), (x, 0.21, 0.9)], 0.012, chrome, 8)


@prop("breadbox", tex=512, tags=["kitchen"], kind="container")
def breadbox():
    """A chrome roll-top breadbox with a red stripe."""
    chrome = M.chrome()
    box((0.38, 0.24, 0.2), (0, 0, 0.1), chrome, bevel=0.07, segments=6)
    box((0.3, 0.004, 0.025), (0, -0.121, 0.13), M.plain((0.6, 0.1, 0.08), 0.3), bevel=0.002)
    box((0.08, 0.02, 0.015), (0, -0.125, 0.07), M.plain((0.05, 0.05, 0.05), 0.4), bevel=0.006)


@prop("phone_wall", tex=512, tags=["kitchen", "electronics"], kind="fixture")
def phone_wall():
    """A harvest-gold rotary wall phone, the coiled cord stretched from use."""
    gold, chrome = M.plain((0.78, 0.62, 0.22), 0.3, edge=0.3), M.chrome()
    box((0.17, 0.09, 0.23), (0, -0.045, 0.115), gold, bevel=0.035, segments=5)
    box((0.055, 0.06, 0.22), (-0.11, -0.1, 0.125), gold, bevel=0.025)
    for z in (0.24, 0.01):
        box((0.065, 0.07, 0.05), (-0.11, -0.11, z), gold, bevel=0.022)
    cyl(0.05, 0.012, (0.015, -0.093, 0.1), chrome, 24, R90)
    cyl(0.022, 0.014, (0.015, -0.095, 0.1), M.plain((0.92, 0.9, 0.82), 0.3), 16, R90)
    for i in range(10):
        a = -0.4 + i * 0.5
        cyl(0.007, 0.016, (0.015 + math.cos(a) * 0.036, -0.097, 0.1 + math.sin(a) * 0.036), M.plain((0.05, 0.05, 0.05), 0.4), 8, R90)
    tube([(-0.115 + math.sin(t * 9) * 0.012, -0.12 + math.cos(t * 9) * 0.012, -0.02 - t * 0.5) for t in [i / 60 for i in range(61)]], 0.004, gold, 6)


@prop("medicine_cooler", tex=1024, tags=["kitchen", "carry", "story"], kind="carry")
def medicine_cooler():
    """Nick's red picnic cooler with a white lid, swing handle and a dial thermometer."""
    red, white, chrome = M.plain((0.6, 0.12, 0.09), 0.4, edge=0.5), M.plain((0.9, 0.88, 0.8), 0.35, edge=0.3), M.chrome()
    box((0.42, 0.3, 0.27), (0, 0, 0.135), red, bevel=0.04, segments=5)
    box((0.44, 0.32, 0.06), (0, 0, 0.3), white, bevel=0.025)
    for x in (-0.2, 0.2):
        box((0.025, 0.03, 0.07), (x, 0, 0.28), chrome, bevel=0.01)
    tube([(-0.2, 0, 0.3), (-0.2, 0, 0.42), (-0.17, 0, 0.44), (0.17, 0, 0.44), (0.2, 0, 0.42), (0.2, 0, 0.3)], 0.008, chrome, 8)
    box((0.14, 0.035, 0.03), (0, 0, 0.44), M.plain((0.05, 0.05, 0.05), 0.5), bevel=0.012)
    cyl(0.05, 0.015, (0.1, -0.155, 0.15), chrome, 24, R90)
    cyl(0.043, 0.017, (0.1, -0.157, 0.15), M.plain((0.95, 0.93, 0.86), 0.3), 24, R90)
    box((0.12, 0.004, 0.05), (-0.09, -0.151, 0.15), M.paper(), bevel=0.001)


@prop("toilet_hightank", tex=1024, tags=["bath"], kind="fixture")
def toilet_hightank():
    """A tenement water closet: high wooden tank, brass flush pipe, pull chain, wooden seat."""
    china, wood, brass = M.plain((0.9, 0.88, 0.82), 0.2, edge=0.2, name="china"), M.wood("oak", "X"), M.brass()
    lathe([(0.0, 0.0), (0.13, 0.0), (0.11, 0.08), (0.12, 0.25), (0.2, 0.38), (0.0, 0.38)], (0, -0.05, 0), china, 32).scale = (0.85, 1.25, 1)
    seat = lathe([(0.12, 0.38), (0.21, 0.385), (0.21, 0.405), (0.12, 0.405)], (0, -0.08, 0), wood, 32)
    seat.scale = (0.85, 1.15, 1)
    box((0.42, 0.04, 0.32), (0, 0.24, 0.62), wood, bevel=0.01, rot=(math.radians(-6), 0, 0))
    floor_box((0.5, 0.22, 0.26), y=0.12, z=1.9, mat=wood, bevel=0.01)
    floor_box((0.54, 0.24, 0.03), y=0.12, z=2.16, mat=wood, bevel=0.01)
    rod((0.0, 0.18, 1.9), (0.0, 0.18, 0.3), 0.022, brass)
    tube([(0.0, 0.18, 0.32), (0.0, 0.1, 0.28), (0.0, 0.02, 0.28)], 0.022, brass, 10)
    tube([(0.22, 0.05, 1.98), (0.22, 0.05, 1.3)], 0.003, brass, 4)
    lathe([(0.0, 1.22), (0.018, 1.22), (0.02, 1.27), (0.008, 1.3), (0.0, 1.3)], (0.22, 0.05, 0), wood, 12)


@prop("pedestal_sink", tex=1024, tags=["bath"], kind="fixture")
def pedestal_sink():
    """A small pedestal sink with separate hot and cold taps."""
    china, chrome = M.plain((0.9, 0.88, 0.82), 0.2, edge=0.2, name="china"), M.chrome()
    lathe([(0.0, 0.0), (0.13, 0.0), (0.09, 0.05), (0.07, 0.4), (0.12, 0.62), (0.0, 0.62)], mat=china, verts=24).scale = (1, 0.8, 1)
    box((0.56, 0.42, 0.14), (0, 0, 0.72), china, bevel=0.05, segments=5)
    floor_box((0.44, 0.28, 0.02), y=-0.02, z=0.775, mat=M.plain((0.65, 0.63, 0.58), 0.2))
    floor_box((0.56, 0.06, 0.08), y=0.18, z=0.79, mat=china, bevel=0.02)
    for x, col in ((-0.12, (0.6, 0.1, 0.1)), (0.12, (0.1, 0.2, 0.6))):
        cyl(0.018, 0.08, (x, 0.13, 0.82), chrome, 10)
        rod((x, 0.13, 0.85), (x, 0.06, 0.84), 0.01, chrome, 8)
        cyl(0.025, 0.015, (x, 0.13, 0.865), chrome, 4, flutes=0)
        cyl(0.01, 0.004, (x, 0.13, 0.875), M.plain(col, 0.3), 10)


@prop("medicine_cabinet", tex=1024, tags=["bath"], kind="container")
def medicine_cabinet():
    """A recessed medicine cabinet with a speckled mirror door."""
    paint = M.paint((0.86, 0.84, 0.76), chips=0.4, name="cabinet_paint")
    mirror = M.metal((0.75, 0.78, 0.8), 0.08, name="mirror")
    floor_box((0.42, 0.05, 0.56), mat=paint, bevel=0.01)
    box((0.36, 0.006, 0.48), (0, -0.028, 0.28), mirror, bevel=0.003)
    for i in range(14):
        rx, rz = (i * 37 % 34) / 100 - 0.17, (i * 53 % 46) / 100 + 0.05
        cyl(0.006 + (i % 3) * 0.003, 0.001, (rx, -0.032, rz), M.plain((0.25, 0.25, 0.22), 0.8, edge=0), 10, R90)
    box((0.02, 0.012, 0.05), (0.15, -0.035, 0.28), M.chrome(), bevel=0.005)


@prop("towel_bar", tex=512, tags=["bath"])
def towel_bar():
    """A chrome towel bar with a thin towel folded over it."""
    chrome, towel = M.chrome(), M.fabric((0.55, 0.7, 0.68), (0.45, 0.6, 0.58), "tweed", 80)
    for x in (-0.25, 0.25):
        cyl(0.02, 0.012, (x, -0.006, 0), chrome, 16, R90)
        rod((x, 0, 0), (x, -0.07, 0), 0.008, chrome)
    rod((-0.27, -0.07, 0), (0.27, -0.07, 0), 0.008, chrome)
    t = box((0.36, 0.02, 0.5), (0.0, -0.07, -0.2), towel, bevel=0.008)
    jitter(t, 0.004, 9)
    cushion((0.36, 0.03, 0.04), (0, -0.07, 0.01), towel, puff=0.2)
