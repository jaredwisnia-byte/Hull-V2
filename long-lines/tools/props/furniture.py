"""Furniture: the big pieces of a 1970s tenement flat, most of it second-hand."""
import math
import random

from mathutils import Euler, Vector

from propkit import prop
from propkit import labels as L
from propkit import mats as M
from propkit.core import box, cushion, cyl, floor_box, jitter, lathe, planar_uv, rod, sag, tube

R90 = (math.radians(90), 0, 0)


def leg(x, y, h, mat, r_bot=0.012, r_top=0.02, splay=6, z_top=None, cap=None):
    """A tapered, splayed mid-century leg hanging from (x, y, z_top)."""
    z_top = h if z_top is None else z_top
    sx, sy = (1 if x > 0 else -1), (1 if y > 0 else -1)
    rot = (-sy * math.radians(splay * 0.6), sx * math.radians(splay), 0)
    ax = Euler(rot).to_matrix() @ Vector((0, 0, 1))
    top = Vector((x, y, z_top))
    cyl(r_bot, h, tuple(top - ax * h / 2), mat, 16, rot, r_top=r_top, bevel=0.002)
    if cap:
        cyl(r_bot + 0.001, 0.025, tuple(top - ax * (h - 0.0125)), cap, 16, rot, bevel=0.0015)


def drawer_front(w, h, x, z, y, mat, pull, knob=False):
    box((w, 0.02, h), (x, y - 0.01, z), mat, bevel=0.006)
    if knob:
        cyl(0.012, 0.02, (x, y - 0.028, z), pull, 16, R90, bevel=0.003)
    else:
        box((min(0.12, w * 0.3), 0.012, 0.016), (x, y - 0.028, z), pull, bevel=0.005)


@prop("sofa_plaid", tex=2048, tags=["furniture", "living"])
def sofa_plaid():
    """A 1970s plaid three-seat sofa on stubby legs, cushions sagging, an afghan over the back."""
    plaid = M.painted("mat_upholstery_orange", rough=0.9, edge=0.05)
    wood = M.painted("mat_wood_walnut", rough=0.45)
    W, D = 2.0, 0.88
    floor_box((W - 0.1, D - 0.1, 0.22), z=0.1, mat=plaid, bevel=0.03)
    for x in (-0.86, 0.86):
        for y in (-0.33, 0.33):
            cyl(0.02, 0.1, (x, y, 0.05), wood, 12, r_top=0.026)
    for i, x in enumerate((-0.6, 0.0, 0.6)):
        c = cushion((0.62, 0.66, 0.16), (x, -0.08, 0.4), plaid, puff=0.12)
        sag(c, 0.025 + 0.015 * (i == 0))
        cushion((0.62, 0.2, 0.42), (x, 0.3, 0.62), plaid, puff=0.15, rot=(math.radians(-8), 0, 0))
    for x in (-0.94, 0.94):
        cushion((0.16, D, 0.5), (x, 0, 0.47), plaid, puff=0.1)
    floor_box((W - 0.06, 0.16, 0.56), y=0.38, z=0.3, mat=plaid, bevel=0.04)
    afghan = box((0.9, 0.04, 0.5), (0.45, 0.4, 0.72), M.fabric((0.62, 0.42, 0.18), (0.3, 0.42, 0.25), "floral", 14), bevel=0.012, rot=(math.radians(-60), 0, 0.05))
    jitter(afghan, 0.006, 3)


@prop("armchair_vinyl", tex=1024, tags=["furniture", "living"])
def armchair_vinyl():
    """A brown vinyl club chair, the arms worn pale where hands went."""
    vinyl = M.painted("mat_leather_tan", rough=0.4, edge=0.5, grime=0.5, dust=0.1)
    wood = M.painted("mat_wood_walnut", rough=0.45)
    floor_box((0.74, 0.74, 0.26), z=0.1, mat=vinyl, bevel=0.04)
    sag(cushion((0.52, 0.6, 0.13), (0, -0.04, 0.42), vinyl, puff=0.15), 0.02)
    cushion((0.56, 0.2, 0.5), (0, 0.29, 0.66), vinyl, puff=0.12, rot=(math.radians(-10), 0, 0))
    for x in (-0.31, 0.31):
        cushion((0.15, 0.76, 0.42), (x, 0.0, 0.42), vinyl, puff=0.1)
    for x in (-0.3, 0.3):
        for y in (-0.3, 0.3):
            cyl(0.02, 0.1, (x, y, 0.05), wood, 12, r_top=0.025)


@prop("coffee_table", tex=1024, tags=["furniture", "living"])
def coffee_table():
    """A walnut mid-century coffee table with a magazine shelf, rings on the top."""
    wood = M.painted("mat_wood_walnut", rough=0.4)
    floor_box((1.1, 0.52, 0.035), z=0.37, mat=wood, bevel=0.012)
    floor_box((0.98, 0.42, 0.018), z=0.12, mat=wood, bevel=0.004)
    for x in (-0.48, 0.48):
        for y in (-0.2, 0.2):
            leg(x, y, 0.37, wood, 0.011, 0.019, 7)
    for i, (x, y) in enumerate(((0.2, -0.1), (-0.3, 0.12))):
        cyl(0.04, 0.0008, (x, y, 0.4055), M.plain((0.07, 0.04, 0.02), 0.6, edge=0), 32)
        cyl(0.034, 0.001, (x, y, 0.406), wood, 32)


@prop("side_table", tex=512, tags=["furniture", "living"])
def side_table():
    """A small walnut end table with a drawer."""
    wood, brass = M.painted("mat_wood_walnut", rough=0.4), M.brass()
    floor_box((0.45, 0.45, 0.03), z=0.55, mat=wood, bevel=0.008)
    floor_box((0.4, 0.4, 0.1), z=0.45, mat=wood, bevel=0.004)
    drawer_front(0.34, 0.07, 0, 0.5, -0.2, wood, brass, knob=True)
    floor_box((0.38, 0.38, 0.016), z=0.14, mat=wood)
    for x in (-0.18, 0.18):
        for y in (-0.18, 0.18):
            leg(x, y, 0.45, wood, 0.01, 0.017, 5)


@prop("bookcase", tex=2048, tags=["furniture", "living", "office"])
def bookcase():
    """An oak bookcase, crammed: novels, a baseball almanac, an atlas, a souvenir or two."""
    wood = M.painted("mat_wood_honey", rough=0.5)
    W, D, H = 0.9, 0.3, 1.8
    for x in (-W / 2 + 0.01, W / 2 - 0.01):
        floor_box((0.02, D, H), x=x, mat=wood, bevel=0.003)
    floor_box((W, 0.01, H), y=D / 2 - 0.005, mat=M.plain((0.25, 0.17, 0.1), 0.8))
    shelves = [0.06, 0.42, 0.78, 1.14, 1.5, H - 0.02]
    for z in shelves:
        floor_box((W - 0.03, D - 0.01, 0.02), z=z, mat=wood, bevel=0.003)
    floor_box((W - 0.03, 0.02, 0.06), y=-D / 2 + 0.01, mat=wood)
    rnd = random.Random(7)
    cols = [(0.4, 0.08, 0.06), (0.08, 0.14, 0.3), (0.12, 0.24, 0.12), (0.5, 0.4, 0.18), (0.18, 0.1, 0.06),
            (0.6, 0.55, 0.42), (0.04, 0.04, 0.04), (0.3, 0.2, 0.35), (0.6, 0.25, 0.1)]
    book_mats = [M.plain(c, 0.7, edge=0.35, grime=0.4, dust=0.3) for c in cols]
    for si, z in enumerate(shelves[:-1]):
        x = -W / 2 + 0.03
        while x < W / 2 - 0.06:
            if rnd.random() < 0.08:
                hgt = rnd.uniform(0.03, 0.06)
                for k in range(rnd.randint(2, 4)):
                    floor_box((0.2, 0.15, hgt / 3), x + 0.1, -0.02, z + 0.02 + k * hgt / 3, mat=rnd.choice(book_mats), rot=(0, 0, rnd.uniform(-0.1, 0.1)))
                x += 0.22
                continue
            t = rnd.uniform(0.018, 0.045)
            h = rnd.uniform(0.18, 0.3)
            lean = rnd.uniform(-0.06, 0.06) if rnd.random() < 0.2 else 0.0
            floor_box((t, rnd.uniform(0.14, 0.22), h), x + t / 2, -0.02, z + 0.02, mat=rnd.choice(book_mats), bevel=0.003, rot=(0, lean, 0))
            x += t + 0.002
    cyl(0.04, 0.12, (0.3, -0.05, shelves[-2] + 0.08), M.plain((0.75, 0.62, 0.3), 0.3), 24, r_top=0.03)


@prop("bed_double", tex=2048, tags=["furniture", "bedroom"])
def bed_double():
    """A maple spindle double bed, unmade: chenille spread kicked back, two dented pillows."""
    maple = M.painted("mat_wood_honey", rough=0.45)
    spread = M.fabric((0.82, 0.62, 0.62), (0.92, 0.88, 0.78), "chenille", 18)
    sheet = M.plain((0.88, 0.86, 0.8), 0.9, edge=0, grime=0.3)
    W, Lg = 1.37, 1.95
    floor_box((W + 0.04, Lg, 0.18), z=0.18, mat=maple, bevel=0.01)
    for x in (-W / 2, W / 2):
        for y in (-Lg / 2, Lg / 2):
            cyl(0.03, 0.36, (x, y, 0.18), maple, 16, bevel=0.004)
    floor_box((W + 0.08, 0.05, 0.08), y=Lg / 2, z=0.82, mat=maple, bevel=0.015)
    floor_box((W + 0.08, 0.05, 0.06), y=Lg / 2, z=0.36, mat=maple)
    for i in range(9):
        x = -W / 2 + 0.1 + i * (W - 0.2) / 8
        lathe([(0.012, 0), (0.018, 0.08), (0.011, 0.2), (0.016, 0.3), (0.011, 0.4), (0.012, 0.46)], (x, Lg / 2, 0.36), maple, 12)
    for x in (-W / 2, W / 2):
        cyl(0.032, 0.9, (x, Lg / 2, 0.45), maple, 16, bevel=0.004)
        lathe([(0.0, 0.0), (0.04, 0.02), (0.03, 0.06), (0.0, 0.08)], (x, Lg / 2, 0.9), maple, 16)
    floor_box((W + 0.08, 0.04, 0.3), y=-Lg / 2, z=0.3, mat=maple, bevel=0.012)
    m = cushion((W - 0.04, Lg - 0.06, 0.2), (0, 0, 0.46), sheet, puff=0.05)
    for x in (-0.33, 0.33):
        p = cushion((0.6, 0.38, 0.14), (x, Lg / 2 - 0.3, 0.62), sheet, puff=0.3, rot=(math.radians(-8), 0, 0.05 * x))
        sag(p, 0.04)
    b = box((W + 0.1, 1.2, 0.05), (0, -0.28, 0.585), spread, bevel=0.02)
    jitter(b, 0.012, 5)
    fold = cushion((W + 0.06, 0.32, 0.12), (0, 0.38, 0.61), spread, puff=0.2, rot=(0, 0, 0.03))
    jitter(fold, 0.01, 6)
    for x in (-W / 2 - 0.02, W / 2 + 0.02):
        box((0.04, 1.2, 0.3), (x, -0.28, 0.46), spread, bevel=0.015)


@prop("nightstand", tex=512, tags=["furniture", "bedroom"])
def nightstand():
    """A maple nightstand with one drawer and an open shelf."""
    maple, brass = M.painted("mat_wood_honey", rough=0.45), M.brass()
    floor_box((0.46, 0.38, 0.03), z=0.6, mat=maple, bevel=0.008)
    for x in (-0.21, 0.21):
        floor_box((0.03, 0.36, 0.6), x=x, mat=maple)
    floor_box((0.42, 0.36, 0.02), z=0.08, mat=maple)
    floor_box((0.42, 0.36, 0.02), z=0.42, mat=maple)
    floor_box((0.42, 0.01, 0.6), y=0.175, mat=maple)
    drawer_front(0.4, 0.15, 0, 0.52, -0.18, maple, brass, knob=True)


@prop("dresser", tex=1024, tags=["furniture", "bedroom"])
def dresser():
    """A walnut six-drawer dresser with brass bail pulls, one drawer not quite shut."""
    wood, brass = M.painted("mat_wood_walnut", rough=0.4), M.brass()
    W, D, H = 1.2, 0.48, 0.82
    floor_box((W, D, H - 0.1), z=0.08, mat=wood, bevel=0.01)
    floor_box((W + 0.03, D + 0.02, 0.03), z=H - 0.03, mat=wood, bevel=0.01)
    for x in (-0.5, 0.5):
        for y in (-0.2, 0.2):
            leg(x, y, 0.08, wood, 0.016, 0.022, 3, z_top=0.08)
    for row in range(3):
        for col in (-1, 1):
            out = 0.04 if (row == 1 and col == 1) else 0.0
            z = 0.2 + row * 0.22
            box((0.57, 0.02, 0.2), (col * 0.295, -D / 2 - 0.01 - out, z), wood, bevel=0.006)
            for k in (-1, 1):
                cyl(0.008, 0.012, (col * 0.295 + k * 0.08, -D / 2 - 0.025 - out, z + 0.02), brass, 12, R90)
            tube([(col * 0.295 - 0.08, -D / 2 - 0.03 - out, z + 0.02), (col * 0.295, -D / 2 - 0.045 - out, z - 0.01), (col * 0.295 + 0.08, -D / 2 - 0.03 - out, z + 0.02)], 0.004, brass, 6)


@prop("desk_steel", tex=2048, tags=["furniture", "office"])
def desk_steel():
    """A grey-green steel tanker desk from a closed office, linoleum top, chrome pulls."""
    steel = M.paint((0.33, 0.38, 0.34), (0.5, 0.5, 0.48), chips=0.6, rough=0.45)
    top = M.plain((0.16, 0.2, 0.17), 0.5, edge=0.2)
    chrome, black = M.chrome(), M.plain((0.03, 0.03, 0.03), 0.6)
    W, D, H = 1.37, 0.76, 0.75
    floor_box((W, D, 0.035), z=H - 0.035, mat=top, bevel=0.01)
    floor_box((W - 0.02, D - 0.02, 0.012), z=H - 0.045, mat=chrome, bevel=0.004)
    for x, w in ((-0.47, 0.4), (0.47, 0.4)):
        floor_box((w, D - 0.06, H - 0.1), x=x, z=0.05, mat=steel, bevel=0.012)
        n = 3 if x > 0 else 2
        for k in range(n):
            hh = (H - 0.16) / n
            z = 0.08 + hh * (k + 0.5)
            box((w - 0.03, 0.02, hh - 0.02), (x, -D / 2 + 0.02, z), steel, bevel=0.008)
            box((0.12, 0.02, 0.02), (x, -D / 2, z + hh * 0.25), chrome, bevel=0.006)
            box((0.05, 0.005, 0.025), (x, -D / 2 + 0.008, z + hh * 0.36), M.paper(), bevel=0.002)
        floor_box((w, D - 0.06, 0.05), x=x, mat=black, bevel=0.01)
    floor_box((0.5, D - 0.06, 0.1), z=H - 0.14, mat=steel, bevel=0.01)
    box((0.48, 0.02, 0.08), (0, -D / 2 + 0.02, H - 0.09), steel, bevel=0.006)
    floor_box((0.5, 0.02, 0.5), y=D / 2 - 0.04, z=0.1, mat=steel)


@prop("desk_chair", tex=1024, tags=["furniture", "office"])
def desk_chair():
    """An oak swivel banker's chair on casters."""
    oak, iron = M.painted("mat_wood_honey", rough=0.45), M.iron()
    seat = box((0.46, 0.44, 0.05), (0, 0, 0.47), oak, bevel=0.02)
    sag(seat, 0.012)
    for i in range(6):
        a = math.radians(-60 + i * 24)
        rod((math.sin(a) * 0.2, 0.18 + math.cos(a) * 0.03, 0.5), (math.sin(a) * 0.22, 0.2 + math.cos(a) * 0.04, 0.78), 0.009, oak)
    tube([(math.sin(math.radians(a)) * 0.24, 0.2 + math.cos(math.radians(a)) * 0.05, 0.8) for a in range(-75, 80, 10)], 0.025, oak, 10)
    for side in (-1, 1):
        tube([(side * 0.22, 0.2, 0.68), (side * 0.25, 0.0, 0.66), (side * 0.24, -0.12, 0.56), (side * 0.22, -0.14, 0.5)], 0.018, oak, 10)
    cyl(0.03, 0.12, (0, 0, 0.4), iron, 16)
    cyl(0.07, 0.03, (0, 0, 0.34), iron, 20)
    for i in range(4):
        a = i * math.pi / 2 + math.pi / 4
        rod((0, 0, 0.32), (math.cos(a) * 0.3, math.sin(a) * 0.3, 0.06), 0.018, iron)
        cyl(0.025, 0.02, (math.cos(a) * 0.31, math.sin(a) * 0.31, 0.03), iron, 16, (0, math.radians(90), a))


@prop("filing_cabinet", tex=1024, tags=["furniture", "office"])
def filing_cabinet():
    """A four-drawer steel filing cabinet with label holders, one drawer dented."""
    steel, chrome = M.paint((0.45, 0.47, 0.44), (0.6, 0.6, 0.58), chips=0.5, rough=0.4), M.chrome()
    W, D, H = 0.38, 0.66, 1.32
    floor_box((W, D, H), mat=steel, bevel=0.01)
    for k in range(4):
        z = 0.06 + k * 0.31 + 0.15
        box((W - 0.02, 0.018, 0.29), (0, -D / 2 - 0.004, z), steel, bevel=0.007, rot=(0, 0, 0.01 if k == 1 else 0))
        box((0.13, 0.025, 0.025), (0, -D / 2 - 0.02, z + 0.04), chrome, bevel=0.008)
        box((0.07, 0.006, 0.03), (0, -D / 2 - 0.015, z + 0.09), chrome, bevel=0.002)
        box((0.06, 0.004, 0.022), (0, -D / 2 - 0.019, z + 0.09), M.paper(), bevel=0.001)


@prop("lamp_table", tex=512, tags=["decor", "living", "bedroom"], kind="fixture")
def lamp_table():
    """A gourd-shaped ceramic table lamp with a pleated fabric shade."""
    glaze = M.plain((0.62, 0.42, 0.14), 0.25, edge=0.2, grime=0.3)
    shade = M.fabric((0.88, 0.8, 0.6), (0.78, 0.68, 0.48), "stripes", 120, rough=0.9)
    brass = M.brass()
    lathe([(0.07, 0), (0.08, 0.02), (0.1, 0.1), (0.08, 0.2), (0.045, 0.26), (0.06, 0.32), (0.03, 0.38), (0.012, 0.4)], mat=glaze, verts=32)
    cyl(0.006, 0.12, (0, 0, 0.46), brass, 8)
    lathe([(0.0, 0.5), (0.02, 0.5), (0.02, 0.52), (0.0, 0.53)], mat=brass, verts=12)
    prof = []
    verts = 48
    obj = lathe([(0.18, 0.4), (0.18, 0.402), (0.11, 0.62), (0.105, 0.622)], mat=shade, verts=verts)
    for v in obj.data.vertices:
        a = math.atan2(v.co.y, v.co.x)
        k = 1.0 + 0.04 * math.cos(a * 24)
        v.co.x *= k
        v.co.y *= k


@prop("lamp_floor", tex=512, tags=["decor", "living"], kind="fixture")
def lamp_floor():
    """A brass pole floor lamp with a cone shade."""
    brass, shade = M.brass(), M.fabric((0.85, 0.78, 0.6), (0.7, 0.6, 0.45), "tweed", 40)
    lathe([(0.0, 0), (0.15, 0), (0.15, 0.02), (0.06, 0.05), (0.02, 0.07)], mat=brass, verts=32)
    cyl(0.011, 1.45, (0, 0, 0.78), brass, 12)
    lathe([(0.24, 1.32), (0.24, 1.322), (0.12, 1.58), (0.115, 1.582)], mat=shade, verts=40)


@prop("coat_rack", tex=1024, tags=["furniture", "entrance"])
def coat_rack():
    """A bentwood coat stand by the door, a raincoat and a flat cap hanging on it."""
    wood, coat = M.wood("mahogany", "Y"), M.fabric((0.48, 0.42, 0.3), (0.4, 0.35, 0.25), "tweed", 30)
    cyl(0.022, 1.75, (0, 0, 0.875), wood, 16, bevel=0.004)
    lathe([(0.0, 1.75), (0.035, 1.76), (0.02, 1.8), (0.0, 1.82)], mat=wood, verts=16)
    for i in range(4):
        a = i * math.pi / 2
        tube([(0, 0, 0.35), (math.cos(a) * 0.18, math.sin(a) * 0.18, 0.12), (math.cos(a) * 0.28, math.sin(a) * 0.28, 0.01)], 0.014, wood, 10)
        tube([(0, 0, 1.6), (math.cos(a + 0.4) * 0.12, math.sin(a + 0.4) * 0.12, 1.66), (math.cos(a + 0.4) * 0.16, math.sin(a + 0.4) * 0.16, 1.62)], 0.011, wood, 10)
    c = cushion((0.42, 0.14, 0.9), (0.06, -0.12, 1.15), coat, puff=0.1, rot=(0.08, 0, 0.3))
    jitter(c, 0.01, 4)
    lathe([(0.0, 1.69), (0.12, 1.69), (0.12, 1.7), (0.09, 1.74), (0.0, 1.76)], (0.1, 0.1, 0.0), M.fabric((0.25, 0.22, 0.18), (0.2, 0.18, 0.15), "tweed", 50), 24, (0.15, 0.1, 0))


@prop("closet_clothes", tex=1024, tags=["bedroom", "closet"])
def closet_clothes():
    """A closet rod hung with shirts, a suit jacket and a pea coat, a shelf of boxes above."""
    wood, chrome = M.wood("pine", "X"), M.chrome()
    rod((-0.42, 0, 1.65), (0.42, 0, 1.65), 0.012, chrome)
    floor_box((0.9, 0.36, 0.02), z=1.75, mat=wood)
    rnd = random.Random(11)
    garments = [((0.2, 0.22, 0.3), 0.75), ((0.88, 0.86, 0.8), 0.7), ((0.55, 0.62, 0.72), 0.7), ((0.12, 0.12, 0.14), 0.95),
                ((0.4, 0.3, 0.2), 0.8), ((0.75, 0.7, 0.55), 0.7), ((0.18, 0.2, 0.3), 1.0)]
    x = -0.38
    for col, ln in garments:
        mat = M.fabric(col, tuple(c * 0.8 for c in col), "tweed", 40)
        c = cushion((0.05, 0.42, ln), (x, 0, 1.6 - ln / 2), mat, puff=0.05, rot=(0, 0, rnd.uniform(-0.15, 0.15)))
        tube([(x, 0, 1.6), (x, 0, 1.66), (x, -0.01, 1.68)], 0.003, chrome, 4)
        x += 0.115
    for k, (w, h) in enumerate(((0.3, 0.14), (0.26, 0.1), (0.34, 0.12))):
        floor_box((w, 0.3, h), -0.25 + k * 0.28, 0, 1.77, mat=M.cardboard(), rot=(0, 0, rnd.uniform(-0.1, 0.1)))
