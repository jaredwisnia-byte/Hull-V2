"""Texture manufacturing: colour a finished mesh from orthographic painted views.

The mesh decides, not the reference sheet. bake.finish later unwraps the mesh into its own UV
atlas and bakes; this module makes what gets baked right:

- every surface point takes a weighted blend of the views, not one view per face:
      weight = facing^4 x visible x resolution
  facing     how squarely the (smoothed) surface faces that view's camera
  visible    1 unless other geometry sits between the point and that camera (ray cast)
  resolution the view's pixels per metre, relative to the best view
- normals used for the choice are smoothed over the surface, so a voxel-carved or decimated
  mesh doesn't flip between views face by face (the patchwork seams);
- where no view sees a point (undersides, inside the cradle) the weight falls back to the
  best-facing view instead of leaving a hole.

project(obj, views, W, D, H, others) -> a material on obj, registered for baking.
views: {"front": path, "back": path, "right": path, "left": path, "top": path} (any subset),
each image cropped tight to the object as seen from that side (front at the image's left in
the right view, front at the bottom of the top view: the hull line's conventions).
"""
import math

import bmesh
import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

DIRS = {"front": Vector((0, -1, 0)), "back": Vector((0, 1, 0)), "right": Vector((1, 0, 0)),
        "left": Vector((-1, 0, 0)), "top": Vector((0, 0, 1))}


def _uv(view, co, W, D, H):
    x, y, z = co
    if view == "front":
        return (x + W / 2) / W, z / H
    if view == "back":
        return 1 - (x + W / 2) / W, z / H
    if view == "right":
        return (y + D / 2) / D, z / H
    if view == "left":
        return 1 - (y + D / 2) / D, z / H
    return (x + W / 2) / W, (y + D / 2) / D          # top: front edge at the image bottom


def smoothed_normals(obj, iters=6):
    me = obj.data
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.verts.ensure_lookup_table()
    n = np.array([list(v.normal) for v in bm.verts])
    nb = [[e.other_vert(v).index for e in v.link_edges] for v in bm.verts]
    for _ in range(iters):
        m = np.array([n[i] + n[js].sum(0) if js else n[i] for i, js in enumerate(nb)])
        n = m / np.maximum(np.linalg.norm(m, axis=1, keepdims=True), 1e-9)
    bm.free()
    return n


def project(obj, views, W, D, H, others=(), name="proj", power=4.0, rough=0.5):
    from . import mats
    me = obj.data
    mw = obj.matrix_world
    names = [k for k in ("front", "back", "right", "left", "top") if k in views]
    sizes = {}
    from PIL import Image
    for k in names:
        w_, h_ = Image.open(views[k]).size
        span = {"front": W, "back": W, "right": D, "left": D, "top": W}[k]
        sizes[k] = w_ / span                                   # pixels per metre
    best = max(sizes.values())
    # Occluders: this mesh and every other part (a handset hides the base beneath it).
    verts, polys = [], []
    for o in [obj] + [o for o in others if o is not obj and o.type == "MESH"]:
        base = len(verts)
        verts += [o.matrix_world @ v.co for v in o.data.vertices]
        polys += [[base + i for i in p.vertices] for p in o.data.polygons]
    tree = BVHTree.FromPolygons(verts, polys)
    sn = smoothed_normals(obj)
    span = max(W, D, H)
    vw = np.zeros((len(me.vertices), len(names)))
    for i, v in enumerate(me.vertices):
        p = mw @ v.co
        nrm = Vector(sn[i])
        for j, k in enumerate(names):
            f = nrm.dot(DIRS[k])
            if f <= 0.05:
                continue
            start = p + nrm * (0.01 * span) + DIRS[k] * (0.004 * span)
            hit = tree.ray_cast(start, DIRS[k], 3 * span)
            if hit[0] is not None and hit[3] > 0.01 * span:
                continue                                       # something is in front of it
            vw[i, j] = f ** power * (sizes[k] / best)
    for i in np.nonzero(vw.sum(1) == 0)[0]:                    # seen by no view: best facing one
        nrm = Vector(sn[i])
        j = int(np.argmax([nrm.dot(DIRS[k]) for k in names]))
        vw[i, j] = 1.0
    vw /= vw.sum(1, keepdims=True)
    # Per-corner UVs for every view, and per-corner weights (packed 4 per colour attribute).
    for k in names:
        # A colour attribute, not a UV map: bake.finish makes the only UV map from the mesh.
        a = me.color_attributes.get("uvp_" + k) or me.color_attributes.new("uvp_" + k, "FLOAT_COLOR", "CORNER")
        for li, loop in enumerate(me.loops):
            u_, v_ = _uv(k, mw @ me.vertices[loop.vertex_index].co, W, D, H)
            a.data[li].color = (u_, v_, 0, 1)
    packs = [names[i:i + 4] for i in range(0, len(names), 4)]
    for pi, pack in enumerate(packs):
        a = me.color_attributes.get("vw%d" % pi) or me.color_attributes.new("vw%d" % pi, "FLOAT_COLOR", "CORNER")
        for li, loop in enumerate(me.loops):
            ws = [vw[loop.vertex_index, names.index(k)] for k in pack] + [0.0] * (4 - len(pack))
            a.data[li].color = ws
    # One material: sum over views of image(uv_view) x weight_view.
    m, nt, bsdf, out = mats._new("proj_" + name)
    acc = None
    for pi, pack in enumerate(packs):
        wattr = nt.nodes.new("ShaderNodeAttribute")
        wattr.attribute_type = "GEOMETRY"
        wattr.attribute_name = "vw%d" % pi
        sep = nt.nodes.new("ShaderNodeSeparateColor")
        nt.links.new(wattr.outputs["Color"], sep.inputs["Color"])
        for ci, k in enumerate(pack):
            uva = nt.nodes.new("ShaderNodeAttribute")
            uva.attribute_type = "GEOMETRY"
            uva.attribute_name = "uvp_" + k
            img = nt.nodes.new("ShaderNodeTexImage")
            img.image = bpy.data.images.load(views[k], check_existing=True)
            img.extension = "EXTEND"
            nt.links.new(uva.outputs["Vector"], img.inputs["Vector"])
            mul = nt.nodes.new("ShaderNodeMix")
            mul.data_type = "RGBA"
            mul.blend_type = "MULTIPLY"
            mul.inputs["Factor"].default_value = 1.0
            nt.links.new(img.outputs["Color"], mul.inputs[6])
            ch = sep.outputs[("Red", "Green", "Blue")[ci]] if ci < 3 else wattr.outputs["Alpha"]
            comb = nt.nodes.new("ShaderNodeCombineColor")
            for c_ in ("Red", "Green", "Blue"):
                nt.links.new(ch, comb.inputs[c_])
            nt.links.new(comb.outputs["Color"], mul.inputs[7])
            if acc is None:
                acc = mul.outputs[2]
            else:
                add = nt.nodes.new("ShaderNodeMix")
                add.data_type = "RGBA"
                add.blend_type = "ADD"
                add.inputs["Factor"].default_value = 1.0
                nt.links.new(acc, add.inputs[6])
                nt.links.new(mul.outputs[2], add.inputs[7])
                acc = add.outputs[2]
    me.materials.clear()
    me.materials.append(m)
    for p in me.polygons:
        p.material_index = 0
    mats.register("proj_" + name, m, bsdf, out, acc, rough, 0.0)
    cover = {k: round(float((vw[:, j] > 0.5).mean()), 3) for j, k in enumerate(names)}
    return {"views": names, "dominant_share": cover,
            "unseen_vertices": int((np.sort(vw, 1)[:, -1] >= 0.999).sum())}


def uv_quality(obj):
    """After unwrapping: how evenly texture is spread over the surface. stretch = a face's UV
    area / 3-D area, relative to the median face. Distorted = stretch outside 1/2..2."""
    me = obj.data
    uv = me.uv_layers.active
    if uv is None:
        return {}
    r = []
    for p in me.polygons:
        if p.area <= 1e-12:
            continue
        pts = [uv.data[li].uv for li in p.loop_indices]
        a = 0.5 * abs(sum(pts[i].x * pts[(i + 1) % len(pts)].y - pts[(i + 1) % len(pts)].x * pts[i].y
                          for i in range(len(pts))))
        r.append((a / p.area, p.area))
    if not r:
        return {}
    ratios = np.array([x for x, _ in r])
    areas = np.array([w for _, w in r])
    med = np.median(ratios[ratios > 0]) if (ratios > 0).any() else 1
    s = ratios / med
    bad = (s < 0.5) | (s > 2.0)
    return {"distorted_area_fraction": round(float(areas[bad].sum() / areas.sum()), 4),
            "uv_coverage": round(float(ratios.dot(areas)), 4)}
