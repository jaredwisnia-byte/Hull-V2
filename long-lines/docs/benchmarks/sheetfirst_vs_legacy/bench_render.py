"""Identical renders and measurements for every benchmark model.

    blender -b --factory-startup -P bench_render.py -- OBJ VERSION

Cameras are placed from the agreed real-world box of the object (not the model's own bounds),
so a wrongly sized model shows it. Same lights, samples, resolution for all models. Each model is
shaded with its own exported maps (albedo, normal, ORM): what the game would get.
Writes renders/<obj>_<ver>_<view>.png, uv/<obj>_<ver>_uv.png, metrics/<obj>_<ver>.json.
"""
import json
import math
import os
import sys
import time

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
OBJ, VER = sys.argv[sys.argv.index("--") + 1:][:2]
BOX = {  # agreed real-world boxes: centre, size (x, y, z) in metres
    "oven": ((0, 0, 0.565), (0.76, 0.66, 1.13)),
    "fridge": ((0, 0, 0.825), (0.775, 0.75, 1.65)),
    "crown": ((0.6, -0.0825, 0.14), (1.2, 0.165, 0.28)),
    "tv": ((0, 0, 0.24), (0.662, 0.308, 0.48)),
    "armchair": ((0, 0, 0.425), (0.8, 0.85, 0.85)),
}
centre, size = (Vector(BOX[OBJ][0]), Vector(BOX[OBJ][1]))
d = os.path.join(HERE, "glb", "%s_%s" % (VER, OBJ))
name = "bench_%s_%s" % (VER.lower(), OBJ)
for sub in ("renders", "uv", "metrics"):
    os.makedirs(os.path.join(HERE, sub), exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=os.path.join(d, name + ".glb"))
objs = [o for o in bpy.data.objects if o.type == "MESH"]


def tex(nt, fn, cs):
    n = nt.nodes.new("ShaderNodeTexImage")
    n.image = bpy.data.images.load(os.path.join(d, fn))
    n.image.colorspace_settings.name = cs
    return n


# Shade every model the same way from its own maps.
mat = bpy.data.materials.new("bench")
mat.use_nodes = True
nt = mat.node_tree
bsdf = nt.nodes["Principled BSDF"]
alb = tex(nt, name + "_albedo.png", "sRGB")
nt.links.new(alb.outputs["Color"], bsdf.inputs["Base Color"])
nrm = tex(nt, name + "_normal.png", "Non-Color")
nm = nt.nodes.new("ShaderNodeNormalMap")
nt.links.new(nrm.outputs["Color"], nm.inputs["Color"])
nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
orm = tex(nt, name + "_orm.png", "Non-Color")
sep = nt.nodes.new("ShaderNodeSeparateColor")
nt.links.new(orm.outputs["Color"], sep.inputs["Color"])
nt.links.new(sep.outputs["Green"], bsdf.inputs["Roughness"])
nt.links.new(sep.outputs["Blue"], bsdf.inputs["Metallic"])
for o in objs:
    o.data.materials.clear()
    o.data.materials.append(mat)

sc = bpy.context.scene
sc.render.engine = "CYCLES"
sc.cycles.samples = 48
sc.cycles.use_denoising = False
sc.render.resolution_x = sc.render.resolution_y = 480
sc.render.film_transparent = False
w = bpy.data.worlds.new("w")
sc.world = w
w.use_nodes = True
w.node_tree.nodes["Background"].inputs["Color"].default_value = (0.42, 0.44, 0.48, 1)
w.node_tree.nodes["Background"].inputs["Strength"].default_value = 1.6
sun = bpy.data.objects.new("sun", bpy.data.lights.new("sun", "SUN"))
sun.data.energy = 3.0
sun.rotation_euler = (math.radians(50), 0, math.radians(-30))
sc.collection.objects.link(sun)
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
sc.collection.objects.link(cam)
sc.camera = cam

VIEWS = {  # direction from centre to camera, up vector, orthographic extent (w, h)
    "front": (Vector((0, -1, 0)), (size.x, size.z)),
    "side": (Vector((1, 0, 0)), (size.y, size.z)),
    "rear": (Vector((0, 1, 0)), (size.x, size.z)),
    "top": (Vector((0, 0, 1)), (size.x, size.y)),
}
for view, (dirn, ext) in list(VIEWS.items()) + [("threequarter", (Vector((0.62, -0.75, 0.45)).normalized(), None))]:
    dist = 6 * max(size)
    cam.location = centre + dirn * dist
    up = Vector((0, 1, 0)) if view == "top" else Vector((0, 0, 1))
    cam.rotation_euler = (-dirn).to_track_quat("-Z", "Y").to_euler() if view != "top" else (0, 0, 0)
    if ext:
        cam.data.type = "ORTHO"
        cam.data.ortho_scale = 1.15 * max(ext)
    else:
        cam.data.type = "PERSP"
        cam.data.lens = 85
        cam.location = centre + dirn * (max(size) * 3.2)
        cam.rotation_euler = (centre - cam.location).to_track_quat("-Z", "Y").to_euler()
    cam.data.clip_end = dist * 3
    sc.render.filepath = os.path.join(HERE, "renders", "%s_%s_%s.png" % (OBJ, VER, view))
    bpy.ops.render.render(write_still=True)

# ---------------------------------------------------------------- measurements
dg = bpy.context.evaluated_depsgraph_get()
verts, polys, uvtris, faces3 = [], [], [], []
for o in objs:
    me = o.evaluated_get(dg).to_mesh()
    me.calc_loop_triangles()
    base = len(verts)
    verts += [o.matrix_world @ v.co for v in me.vertices]
    uv = me.uv_layers.active
    for t in me.loop_triangles:
        polys.append([base + i for i in t.vertices])
        uvtris.append([tuple(uv.data[li].uv) for li in t.loops] if uv else None)
V = np.array([list(v) for v in verts])
lo, hi = V.min(0), V.max(0)
m = {"object": OBJ, "version": VER, "tris": len(polys), "size_m": [round(float(x), 3) for x in hi - lo],
     "target_m": list(size)}
m["dimension_error_pct"] = [round(float(abs(a - b) / b * 100), 1) for a, b in zip(hi - lo, size)]
# Open edges: a closed solid has every edge shared by exactly two triangles.
from collections import Counter
ec = Counter()
for p in polys:
    for i in range(3):
        a, b = p[i], p[(i + 1) % 3]
        ka, kb = tuple(np.round(V[a], 5)), tuple(np.round(V[b], 5))
        ec[(min(ka, kb), max(ka, kb))] += 1
m["open_edges"] = int(sum(1 for c in ec.values() if c == 1))
m["nonmanifold_edges"] = int(sum(1 for c in ec.values() if c > 2))
# UV distortion per triangle: singular values of the 3-D -> UV map, relative to the median scale.
scales, conf, areas = [], [], []
for p, t in zip(polys, uvtris):
    if t is None:
        continue
    P = V[p]
    e1, e2 = P[1] - P[0], P[2] - P[0]
    n1 = np.linalg.norm(e1)
    if n1 < 1e-9:
        continue
    x = e1 / n1
    nrm_ = np.cross(e1, e2)
    a3 = np.linalg.norm(nrm_) / 2
    if a3 < 1e-12:
        continue
    y = np.cross(nrm_ / (2 * a3), x)
    p2 = np.array([[0, 0], [n1, 0], [e2 @ x, e2 @ y]])
    uvt = np.array(t)
    A = np.array([p2[1] - p2[0], p2[2] - p2[0]]).T
    B = np.array([uvt[1] - uvt[0], uvt[2] - uvt[0]]).T
    try:
        J = B @ np.linalg.inv(A)
    except np.linalg.LinAlgError:
        continue
    s = np.linalg.svd(J, compute_uv=False)
    if s[1] <= 1e-12:
        conf.append(50.0)
        scales.append(0.0)
    else:
        conf.append(float(s[0] / s[1]))
        scales.append(float(math.sqrt(s[0] * s[1])))
    areas.append(a3)
areas = np.array(areas)
scales = np.array(scales)
med = np.median(scales[scales > 0]) if (scales > 0).any() else 1
rel = scales / med
m["uv_area_distorted_pct"] = round(float(areas[(rel < 0.5) | (rel > 2)].sum() / areas.sum() * 100), 1)
m["uv_angle_distortion_mean"] = round(float(np.average(np.minimum(conf, 50), weights=areas)), 2)
m["uv_angle_distorted_pct"] = round(float(areas[np.array(conf) > 2].sum() / areas.sum() * 100), 1)

# Orthographic silhouettes by ray casting (in the agreed box frame).
tree = BVHTree.FromPolygons(verts, polys)


def silhouette(view, n=128):
    dirn, ext = VIEWS[view]
    wv, hv = ext
    h = max(8, int(n * hv / wv))
    out = np.zeros((h, n), bool)
    for j in range(h):
        for i in range(n):
            a, b = (i + .5) / n - .5, .5 - (j + .5) / h
            if view == "front":
                o_ = centre + Vector((a * wv, -3, b * hv)); r = Vector((0, 1, 0))
            elif view == "side":
                o_ = centre + Vector((3, a * wv, b * hv)); r = Vector((-1, 0, 0))
            else:  # top
                o_ = centre + Vector((a * wv, -b * hv, 3)); r = Vector((0, 0, -1))
            out[j, i] = tree.ray_cast(o_, r, 10)[0] is not None
    return out


def mask_iou(model_mask, ref_mask):
    from scipy import ndimage
    ys, xs = np.nonzero(ref_mask)
    ref = ref_mask[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    ref = np.asarray(Image.fromarray(ref.astype(np.uint8) * 255).resize(model_mask.shape[::-1])) > 127
    return round(float((ref & model_mask).sum() / max(1, (ref | model_mask).sum())), 3)


refs = json.load(open(os.path.join(HERE, "reference_views.json")))
ious = {}
for view, spec in refs.get(OBJ, {}).get("silhouettes", {}).items():
    im = np.asarray(Image.open(os.path.join(HERE, spec["file"])).convert("RGB")).astype(int)
    crop = im[spec["box"][1]:spec["box"][3], spec["box"][0]:spec["box"][2]]
    ref_mask = np.abs(crop - crop[0, 0]).sum(-1) > 60
    sil = silhouette("side" if view == "profile" else view)
    if view == "profile":   # the drawn section may face either way: score the better orientation
        ious[view] = max(mask_iou(sil, ref_mask), mask_iou(sil[:, ::-1], ref_mask))
    else:
        ious[view] = mask_iou(sil, ref_mask)
m["silhouette_iou"] = ious

# Texture placement: flat-lit front render vs the reference front (grayscale correlation).
tp = refs.get(OBJ, {}).get("front_texture")
if tp:
    em = bpy.data.materials.new("flat")
    em.use_nodes = True
    ent = em.node_tree
    ent.nodes.remove(ent.nodes["Principled BSDF"])
    a2 = tex(ent, name + "_albedo.png", "sRGB")
    e = ent.nodes.new("ShaderNodeEmission")
    ent.links.new(a2.outputs["Color"], e.inputs["Color"])
    ent.links.new(e.outputs["Emission"], ent.nodes["Material Output"].inputs["Surface"])
    for o in objs:
        o.data.materials.clear()
        o.data.materials.append(em)
    sun.data.energy = 0
    w.node_tree.nodes["Background"].inputs["Strength"].default_value = 0
    dirn, ext = VIEWS["front"]
    cam.data.type = "ORTHO"
    cam.data.ortho_scale = max(ext)
    cam.location = centre + dirn * 6 * max(size)
    cam.rotation_euler = (-dirn).to_track_quat("-Z", "Y").to_euler()
    sc.render.resolution_x = 256
    sc.render.resolution_y = int(256 * ext[1] / ext[0]) if ext[0] >= ext[1] else 256
    sc.render.resolution_x = 256 if ext[0] >= ext[1] else int(256 * ext[0] / ext[1])
    sc.cycles.samples = 8
    fp = os.path.join(HERE, "metrics", "%s_%s_flatfront.png" % (OBJ, VER))
    sc.render.filepath = fp
    bpy.ops.render.render(write_still=True)
    got = np.asarray(Image.open(fp).convert("L").resize((128, 128))).astype(float)
    ref = np.asarray(Image.open(os.path.join(HERE, tp["file"])).convert("L").crop(tuple(tp["box"])).resize((128, 128))).astype(float)
    msk = (got > 8) & (ref > 30)
    if msk.sum() > 50:
        m["front_texture_correlation"] = round(float(np.corrcoef(got[msk], ref[msk])[0, 1]), 3)
        m["front_texture_coverage"] = round(float(msk.mean()), 3)

json.dump(m, open(os.path.join(HERE, "metrics", "%s_%s.json" % (OBJ, VER)), "w"), indent=1)

# UV layout: triangle edges drawn over the model's albedo atlas.
atlas = Image.open(os.path.join(d, name + "_albedo.png")).convert("RGB")
s_ = 900 / max(atlas.size)
atlas = atlas.resize((int(atlas.size[0] * s_), int(atlas.size[1] * s_)))
dr = ImageDraw.Draw(atlas)
for t in uvtris:
    if t:
        pts = [(u * atlas.size[0], (1 - v) * atlas.size[1]) for u, v in t]
        dr.line(pts + [pts[0]], fill=(0, 255, 120), width=1)
atlas.save(os.path.join(HERE, "uv", "%s_%s_uv.png" % (OBJ, VER)))
print("METRICS", json.dumps(m))
