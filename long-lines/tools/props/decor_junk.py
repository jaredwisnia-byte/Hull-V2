"""Decorations, keepsakes and junk: what makes a flat look lived in."""
import math
import random

from propkit import prop
from propkit import labels as L
from propkit import mats as M
from propkit.core import box, cushion, cyl, floor_box, jitter, lathe, planar_uv, rod, sag, tube

R90 = (math.radians(90), 0, 0)


def framed(img, w, h, frame_mat, depth=0.025, border=0.03):
    """A framed picture hanging flat on a wall. Origin at the bottom centre of the
    back face; the picture faces -Y."""
    for x in (-w / 2 - border / 2, w / 2 + border / 2):
        box((border, depth, h + border * 2), (x, -depth / 2, h / 2), frame_mat, bevel=0.005)
    for z in (-border / 2, h + border / 2):
        box((w, depth, border), (0, -depth / 2, z), frame_mat, bevel=0.005)
    p = box((w, 0.004, h), (0, -depth * 0.4, h / 2), M.image(img, 0.6, grime=0.5), bevel=0.0005)
    planar_uv(p, 0, 2, w, h)


@prop("frame_naples", tex=512, tags=["decor", "wall"])
def frame_naples():
    """A painted Bay of Naples in a gilt frame: Mom's."""
    framed(L.painting("art_naples", "naples", seed=3), 0.5, 0.36, M.metal((0.7, 0.55, 0.25), 0.4, name="gilt"), border=0.05)


@prop("frame_landscape", tex=512, tags=["decor", "wall"])
def frame_landscape():
    """A dime-store landscape print in a wooden frame."""
    framed(L.painting("art_hills", "landscape", seed=5), 0.4, 0.3, M.wood("walnut", "X"))


@prop("frame_saint", tex=512, tags=["decor", "wall"])
def frame_saint():
    """A holy card print of a saint, palm frond tucked behind the frame."""
    framed(L.painting("art_saint", "saint", 256, 384, seed=2), 0.2, 0.3, M.metal((0.7, 0.55, 0.25), 0.4, name="gilt"))
    tube([(0.1, -0.03, 0.31), (0.14, -0.04, 0.38), (0.17, -0.04, 0.42)], 0.006, M.plain((0.62, 0.55, 0.32), 0.8), 6)


@prop("frame_portrait", tex=512, tags=["decor", "wall"])
def frame_portrait():
    """A black-and-white family portrait: Nick, Terry and their parents, 1958."""
    framed(L.painting("art_family", "portrait", 384, 288, seed=4), 0.3, 0.22, M.plain((0.06, 0.05, 0.04), 0.4, edge=0.4))


@prop("crucifix", tex=256, tags=["decor", "wall"])
def crucifix():
    """A dark wooden crucifix with a brass corpus."""
    wood, brass = M.wood("mahogany", "Y"), M.brass()
    box((0.03, 0.02, 0.3), (0, -0.01, 0.15), wood, bevel=0.004)
    box((0.17, 0.02, 0.03), (0, -0.01, 0.21), wood, bevel=0.004)
    box((0.012, 0.008, 0.11), (0, -0.024, 0.18), brass, bevel=0.003)
    box((0.11, 0.008, 0.01), (0, -0.024, 0.21), brass, bevel=0.003)
    cyl(0.009, 0.008, (0, -0.024, 0.24), brass, 10, R90)


@prop("statue_madonna", tex=512, tags=["decor", "small"])
def statue_madonna():
    """A plaster Madonna, blue robe, paint rubbed off her nose."""
    blue, white, skin = M.plain((0.25, 0.4, 0.65), 0.6, edge=0.6), M.plain((0.88, 0.86, 0.8), 0.6, edge=0.4), M.plain((0.86, 0.72, 0.62), 0.6, edge=0.4)
    cyl(0.05, 0.03, (0, 0, 0.015), M.plain((0.5, 0.48, 0.42), 0.7), 20, bevel=0.005)
    lathe([(0.045, 0.03), (0.05, 0.08), (0.035, 0.18), (0.03, 0.22), (0.0, 0.24)], mat=white, verts=20)
    lathe([(0.0, 0.03), (0.05, 0.03), (0.055, 0.12), (0.04, 0.2), (0.035, 0.24), (0.025, 0.27), (0.0, 0.28)], (0, 0.004, 0), blue, 20).scale = (1, 0.9, 1)
    cyl(0.017, 0.03, (0, -0.008, 0.26), skin, 12)
    for side in (-1, 1):
        rod((side * 0.01, -0.03, 0.17), (side * 0.025, -0.04, 0.15), 0.008, skin, 8)


@prop("plant_pothos", tex=512, tags=["decor", "plant"])
def plant_pothos():
    """A pothos in a clay pot, vines trailing over the edge."""
    clay, leaf = M.plain((0.62, 0.32, 0.18), 0.8, edge=0.3), M.plain((0.2, 0.38, 0.14), 0.5, edge=0.1, dust=0.3)
    lathe([(0.0, 0.0), (0.06, 0.0), (0.075, 0.11), (0.085, 0.115), (0.085, 0.13), (0.07, 0.13), (0.0, 0.12)], mat=clay, verts=24)
    rnd = random.Random(1)
    for i in range(18):
        a = rnd.uniform(0, 6.28)
        r = rnd.uniform(0.0, 0.11)
        z = 0.13 + rnd.uniform(0.0, 0.12) - (0.1 if r > 0.08 else 0)
        l = box((0.06, 0.004, 0.045), (math.cos(a) * r, math.sin(a) * r, z), leaf, bevel=0.0015, rot=(rnd.uniform(-0.8, 0.8), rnd.uniform(-0.5, 0.5), a))
        jitter(l, 0.002, i)
    for k in range(3):
        a = k * 2.0
        tube([(math.cos(a) * 0.07, math.sin(a) * 0.07, 0.13), (math.cos(a) * 0.12, math.sin(a) * 0.12, 0.08), (math.cos(a) * 0.14, math.sin(a) * 0.14, -0.02)], 0.003, leaf, 4)


@prop("plant_snake", tex=512, tags=["decor", "plant"])
def plant_snake():
    """A snake plant: impossible to kill, which is why it's still alive."""
    pot, leaf = M.plain((0.85, 0.82, 0.72), 0.3, edge=0.3), M.plain((0.16, 0.3, 0.12), 0.5, edge=0.2)
    lathe([(0.0, 0.0), (0.07, 0.0), (0.09, 0.16), (0.0, 0.15)], mat=pot, verts=24)
    rnd = random.Random(2)
    for i in range(9):
        a = rnd.uniform(0, 6.28)
        h = rnd.uniform(0.25, 0.45)
        b = box((0.035, 0.006, h), (math.cos(a) * 0.03, math.sin(a) * 0.03, 0.15 + h / 2), leaf, bevel=0.002, rot=(rnd.uniform(-0.15, 0.15), rnd.uniform(-0.15, 0.15), a))
        for v in b.data.vertices:
            if v.co.z > h * 0.3:
                v.co.x *= 0.4


@prop("wall_clock", tex=256, tags=["decor", "wall", "kitchen"])
def wall_clock():
    """A kitchen wall clock, stopped at 1:04 when the power went."""
    rim, face, black = M.plain((0.78, 0.62, 0.22), 0.3, edge=0.3), M.plain((0.95, 0.93, 0.86), 0.3), M.plain((0.05, 0.05, 0.05), 0.4)
    cyl(0.14, 0.04, (0, -0.02, 0.14), rim, 40, R90, bevel=0.008)
    cyl(0.12, 0.042, (0, -0.021, 0.14), face, 40, R90)
    for i in range(12):
        a = i * math.pi / 6
        box((0.004, 0.002, 0.016), (math.sin(a) * 0.1, -0.043, 0.14 + math.cos(a) * 0.1), black, bevel=0, rot=(0, a, 0))
    box((0.008, 0.003, 0.06), (0.012, -0.045, 0.165), black, bevel=0.001, rot=(0, 0.55, 0))
    box((0.006, 0.003, 0.09), (0.018, -0.046, 0.18), black, bevel=0.001, rot=(0, 0.42, 0))


@prop("souvenir_plate", tex=256, tags=["decor", "wall"])
def souvenir_plate():
    """A souvenir plate from Coney Island on a wire hanger."""
    img = L.painting("art_coney", "landscape", 256, 256, seed=11)
    p = cyl(0.11, 0.015, (0, -0.0075, 0.11), M.image(img, 0.2), 32, R90)
    planar_uv(p, 0, 2, 0.22, 0.22)
    tube([(math.cos(a) * 0.112, -0.016, 0.11 + math.sin(a) * 0.112) for a in [i * math.pi / 16 for i in range(33)]], 0.004, M.plain((0.9, 0.85, 0.6), 0.3), 6)


@prop("bowling_trophy", tex=256, tags=["decor", "small"])
def bowling_trophy():
    """Dad's 1962 league bowling trophy, the little gold bowler missing an arm."""
    gold, wood = M.metal((0.8, 0.62, 0.25), 0.3, name="gilt"), M.wood("walnut", "X")
    floor_box((0.12, 0.12, 0.05), mat=wood, bevel=0.006)
    floor_box((0.06, 0.06, 0.012), z=0.05, mat=gold)
    cyl(0.012, 0.16, (0, 0, 0.14), gold, 12)
    lathe([(0.0, 0.22), (0.04, 0.23), (0.03, 0.27), (0.0, 0.28)], mat=gold, verts=16)
    cyl(0.012, 0.03, (0, 0, 0.3), gold, 10)
    cyl(0.009, 0.01, (0, 0, 0.325), gold, 10)
    box((0.05, 0.003, 0.02), (0, -0.061, 0.025), gold, bevel=0.002)


@prop("ceramic_dog", tex=256, tags=["decor", "small"])
def ceramic_dog():
    """A ceramic spaniel from the five-and-dime."""
    c, black = M.plain((0.9, 0.86, 0.78), 0.2, edge=0.3), M.plain((0.25, 0.15, 0.08), 0.3)
    cushion((0.06, 0.12, 0.06), (0, 0, 0.06), c, puff=0.4)
    cushion((0.05, 0.06, 0.05), (0, -0.06, 0.11), c, puff=0.4)
    for s in (-1, 1):
        cushion((0.015, 0.03, 0.04), (s * 0.028, -0.055, 0.1), black, puff=0.3)
    for x in (-0.02, 0.02):
        for y in (-0.04, 0.04):
            cyl(0.01, 0.04, (x, y, 0.02), c, 8)


@prop("pillow_throw", tex=256, tags=["decor", "living"])
def pillow_throw():
    """A needlepoint throw pillow."""
    p = cushion((0.4, 0.4, 0.13), (0, 0, 0.065), M.fabric((0.7, 0.42, 0.12), (0.45, 0.15, 0.08), "floral", 6), puff=0.35)
    jitter(p, 0.004, 3)


@prop("rug_braided", tex=1024, tags=["decor", "living"])
def rug_braided():
    """An oval braided rag rug, faded where everyone walks."""
    rnd = random.Random(4)
    cols = [(0.45, 0.2, 0.12), (0.25, 0.3, 0.2), (0.55, 0.45, 0.25), (0.3, 0.22, 0.18), (0.6, 0.35, 0.15)]
    for i in range(12):
        r = 0.06 + i * 0.06
        pts = [(math.cos(a) * (r + 0.35), math.sin(a) * r, 0.006) for a in [k * math.pi / 32 for k in range(65)]]
        tube(pts, 0.009, M.fabric(cols[i % 5], tuple(c * 0.7 for c in cols[i % 5]), "tweed", 60), 5)


@prop("laundry_pile", tex=1024, tags=["junk", "bedroom"])
def laundry_pile():
    """A heap of laundry waiting for the laundromat that will never open again."""
    rnd = random.Random(6)
    cols = [(0.2, 0.25, 0.4), (0.85, 0.83, 0.78), (0.5, 0.15, 0.1), (0.3, 0.3, 0.28), (0.6, 0.55, 0.4), (0.15, 0.15, 0.18)]
    for i in range(12):
        c = cushion((rnd.uniform(0.2, 0.4), rnd.uniform(0.15, 0.3), rnd.uniform(0.03, 0.06)),
                    (rnd.uniform(-0.15, 0.15), rnd.uniform(-0.12, 0.12), 0.02 + i * 0.022), M.fabric(cols[i % 6], tuple(x * 0.8 for x in cols[i % 6]), "tweed", 50),
                    puff=0.2, rot=(rnd.uniform(-0.3, 0.3), rnd.uniform(-0.3, 0.3), rnd.uniform(0, 3)))
        jitter(c, 0.01, i)


@prop("shoes_pair", tex=512, tags=["junk", "small"])
def shoes_pair():
    """A pair of scuffed brown oxfords, laces undone."""
    leather, sole = M.plain((0.25, 0.13, 0.06), 0.35, edge=0.6), M.plain((0.06, 0.05, 0.04), 0.7)
    for s, rz in ((-1, 0.15), (1, -0.25)):
        x = s * 0.07
        floor_box((0.09, 0.27, 0.02), x, 0, 0, mat=sole, bevel=0.008, rot=(0, 0, rz))
        c = cushion((0.085, 0.24, 0.075), (x, 0.0, 0.055), leather, puff=0.25, rot=(0, 0, rz))
        sag(c, 0.03)


@prop("boots_work", tex=512, tags=["junk", "entrance"])
def boots_work():
    """Sanitation Department work boots by the door, still muddy."""
    leather, sole = M.plain((0.22, 0.14, 0.08), 0.6, edge=0.6, dust=0.5), M.plain((0.05, 0.05, 0.04), 0.7)
    for s in (-1, 1):
        x = s * 0.075
        floor_box((0.11, 0.3, 0.03), x, 0, 0, mat=sole, bevel=0.01)
        cushion((0.1, 0.28, 0.09), (x, 0.0, 0.07), leather, puff=0.2)
        cushion((0.1, 0.12, 0.2), (x, 0.07, 0.17), leather, puff=0.15, rot=(0, s * 0.15 if s > 0 else 0, 0))


@prop("umbrella", tex=256, tags=["entrance", "junk"])
def umbrella():
    """A black umbrella leaning in the corner."""
    black, wood = M.fabric((0.05, 0.05, 0.06), (0.03, 0.03, 0.03), "plain"), M.wood("mahogany", "Y")
    lathe([(0.0, 0.05), (0.06, 0.25), (0.045, 0.75), (0.008, 0.85)], mat=black, verts=8)
    rod((0, 0, 0.0), (0, 0, 0.92), 0.005, M.chrome())
    tube([(0, 0, 0.9), (0, 0, 0.97), (0.04, 0, 0.99), (0.05, 0, 0.95)], 0.009, wood, 8)


@prop("suitcase", tex=512, tags=["closet", "junk"], kind="container")
def suitcase():
    """A tweed suitcase with leather corners, Dad's, from the Navy."""
    tw, leather, brass = M.fabric((0.45, 0.38, 0.28), (0.35, 0.3, 0.22), "tweed", 40), M.plain((0.3, 0.16, 0.08), 0.4, edge=0.6), M.brass()
    floor_box((0.65, 0.2, 0.42), mat=tw, bevel=0.02)
    for x in (-0.31, 0.31):
        for z in (0.02, 0.4):
            box((0.05, 0.21, 0.05), (x, 0, z), leather, bevel=0.012)
    tube([(-0.08, -0.0, 0.42), (-0.08, 0, 0.47), (0.08, 0, 0.47), (0.08, 0, 0.42)], 0.012, leather, 8)
    for x in (-0.2, 0.2):
        box((0.03, 0.02, 0.025), (x, -0.105, 0.38), brass, bevel=0.005)


@prop("toolbox", tex=512, tags=["closet", "junk"], kind="container")
def toolbox():
    """A red steel toolbox, a hammer laid on top."""
    red, chrome = M.paint((0.6, 0.1, 0.07), (0.5, 0.5, 0.48), chips=0.7, rough=0.4), M.chrome()
    floor_box((0.46, 0.2, 0.18), mat=red, bevel=0.008)
    floor_box((0.47, 0.21, 0.04), z=0.18, mat=red, bevel=0.01)
    tube([(-0.12, 0, 0.22), (-0.12, 0, 0.27), (0.12, 0, 0.27), (0.12, 0, 0.22)], 0.007, chrome, 8)
    box((0.03, 0.02, 0.02), (0, -0.105, 0.17), chrome, bevel=0.004)
    rod((-0.18, 0.04, 0.235), (0.1, 0.0, 0.235), 0.012, M.wood("oak", "X"))
    box((0.03, 0.1, 0.03), (0.11, 0.0, 0.235), M.iron(), bevel=0.006)


@prop("wastebasket", tex=256, tags=["junk", "office"])
def wastebasket():
    """A steel wastebasket with crumpled paper spilling out."""
    steel = M.paint((0.35, 0.4, 0.36), chips=0.5, name="steel_green")
    lathe([(0.0, 0.0), (0.12, 0.0), (0.15, 0.32), (0.143, 0.32), (0.113, 0.012), (0.0, 0.012)], mat=steel, verts=28)
    rnd = random.Random(7)
    for i in range(7):
        b = cushion((0.07, 0.07, 0.06), (rnd.uniform(-0.08, 0.08), rnd.uniform(-0.08, 0.08), 0.24 + i * 0.015), M.paper((0.88, 0.86, 0.78)), puff=0.5)
        jitter(b, 0.008, i)
    c = cushion((0.07, 0.07, 0.06), (0.2, -0.1, 0.03), M.paper((0.88, 0.86, 0.78)), puff=0.5)
    jitter(c, 0.008, 9)


@prop("mop_bucket", tex=512, tags=["junk", "bath", "kitchen"])
def mop_bucket():
    """A galvanised bucket with a string mop."""
    galv, wood = M.metal((0.62, 0.62, 0.6), 0.45, name="galv"), M.wood("pine", "Y")
    lathe([(0.0, 0.0), (0.12, 0.0), (0.14, 0.28), (0.133, 0.28), (0.113, 0.01), (0.0, 0.01)], mat=galv, verts=28)
    tube([(-0.14, 0, 0.27), (0.0, 0, 0.36), (0.14, 0, 0.27)], 0.003, galv, 4)
    rod((0.02, 0.0, 0.05), (0.15, 0.1, 1.25), 0.013, wood)
    rnd = random.Random(2)
    for i in range(14):
        a = i * 0.45
        tube([(0.02, 0, 0.12), (0.02 + math.cos(a) * 0.06, math.sin(a) * 0.06, 0.04), (0.02 + math.cos(a) * 0.09, math.sin(a) * 0.09, 0.2)], 0.008, M.plain((0.7, 0.66, 0.55), 0.95), 5)


@prop("trash_bag", tex=256, tags=["junk", "kitchen"])
def trash_bag():
    """A full black garbage bag, tied, waiting for a collection that won't come."""
    b = cushion((0.4, 0.35, 0.5), (0, 0, 0.25), M.plain((0.04, 0.04, 0.045), 0.25, edge=0.1, dust=0.1), puff=0.5)
    jitter(b, 0.02, 4)
    lathe([(0.0, 0.48), (0.05, 0.5), (0.02, 0.56), (0.04, 0.6), (0.0, 0.6)], mat=M.plain((0.04, 0.04, 0.045), 0.25), verts=10)


@prop("broom", tex=256, tags=["junk", "kitchen"])
def broom():
    """A corn broom worn crooked."""
    rod((0, 0, 0.25), (0, 0, 1.4), 0.012, M.wood("pine", "Y"))
    b = box((0.28, 0.05, 0.3), (0.0, 0, 0.15), M.plain((0.72, 0.6, 0.35), 0.95), bevel=0.01, rot=(0, 0.08, 0))
    for v in b.data.vertices:
        if v.co.z > 0.05:
            v.co.x *= 0.45
    box((0.14, 0.055, 0.04), (0, 0, 0.27), M.plain((0.6, 0.15, 0.1), 0.6), bevel=0.01)
