"""Extrude line: trim and frames from painted trim sheets.

moulding(...)  a cross-section (drawn on the sheet, or a default for the kind) swept
               straight along a standard 1.2 m length, wrapped with the painted strip.
               Game code places and scales pieces along walls (baseboard, crown, rails).
frame(...)     a painted front (door / window casing, mirror surround, access panel)
               extruded to its real depth, with its opening knocked out.

Inputs are panel numbers from propkit.atlas.panels() on the sheet; nothing is drawn by hand.
"""
import math
import os

import numpy as np
from PIL import Image

from .atlas import BG_MAX, _crop, panels

PIECE_M = 1.2

# Default sections (y = depth out from the wall, z = up), normalised to height 1, for
# sheets that show a strip but no section. Shapes of common 1970s stock mouldings.
PROFILES = {
    "baseboard": [(0, 0), (0.09, 0), (0.09, 0.82), (0.07, 0.9), (0.045, 0.96), (0.02, 1.0), (0, 1.0)],
    "crown": [(0, 0), (0.06, 0), (0.12, 0.12), (0.3, 0.35), (0.55, 0.6), (0.75, 0.88), (0.8, 1.0), (0, 1.0)],
    "chair_rail": [(0, 0), (0.25, 0.05), (0.42, 0.25), (0.48, 0.5), (0.42, 0.75), (0.25, 0.95), (0, 1.0)],
    "picture_rail": [(0, 0), (0.3, 0.1), (0.45, 0.45), (0.35, 0.8), (0.1, 1.0), (0, 1.0)],
    "quarter_round": [(0, 0), (1.0, 0), (0.92, 0.38), (0.7, 0.7), (0.38, 0.92), (0, 1.0)],
}


def _mask(png):
    a = np.asarray(Image.open(png).convert("RGB"))
    return a.max(-1) > BG_MAX


def section_from_drawing(png, kind, simplify=1.0):
    """The section polygon from a drawn profile: largest drawn region, outline traced
    and simplified, oriented so the flat side (the wall) is at y = 0 and the face
    points out. Falls back to the default for the kind if the drawing is unusable."""
    from scipy import ndimage
    from skimage.measure import approximate_polygon, find_contours
    m = _mask(png)
    lab, n = ndimage.label(m)
    if n == 0:
        return None
    big = lab == (np.argmax(np.bincount(lab.ravel())[1:]) + 1)
    big = ndimage.binary_fill_holes(big)
    ys, xs = np.nonzero(big)
    big = big[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    h, w = big.shape
    if h < 10 or w < 4:
        return None
    edge = max(1, w // 10)
    wall_left = big[:, :edge].mean() >= big[:, -edge:].mean()
    c = max(find_contours(np.pad(big, 1).astype(float), 0.5), key=len)
    c = approximate_polygon(c, tolerance=max(0.5, h / 60 * simplify))
    pts = []
    for r, col in c[:-1]:
        y = (col - 1) / h if wall_left else (w - (col - 1)) / h  # depth from the wall, in heights
        pts.append((max(0.0, y), 1 - (r - 1) / h))
    return pts if len(pts) >= 3 else None


def moulding(sheet, strip, profile, kind, height_m, src_dir, strip_frac=None, name="trim", section_tolerance=1.0):
    """Builds the piece along +x from 0 to PIECE_M, wall at y = 0 (face toward -y), z up."""
    import bmesh
    from . import core, mats
    boxes = panels(sheet, min_area=900)
    img = Image.open(sheet).convert("RGB")
    sb = list(boxes[strip])
    strip_frac = strip_frac or [0.03, 0, 0.97, 1]   # painted strips have shaded end caps: keep them off the repeat
    if strip_frac:
        x0, y0, x1, y1 = sb
        sb = [int(x0 + strip_frac[0] * (x1 - x0)), int(y0 + strip_frac[1] * (y1 - y0)),
              int(x0 + strip_frac[2] * (x1 - x0)), int(y0 + strip_frac[3] * (y1 - y0))]
    spng = _crop(img, sb, src_dir, "strip")
    sec = section_from_drawing(_crop(img, boxes[profile], src_dir, "section"), kind, section_tolerance) if profile is not None \
        else PROFILES[kind]
    if sec is None:
        raise ValueError("unusable drawn moulding cross-section: " + name)
    sec = [(-y * height_m, z * height_m) for y, z in sec]
    sw, sh = Image.open(spng).size
    repeat_m = height_m * sw / sh
    bm = bmesh.new()
    a = [bm.verts.new((0, y, z)) for y, z in sec]
    b = [bm.verts.new((PIECE_M, y, z)) for y, z in sec]
    n = len(sec)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((a[i], a[j], b[j], b[i]))
    bm.faces.new(list(reversed(a)))
    bm.faces.new(b)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    obj = core.mesh_obj(name, bm)
    obj.data.materials.append(mats.image(spng, rough=0.55, grime=0.3, name="trim_" + name, extension="REPEAT"))
    me = obj.data
    attr = me.color_attributes.new("label_uv", "FLOAT_COLOR", "CORNER")
    for li, loop in enumerate(me.loops):
        v = me.vertices[loop.vertex_index].co
        attr.data[li].color = (v.x / repeat_m, min(max(v.z / height_m, 0.002), 0.998), 0, 1)
    depth = max(-y for y, _ in sec)
    return {"length_m": PIECE_M, "height_m": height_m, "depth_m": round(depth, 4), "section_points": n,
            "section_from": "drawing" if profile is not None else "default:" + kind}


def frame(sheet, panel, height_m, src_dir, depth_m=0.022, name="frame", opening_mode="strict"):
    """Extrudes the painted front; a dark opening inside it is cut through."""
    from . import core, mats, trim_checks
    boxes = panels(sheet, min_area=900)
    img = Image.open(sheet).convert("RGB")
    png = _crop(img, boxes[panel], src_dir, "front")
    m = _mask(png)
    H, W = m.shape
    hgt, wid = height_m, height_m * W / H
    front = mats.image(png, rough=0.55, grime=0.3, name="frame_" + name)
    body = core.box((wid, depth_m, hgt), (0, -depth_m / 2, hgt / 2), front, bevel=0.003, name=name)
    body.data.transform(body.matrix_world)
    body.matrix_world.identity()
    # Select a real painted void, not simply the largest dark region (often background).
    # Retry mode handles open-bottom door casings where the void touches the background.
    opening = trim_checks.opening_from_paint(png, opening_mode)
    if opening:
        u0, t0, u1, t1 = opening
        ow, oh = (u1 - u0) * wid, (t1 - t0) * hgt + (0.02 if t1 >= 0.995 else 0)
        cx, cz = (u0 + u1) / 2 * wid - wid / 2, hgt - (t0 + t1) / 2 * hgt
        cut = core.box((ow, depth_m * 4, oh), (cx, -depth_m / 2, cz - (0.01 if t1 >= 0.995 else 0)), None,
                       bevel=0, name="cut")
        core.PARTS.remove(cut)
        mod = body.modifiers.new("open", "BOOLEAN")
        mod.operation = "DIFFERENCE"
        mod.solver = "EXACT"
        mod.object = cut
        core.apply_mods(body)
        import bpy
        bpy.data.objects.remove(cut)
    core.planar_uv(body, 0, 2, wid, hgt)
    at = body.data.color_attributes["label_uv"]
    for li in range(len(body.data.loops)):  # planar_uv centres on 0; this frame stands on z = 0
        u, v, c, d = at.data[li].color
        at.data[li].color = (u, v - 0.5, c, d)
    return {"width_m": round(wid, 3), "height_m": hgt, "depth_m": depth_m, "opening": bool(opening)}
