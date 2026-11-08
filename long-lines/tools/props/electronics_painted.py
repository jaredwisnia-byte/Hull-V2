"""Props textured from supplied painted texture sheets (assets/source_textures/<prop>/).

Pattern for a painted prop: crop the sheet into per-face images, build geometry
whose proportions follow the painting, map each face planar to its crop, and let
the kit bake the result (which adds contact grime from the real shape on top).
"""
import math
import os

from mathutils import Euler, Vector

from propkit import prop
from propkit import mats as M
from propkit.core import box, cyl, floor_box, planar_uv, mesh_obj, smooth, squircle

import bmesh

SRC = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "assets", "source_textures"))
R90 = (math.radians(90), 0, 0)


def tex(prop_name, part, rough=0.55, grime=0.25):
    return M.image(os.path.join(SRC, prop_name, part + ".png"), rough, grime, 0.03, name="%s_%s" % (prop_name, part))


def walnut_stand(top_z=0.43, painted=None):
    """The tapered-leg TV stand shared by the TV props. painted: a prop name whose
    'top' crop dresses the slabs, so the stand matches a painted TV."""
    walnut, brass = M.wood("walnut"), M.brass()
    slab = tex(painted, "top", 0.5, 0.3) if painted else walnut
    legs = M.plain((0.12, 0.06, 0.03), 0.45, edge=0.35, name="stand_legs") if painted else walnut
    for size, z in (((0.74, 0.46, 0.03), top_z - 0.03), ((0.68, 0.40, 0.06), top_z - 0.09), ((0.62, 0.34, 0.018), 0.121)):
        b = floor_box(size, z=z, mat=slab, bevel=0.008 if size[2] > 0.02 else 0.004)
        if painted:
            planar_uv(b, 0, 1, size[0], size[1])
    for sx in (-1, 1):
        for sy in (-1, 1):
            rot = (-sy * math.radians(4.2), sx * math.radians(7), 0)
            ax = Euler(rot).to_matrix() @ Vector((0, 0, 1))
            top = Vector((sx * 0.3, sy * 0.17, top_z - 0.06))
            cyl(0.012, 0.37, tuple(top - ax * 0.185), legs, 16, rot, r_top=0.021, bevel=0.002)
            cyl(0.0128, 0.03, tuple(top - ax * 0.358), brass, 16, rot, bevel=0.0015)


def bulged_face(w, h, loc, mat, bulge, n=5.0, nx=28, nz=22):
    """A rounded-rectangle face bulging toward -Y, with 0..1 label coordinates."""
    bm = bmesh.new()
    grid = []
    for j in range(nz + 1):
        row = []
        for i in range(nx + 1):
            su, sw = squircle(i / nx * 2 - 1, j / nz * 2 - 1, n)
            b = bulge * (1 - min(1.0, (su * su + sw * sw) * 0.9))
            row.append(bm.verts.new((su * w / 2, -b, sw * h / 2)))
        grid.append(row)
    for j in range(nz):
        for i in range(nx):
            bm.faces.new((grid[j][i], grid[j + 1][i], grid[j + 1][i + 1], grid[j][i + 1]))
    o = mesh_obj("face", bm)
    o.location = loc
    o.data.materials.append(mat)
    planar_uv(o, 0, 2, w, h)
    return smooth(o, 80)


@prop("tv_painted", tex=2048, tags=["electronics", "living"], kind="fixture")
def tv_painted():
    """1975 'Westbury' colour TV textured from Jared's painted sheet, on the walnut stand."""
    P = "tv_painted"
    top_z = 0.43
    walnut_stand(top_z, P)
    # Proportions follow the sheet: front 522 x 388 px; side strip 167 px deep.
    s = 0.62 / 522.0
    W, H, Dw = 0.62, 388 * s, 167 * s
    z0 = top_z + 0.012
    rubber, dark = M.plain((0.02, 0.02, 0.02), 0.8, edge=0), M.plain((0.07, 0.066, 0.062), 0.55, edge=0.1, grime=0.35, name="tv_back_plastic")
    for sx in (-1, 1):
        for sy in (-1, 1):
            cyl(0.016, 0.012, (sx * 0.26, sy * 0.15, top_z + 0.006), rubber, 12)
    fy = -0.2
    # Wood cabinet: a body plus textured face panels.
    box((W - 0.01, Dw - 0.01, H - 0.01), (0, fy + Dw / 2, z0 + H / 2), M.wood("walnut"), bevel=0.01)
    front = box((W, 0.012, H), (0, fy - 0.003, z0 + H / 2), tex(P, "front"), bevel=0.004)
    planar_uv(front, 0, 2, W, H)
    for sx in (-1, 1):
        side = box((0.012, Dw, H), (sx * (W / 2 - 0.003), fy + Dw / 2, z0 + H / 2), tex(P, "side"), bevel=0.004)
        planar_uv(side, 1, 2, Dw, H, flip_u=sx < 0)
    top = box((W, Dw, 0.012), (0, fy + Dw / 2, z0 + H - 0.003), tex(P, "top"), bevel=0.004)
    planar_uv(top, 0, 1, W, Dw)
    # Screen: the painted screen, bulging slightly out of the painted bezel.
    sw, sh = 355 * s, 293 * s
    sx_, sz = -W / 2 + (32 + 387) / 2 * s, z0 + H - (40 + 333) / 2 * s
    bulged_face(sw * 0.94, sh * 0.94, (sx_, fy - 0.0095, sz), tex(P, "screen", 0.12, 0.1), 0.012)
    # Knobs over the painted ones, each capped with its painted dial.
    for k, (py, part) in enumerate(((106, "dial1"), (173, "dial2"))):
        kx, kz = -W / 2 + 434 * s, z0 + H - py * s
        knob = cyl(0.025, 0.022, (kx, fy - 0.02, kz), tex(P, part, 0.4, 0.2), 32, R90, bevel=0.003)
        planar_uv(knob, 0, 1, 0.05, 0.05)
    # Rear housing for the tube, in dark plastic, with the painted back panel.
    bd, bw, bh = 0.2, 0.54, 0.4
    hb = box((bw, bd, bh), (0, fy + Dw + bd / 2 - 0.01, z0 + bh / 2 + 0.02), dark, bevel=0.03)
    back = box((bw * 0.96, 0.01, bh * 0.94), (0, fy + Dw + bd - 0.005, z0 + bh / 2 + 0.02), tex(P, "back_crop", 0.6, 0.3), bevel=0.004)
    planar_uv(back, 0, 2, bw * 0.96, bh * 0.94, flip_u=True)
