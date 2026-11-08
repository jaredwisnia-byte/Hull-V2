"""Puts the model's front depth (ray cast) beside the reference depth map of a sheet set, to
spot geometry the reference does not show (liberties) or relief it shows that the model lacks.

    blender -b --factory-startup -P tools/match_check.py -- MODEL.glb MANIFEST.json OUT.png
"""
import bpy, sys, json, numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from PIL import Image
a = sys.argv[sys.argv.index("--") + 1:]
glb, man, out = a[0], a[1], a[2]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=glb)
dg = bpy.context.evaluated_depsgraph_get()
verts, polys = [], []
for o in [x for x in bpy.data.objects if x.type == "MESH"]:
    me = o.evaluated_get(dg).to_mesh(); b = len(verts)
    verts += [o.matrix_world @ v.co for v in me.vertices]; polys += [[b + i for i in p.vertices] for p in me.polygons]
t = BVHTree.FromPolygons(verts, polys)
lo = Vector([min(v[i] for v in verts) for i in range(3)]); hi = Vector([max(v[i] for v in verts) for i in range(3)])
m = json.load(open(man)); x0, y0, x1, y1 = m["depth_map"]["view_bboxes_px"]["front"]
ref = Image.open(man.replace("manifest.json", m["depth_map"]["filename"])).convert("L").crop((x0, y0, x1, y1))
W, H = 160, int(160 * (y1 - y0) / (x1 - x0))
d = np.zeros((H, W))
for j in range(H):
    for i in range(W):
        loc, n, idx, dist = t.ray_cast(Vector((lo.x + (i + .5) / W * (hi.x - lo.x), lo.y - 1, hi.z - (j + .5) / H * (hi.z - lo.z))), Vector((0, 1, 0)), 10)
        d[j, i] = (loc.y - (lo.y - 1)) if loc else 0
hit = d > 0
dd = np.where(hit, d[hit].max() - d, 0) if hit.any() else d   # nearer = brighter, like the reference
dd = np.where(hit, 0.25 + 0.75 * (dd - dd[hit].min()) / max(1e-6, np.ptp(dd[hit])), 0)
img = Image.fromarray((dd * 255).astype(np.uint8)).resize((x1 - x0, y1 - y0))
S = Image.new("L", ((x1 - x0) * 2 + 10, y1 - y0)); S.paste(ref, (0, 0)); S.paste(img, (x1 - x0 + 10, 0)); S.save(out)
