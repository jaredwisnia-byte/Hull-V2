"""Visual hull: a 3D model from orthographic painted views (front, side, top...).

Each view's outline is cut out of a block of voxels; what survives every view is the
object. The surface is extracted with marching cubes, lightly smoothed, decimated,
and every face is painted from the view it faces. One call turns a sheet of views
into a textured prop, so any object drawn in front/side/top views needs no modelling.

    from propkit.hull import hull_prop
    hull_prop({"front": "front.png", "right": "right.png", "top": "top.png",
               "back": "back.png", "left": "left.png"}, height=0.5)

View conventions (as on a typical sheet): front = seen from the front; right = seen
from the object's right side, so the front is on the image's LEFT; left = seen from the
left side, front on the RIGHT; back = seen from behind; top = seen from above with the
front at the BOTTOM of the image. Only front and one side are required.
"""
import math

import bmesh
import bpy
import numpy as np
from PIL import Image
from scipy import ndimage
from skimage.measure import marching_cubes
from skimage.morphology import convex_hull_image

from . import mats as M
from .core import apply_mods, link, smooth


def silhouette(path, thresh=30, convex=False):
    """Mask of the object in a view: differs from the border colour, biggest
    connected shape, holes filled. Returns (mask, cropped colour image)."""
    im = Image.open(path).convert("RGB")
    a = np.asarray(im).astype(np.int32)
    border = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])
    bg = np.median(border, axis=0)
    m = np.abs(a - bg).sum(2) > thresh
    m = ndimage.binary_closing(m, iterations=2)
    lab, n = ndimage.label(m)
    if n == 0:
        raise ValueError("no object found in " + path)
    sizes = ndimage.sum(m, lab, range(1, n + 1))
    m = lab == (int(np.argmax(sizes)) + 1)
    # Dark parts of an object (screens, back panels) can match a dark sheet
    # background. Treat anything bounded by the object both along its row and
    # its column as solid; outer notches (between legs, under a lip) stay open.
    rows = np.zeros_like(m)
    cols = np.zeros_like(m)
    for i in np.nonzero(m.any(1))[0]:
        xs = np.nonzero(m[i])[0]
        rows[i, xs[0]:xs[-1] + 1] = True
    for j in np.nonzero(m.any(0))[0]:
        ys = np.nonzero(m[:, j])[0]
        cols[ys[0]:ys[-1] + 1, j] = True
    m = ndimage.binary_fill_holes(m | (rows & cols))
    if convex:
        m = convex_hull_image(m)
    ys, xs = np.nonzero(m)
    box = (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1)
    return m[box[1]:box[3], box[0]:box[2]], im.crop(box)


def _sample(mask, u, v):
    """mask sampled at normalised coords u (0 left..1 right), v (0 top..1 bottom)."""
    h, w = mask.shape
    ix = np.clip((u * (w - 1)).round().astype(int), 0, w - 1)
    iy = np.clip((v * (h - 1)).round().astype(int), 0, h - 1)
    return mask[iy, ix]


def hull_prop(views, height, res=110, smooth_iters=4, decimate=0.35, rough=0.5, name="hull",
              convex=False, paint_only=()):
    """convex: fill each outline to its convex shape (boxy objects; dark areas can't
    punch holes). paint_only: views used for texture but not trusted to carve (e.g. a
    dark back panel on a dark sheet)."""
    sil = {k: silhouette(p, convex=convex) for k, p in views.items()}
    carve = {k: v for k, v in sil.items() if k not in paint_only}
    fm, fim = sil["front"]
    side_key = "right" if "right" in sil else "left"
    sm, _ = sil[side_key]
    H = height
    W = H * fm.shape[1] / fm.shape[0]
    D = H * sm.shape[1] / sm.shape[0]
    nx = res
    ny = max(8, int(res * D / W))
    nz = max(8, int(res * H / W))
    x = (np.arange(nx) + 0.5) / nx  # 0 = left (-X), 1 = right (+X)
    y = (np.arange(ny) + 0.5) / ny  # 0 = front (-Y), 1 = back (+Y)
    z = (np.arange(nz) + 0.5) / nz  # 0 = bottom, 1 = top
    X, Yy, Z = np.meshgrid(x, y, z, indexing="ij")
    keep = _sample(fm, X, 1 - Z)
    if "back" in carve:
        keep &= _sample(carve["back"][0], 1 - X, 1 - Z)
    if "right" in carve:
        keep &= _sample(carve["right"][0], Yy, 1 - Z)
    if "left" in carve:
        keep &= _sample(carve["left"][0], 1 - Yy, 1 - Z)
    if "top" in carve:
        keep &= _sample(carve["top"][0], X, 1 - Yy)
    vol = np.pad(keep.astype(np.float32), 1)
    vol = ndimage.gaussian_filter(vol, 0.7)
    verts, faces, _, _ = marching_cubes(vol, 0.5)
    verts -= 1.0
    sx, sy, sz = W / nx, D / ny, H / nz
    bm = bmesh.new()
    bv = [bm.verts.new(((vx + 0.5) * sx - W / 2, (vy + 0.5) * sy - D / 2, (vz + 0.5) * sz)) for vx, vy, vz in verts]
    for a, b, c in faces:
        try:
            bm.faces.new((bv[a], bv[c], bv[b]))
        except ValueError:
            pass
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    obj = link(bpy.data.objects.new(name, me))
    sm_mod = obj.modifiers.new("smooth", "SMOOTH")
    sm_mod.iterations = smooth_iters
    sm_mod.factor = 0.5
    dec = obj.modifiers.new("dec", "DECIMATE")
    dec.ratio = decimate
    apply_mods(obj)
    # Paint each face from the view it faces.
    order = ["front", "back", "right", "left", "top"]
    mats_ = {}
    for k in order:
        if k in sil:
            path = "/tmp/_hull_%s_%s.png" % (name, k)
            sil[k][1].save(path)
            mats_[k] = M.image(path, rough, 0.25, 0.05, name="%s_%s" % (name, k))
            obj.data.materials.append(mats_[k])
    slot = {k: i for i, k in enumerate([k for k in order if k in mats_])}
    attr = obj.data.color_attributes.new("label_uv", "FLOAT_COLOR", "CORNER")
    me = obj.data
    for poly in me.polygons:
        n = poly.normal
        cands = {"front": -n.y, "back": n.y, "right": n.x, "left": -n.x, "top": n.z}
        k = max((c for c in cands if c in slot), key=lambda c: cands[c])
        poly.material_index = slot[k]
        for li in poly.loop_indices:
            v = me.vertices[me.loops[li].vertex_index].co
            u_, w_ = (v.x + W / 2) / W, v.z / H
            if k == "back":
                u_ = 1 - u_
            elif k == "right":
                u_ = (v.y + D / 2) / D
            elif k == "left":
                u_ = 1 - (v.y + D / 2) / D
            elif k == "top":
                w_ = 1 - (v.y + D / 2) / D
            attr.data[li].color = (u_, w_, 0, 1)
    return smooth(obj, 50)
