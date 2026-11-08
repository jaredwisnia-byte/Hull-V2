"""Consumer goods and paper: what a 1975 flat is full of. All brands invented."""
import math
import random

from propkit import prop
from propkit import labels as L
from propkit import mats as M
from propkit.core import box, cushion, cyl, floor_box, jitter, lathe, planar_uv, rod, tube, wrap_uv

R90 = (math.radians(90), 0, 0)


def can(r, h, label_png, loc=(0, 0, 0), top=None):
    tin = M.metal((0.7, 0.7, 0.68), 0.35, name="tin")
    x, y, z = loc
    body = cyl(r, h, (x, y, z + h / 2), M.image(label_png, 0.4), 32)
    wrap_uv(body, h, -h / 2)
    for zz in (z + 0.003, z + h - 0.003):
        cyl(r + 0.001, 0.006, (x, y, zz), tin, 32, bevel=0.002)
    cyl(r * 0.93, 0.002, (x, y, z + h), top or tin, 32)
    return body


def bottle(profile, glass_tint, label_png=None, label_z=(0.04, 0.12), loc=(0, 0, 0), cap=None):
    x, y, z = loc
    lathe(profile, (x, y, z), M.glass(glass_tint), 24)
    if label_png:
        near = [p[0] for p in profile if label_z[0] - 0.05 <= p[1] <= label_z[1] + 0.05] or [p[0] for p in profile]
        r = max(near) + 0.001
        lb = cyl(r, label_z[1] - label_z[0], (x, y, z + (label_z[0] + label_z[1]) / 2), M.image(label_png, 0.6), 24)
        wrap_uv(lb, label_z[1] - label_z[0], -(label_z[1] - label_z[0]) / 2)
    top = profile[-1][1]
    if cap:
        cyl(profile[-1][0] + 0.002, 0.012, (x, y, z + top), cap, 16, flutes=12)


SOUP = lambda: L.wrap_label("soup", "Kettlewood", "TOMATO SOUP", (200, 30, 25), (245, 240, 225), (230, 180, 40), "CONDENSED")
BEANS = lambda: L.wrap_label("beans", "Harbor", "PORK & BEANS", (40, 80, 50), (240, 220, 160), (190, 50, 30), "IN TOMATO SAUCE")
BEER = lambda: L.wrap_label("beer", "Gotham", "LAGER BEER", (235, 225, 205), (180, 30, 30), (30, 50, 110), "BREWED IN BROOKLYN")


@prop("can_beans", tex=256, tags=["goods", "food", "small"], kind="carry")
def can_beans():
    """A can of Harbor pork and beans."""
    can(0.038, 0.11, BEANS())


@prop("can_beer", tex=256, tags=["goods", "drink", "small", "junk"], kind="carry")
def can_beer():
    """A can of Gotham lager with a pull tab."""
    can(0.033, 0.122, BEER())
    box((0.012, 0.022, 0.002), (0.0, 0.012, 0.123), M.metal((0.7, 0.7, 0.68), 0.3, name="tin"), bevel=0.001)


@prop("beer_cans_crushed", tex=512, tags=["junk", "goods"])
def beer_cans_crushed():
    """Three crushed lager cans."""
    rnd = random.Random(3)
    for i in range(3):
        body = cyl(0.034, 0.122, (i * 0.08 - 0.08, rnd.uniform(-0.05, 0.05), 0.022), M.image(BEER(), 0.4), 24,
                   (math.radians(90), 0, rnd.uniform(0, 3)))
        wrap_uv(body, 0.122, -0.061)
        body.scale = (1.0, 1.0, 0.6)
        jitter(body, 0.004, i)


@prop("bottle_soda", tex=256, tags=["goods", "drink", "small"], kind="carry")
def bottle_soda():
    """A returnable glass bottle of Bronx Bell cream soda."""
    lbl = L.wrap_label("soda", "Bronx Bell", "CREAM SODA", (250, 240, 220), (30, 90, 160), (220, 60, 50), "16 FL OZ")
    bottle([(0.0, 0.0), (0.03, 0.0), (0.032, 0.02), (0.031, 0.13), (0.02, 0.18), (0.012, 0.22), (0.013, 0.24)], (0.25, 0.4, 0.3), lbl, (0.04, 0.11), cap=M.metal((0.7, 0.2, 0.15), 0.3, name="cap_red"))


@prop("bottle_beer", tex=256, tags=["goods", "drink", "small", "junk"], kind="carry")
def bottle_beer():
    """A brown longneck, empty."""
    lbl = L.wrap_label("beer_bottle", "Gotham", "LAGER", (235, 225, 205), (180, 30, 30), (30, 50, 110))
    bottle([(0.0, 0.0), (0.03, 0.0), (0.031, 0.015), (0.03, 0.14), (0.016, 0.19), (0.011, 0.24), (0.012, 0.245)], (0.18, 0.09, 0.03), lbl, (0.05, 0.11))


@prop("bottle_liquor", tex=256, tags=["goods", "drink", "small"], kind="carry")
def bottle_liquor():
    """A fifth of Old Battery bourbon, a third left."""
    lbl = L.box_art("bourbon", "Old Battery", "KENTUCKY BOURBON", (230, 215, 170), (90, 30, 20), (40, 30, 20), 256, 320, motif="stripes")
    lathe([(0.0, 0.0), (0.045, 0.0), (0.046, 0.18), (0.03, 0.22), (0.014, 0.24), (0.014, 0.28)], mat=M.glass((0.45, 0.25, 0.08)), verts=24).scale = (1, 0.6, 1)
    lb = box((0.08, 0.002, 0.1), (0, -0.028, 0.1), M.image(lbl, 0.7), bevel=0.0005)
    planar_uv(lb, 0, 2, 0.08, 0.1)
    cyl(0.017, 0.025, (0, 0, 0.29), M.plain((0.7, 0.55, 0.25), 0.4), 16, flutes=14)


@prop("milk_carton", tex=256, tags=["goods", "food", "small"], kind="carry")
def milk_carton():
    """A quart carton of Hudson Valley milk."""
    art = L.box_art("milk", "Hudson Valley", "HOMOGENIZED MILK", (245, 245, 240), (30, 80, 160), (30, 80, 160), 256, 384, motif="stripes")
    b = floor_box((0.07, 0.07, 0.19), mat=M.image(art, 0.7), bevel=0.003)
    planar_uv(b, 0, 2, 0.07, 0.19)
    b.location.z += 0
    for s in (-1, 1):
        box((0.072, 0.004, 0.06), (0, s * 0.018, 0.215), M.paper((0.92, 0.92, 0.9)), bevel=0.001, rot=(s * 0.5, 0, 0))
    floor_box((0.072, 0.012, 0.025), z=0.235, mat=M.paper((0.92, 0.92, 0.9)), bevel=0.001)


@prop("cereal_box", tex=512, tags=["goods", "food"], kind="carry")
def cereal_box():
    """A box of Sunny Oats, the top folded shut."""
    art = L.box_art("cereal", "Sunny Oats", "TOASTED OAT CEREAL", (240, 200, 40), (180, 40, 20), (30, 100, 170), motif="bowl")
    b = floor_box((0.19, 0.07, 0.28), mat=M.image(art, 0.7), bevel=0.003)
    planar_uv(b, 0, 2, 0.19, 0.28)


@prop("coffee_can", tex=256, tags=["goods", "food", "small"], kind="carry")
def coffee_can():
    """A tin of Manhattan Roast ground coffee."""
    lbl = L.wrap_label("coffee", "Manhattan", "ROAST COFFEE", (130, 30, 25), (235, 200, 120), (30, 25, 20), "VACUUM PACKED")
    can(0.052, 0.14, lbl, top=M.plain((0.1, 0.1, 0.1), 0.5))


@prop("cigarette_pack", tex=256, tags=["goods", "small", "carry"], kind="carry")
def cigarette_pack():
    """A soft pack of Carlyle Kings, a couple shaken out."""
    art = L.box_art("cigs", "Carlyle", "KING SIZE", (245, 240, 230), (170, 20, 20), (170, 20, 20), 256, 384, motif="stripes")
    b = floor_box((0.055, 0.022, 0.085), mat=M.image(art, 0.6), bevel=0.003)
    planar_uv(b, 0, 2, 0.055, 0.085)
    for x in (-0.01, 0.006):
        cyl(0.004, 0.08, (x, 0, 0.09 + (0.01 if x > 0 else 0)), M.paper((0.95, 0.95, 0.92)), 8)
        cyl(0.0042, 0.02, (x, 0, 0.06 + (0.01 if x > 0 else 0)), M.plain((0.8, 0.55, 0.25), 0.7, edge=0), 8)


@prop("ashtray_full", tex=512, tags=["goods", "small", "junk"], kind="carry")
def ashtray_full():
    """A heavy amber glass ashtray, overflowing."""
    lathe([(0.0, 0.0), (0.08, 0.0), (0.085, 0.03), (0.07, 0.032), (0.055, 0.012), (0.0, 0.012)], mat=M.glass((0.5, 0.3, 0.08)), verts=32)
    rnd = random.Random(5)
    ash = M.plain((0.35, 0.33, 0.3), 0.95, edge=0)
    cyl(0.05, 0.004, (0, 0, 0.014), ash, 20)
    for i in range(9):
        a = rnd.uniform(0, 6.28)
        r = rnd.uniform(0.01, 0.05)
        rot = (math.radians(rnd.uniform(70, 100)), 0, a)
        cyl(0.0042, rnd.uniform(0.02, 0.04), (math.cos(a) * r, math.sin(a) * r, 0.02), M.plain((0.8, 0.55, 0.25), 0.7, edge=0), 8, rot)


@prop("newspaper_folded", tex=512, tags=["paper", "small"], kind="readable")
def newspaper_folded():
    """Thursday's paper: FORD TO CITY: DROP DEAD."""
    art = L.newspaper("news_dropdead", "FORD TO CITY:\nDROP DEAD", sub="Vows He'll Veto Any Bail-Out")
    b = box((0.3, 0.4, 0.012), (0, 0, 0.006), M.image(art, 0.9), bevel=0.002)
    from propkit.core import planar_uv as pu
    pu(b, 0, 1, 0.3, 0.4)
    jitter(b, 0.0015, 2)


@prop("newspaper_stack", tex=512, tags=["paper", "junk"])
def newspaper_stack():
    """A bundle of old papers tied with string for the curb."""
    rnd = random.Random(2)
    p = M.paper((0.8, 0.77, 0.66))
    for i in range(14):
        b = floor_box((0.3, 0.4, 0.012), 0, 0, i * 0.012, mat=p, bevel=0.002, rot=(0, 0, rnd.uniform(-0.06, 0.06)))
        jitter(b, 0.002, i)
    top = floor_box((0.3, 0.4, 0.004), 0, 0, 0.168, mat=M.image(L.newspaper("news_old", "SUBWAY FARE\nGOES TO 50c", sub="Riders groan")), bevel=0.001)
    from propkit.core import planar_uv as pu
    pu(top, 0, 1, 0.3, 0.4)
    s = M.plain((0.7, 0.62, 0.45), 0.9, edge=0)
    tube([(-0.155, 0, 0.0), (-0.155, 0, 0.175), (0.155, 0, 0.175), (0.155, 0, 0.0)], 0.002, s, 4)
    tube([(0, -0.205, 0.0), (0, -0.205, 0.175), (0, 0.205, 0.175), (0, 0.205, 0.0)], 0.002, s, 4)


@prop("magazine_pile", tex=512, tags=["paper", "small"])
def magazine_pile():
    """A slithering pile of magazines."""
    rnd = random.Random(8)
    for i in range(6):
        art = L.box_art("mag%d" % i, ["LOOK", "SPORT", "PEOPLE", "TV WEEK", "MECHANICS", "LIFE & HOME"][i], ["Fall Preview", "Yankees '76?", "Disco!", "Kojak Inside", "Fix It Yourself", "Thanksgiving"][i],
                        tuple(rnd.randint(40, 230) for _ in range(3)), (250, 250, 245), (200, 30, 30), 256, 340, seed=i)
        b = floor_box((0.21, 0.28, 0.006), rnd.uniform(-0.04, 0.04), rnd.uniform(-0.04, 0.04), i * 0.006, mat=M.image(art, 0.4), bevel=0.001, rot=(0, 0, rnd.uniform(-0.4, 0.4)))
        planar_uv(b, 0, 1, 0.21, 0.28)


@prop("book_stack", tex=512, tags=["paper", "small"])
def book_stack():
    """A stack of library books, two weeks overdue."""
    rnd = random.Random(4)
    cols = [(0.4, 0.08, 0.06), (0.08, 0.14, 0.3), (0.12, 0.24, 0.12), (0.5, 0.4, 0.18), (0.6, 0.55, 0.42)]
    z = 0
    for i in range(5):
        t = rnd.uniform(0.025, 0.05)
        floor_box((rnd.uniform(0.15, 0.22), rnd.uniform(0.22, 0.28), t), 0, 0, z, mat=M.plain(cols[i], 0.7, edge=0.4), bevel=0.004, rot=(0, 0, rnd.uniform(-0.2, 0.2)))
        z += t


@prop("record_stack", tex=1024, tags=["living", "goods"])
def record_stack():
    """LPs leaning against the wall, sleeves worn white at the corners."""
    names = [("Night Train North", "The Marquettes"), ("Mulberry Street", "Frankie Sorrento"), ("Brass in Pocket", "Calvin Ray"),
             ("Saturday Strings", "Philly Soul Orchestra"), ("Blue Smoke", "Dee Holloway"), ("Live at the Fillmore East", "Gravel Road")]
    for i, (t, a) in enumerate(names):
        img = L.record_sleeve("lp%d" % i, t, a, seed=i)
        b = box((0.31, 0.004, 0.31), (0.0 + i * 0.005, -0.02 - i * 0.008, 0.155), M.image(img, 0.5, edge=0.4), bevel=0.0015, rot=(math.radians(-8), 0, 0))
        planar_uv(b, 0, 2, 0.31, 0.31)


@prop("shoebox", tex=256, tags=["closet", "goods"], kind="container")
def shoebox():
    """A shoebox of letters and photographs."""
    c = M.cardboard()
    floor_box((0.32, 0.2, 0.11), mat=c, bevel=0.003)
    floor_box((0.33, 0.21, 0.03), z=0.1, mat=M.plain((0.75, 0.7, 0.6), 0.8), bevel=0.003)


@prop("cardboard_box_open", tex=1024, tags=["junk", "goods"], kind="container")
def cardboard_box_open():
    """An open moving box full of odds and ends: a lamp base, books, a rolled poster."""
    c = M.cardboard()
    floor_box((0.5, 0.4, 0.02), mat=c)
    for x in (-0.24, 0.24):
        floor_box((0.02, 0.4, 0.38), x=x, mat=c)
    for y in (-0.19, 0.19):
        floor_box((0.5, 0.02, 0.38), y=y, mat=c)
    for x, r in ((-0.25, 0.4), (0.25, -0.4)):
        box((0.02, 0.4, 0.22), (x + (0.1 if x < 0 else -0.1), 0, 0.46), c, rot=(0, r, 0))
    floor_box((0.2, 0.26, 0.2), -0.1, 0, 0.02, mat=M.plain((0.2, 0.1, 0.06), 0.7, edge=0.4))
    cyl(0.03, 0.5, (0.1, 0.05, 0.3), M.paper((0.9, 0.85, 0.7)), 16, (0.3, 0.2, 0))
    lathe([(0.0, 0.02), (0.06, 0.02), (0.08, 0.1), (0.04, 0.2), (0.02, 0.32)], (0.12, -0.08, 0), M.plain((0.2, 0.4, 0.5), 0.3), 16)


@prop("paper_bags", tex=512, tags=["kitchen", "goods"])
def paper_bags():
    """Grocery bags from Thursday, never unpacked: bread, celery, a box of detergent."""
    kraft = M.plain((0.62, 0.47, 0.3), 0.9, edge=0.2)
    b = floor_box((0.3, 0.18, 0.4), mat=kraft, bevel=0.01)
    jitter(b, 0.004, 1)
    b2 = floor_box((0.28, 0.17, 0.32), 0.18, 0.2, 0, mat=kraft, bevel=0.01, rot=(0, 0, 0.4))
    jitter(b2, 0.004, 2)
    cushion((0.12, 0.09, 0.2), (0.0, 0.0, 0.45), M.plain((0.75, 0.55, 0.3), 0.8), puff=0.3, rot=(0.3, 0, 0))
    for i in range(4):
        rod((0.18 + i * 0.01, 0.2, 0.25), (0.15 + i * 0.015, 0.18, 0.5), 0.008, M.plain((0.45, 0.6, 0.25), 0.7))
    art = L.box_art("detergent", "Tidewater", "LAUNDRY POWDER", (240, 120, 30), (250, 250, 245), (30, 90, 170), 256, 320)
    d = floor_box((0.16, 0.08, 0.22), -0.02, 0.02, 0.28, mat=M.image(art, 0.6), bevel=0.003, rot=(0, 0.1, 0))
    planar_uv(d, 0, 2, 0.16, 0.22)
