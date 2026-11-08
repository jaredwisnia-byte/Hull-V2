"""Shared parts: assemble props from these instead of rebuilding them.

wheel()      car or cart wheel: tread band + painted sidewall/hubcap face
sheet_box()  a box whose faces each show a painted crop (appliances, cabinets, crates)
rolled_rim() the rolled edge of a can, pot or bucket
rails()      a run of evenly spaced rods (grilles, racks, balusters)
Every part takes materials from the caller, so one routine serves many props.
"""
import math

from . import mats as M
from .core import box, cyl, planar_uv, rod, tube, wrap_uv

RY = (0, math.radians(90), 0)


def wheel(x, y, radius, width, tread_mat, face_mat, z=None, outer_sign=1, tread_repeat=5.0):
    """A wheel on an axle along X at (x, y). face_mat is shown on the outer face."""
    z = radius if z is None else z
    t = cyl(radius, width, (x, y, z), tread_mat, 40, RY, bevel=width * 0.18)
    wrap_uv(t, width, -width / 2, tread_repeat)
    f = cyl(radius * 0.985, 0.005, (x + outer_sign * (width / 2 + 0.002), y, z), face_mat, 40, RY)
    planar_uv(f, 0, 1, radius * 2, radius * 2)  # local axes, before the part is rotated
    return t


def sheet_box(size, loc, faces, body_mat=None, bevel=0.012):
    """A box with painted faces. faces: {"front"|"back"|"left"|"right"|"top": material,
    or (material, (u0, v0, u1, v1)) to use part of an image}. Front is -Y.
    Faces left out show body_mat."""
    w, d, h = size
    x, y, z = loc
    body = box((w - 0.004, d - 0.004, h - 0.004), (x, y, z + h / 2), body_mat or M.plain((0.5, 0.5, 0.5), 0.5), bevel=bevel)
    t = 0.004
    spec = {
        "front": ((w, t, h), (x, y - d / 2, z + h / 2), (0, 2, w, h, False)),
        "back": ((w, t, h), (x, y + d / 2, z + h / 2), (0, 2, w, h, True)),
        "left": ((t, d, h), (x - w / 2, y, z + h / 2), (1, 2, d, h, True)),
        "right": ((t, d, h), (x + w / 2, y, z + h / 2), (1, 2, d, h, False)),
        "top": ((w, d, t), (x, y, z + h), (0, 1, w, d, False)),
    }
    out = {"body": body}
    for k, mat in faces.items():
        sz, c, (au, av, uw, vh, flip) = spec[k]
        p = box(sz, c, mat, bevel=min(bevel, 0.002))
        planar_uv(p, au, av, uw, vh, flip_u=flip)
        out[k] = p
    return out


def rolled_rim(r, z, mat, thick=0.003, segs=48):
    pts = [(math.cos(a) * r, math.sin(a) * r, z) for a in [i * 2 * math.pi / segs for i in range(segs + 1)]]
    return tube(pts, thick, mat, 8)


def rails(a, b, count, r, mat, offset=(0, 0, 0.1)):
    """count rods from a to b, each running along offset."""
    out = []
    for i in range(count):
        t = i / max(count - 1, 1)
        p = tuple(a[k] + (b[k] - a[k]) * t for k in range(3))
        q = tuple(p[k] + offset[k] for k in range(3))
        out.append(rod(p, q, r, mat, 8))
    return out
