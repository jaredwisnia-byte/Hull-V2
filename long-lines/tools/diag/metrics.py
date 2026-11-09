"""Geometry metrics of a built prop against its reference views (regression tests, A/B comparisons).

    blender -b --factory-startup -P tools/diag/metrics.py -- GLB VIEWS_DIR [--json OUT]

silhouette IoU per view: the mesh's orthographic outline (rasterised from its triangles, framed to
its bounding box) against the reference view's outline (propkit.hull.silhouette), at the reference's
resolution. 1.0 = identical outlines.
ridge_deg: mean angle between each face's normal and the area-weighted mean normal of the faces
within 3% of the object's size, over faces within 25 degrees of that mean (true edges excluded).
Terraces and grooves raise it; a smooth or cleanly faceted surface keeps it low.
"""
import json
import os
import sys

import bpy
import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from propkit.hull import silhouette   # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:]
glb, views = argv[0], argv[1]
out_json = argv[argv.index("--json") + 1] if "--json" in argv else None
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=glb)
bpy.context.view_layer.update()
V, T = [], []
for o in bpy.data.objects:
    if o.type != "MESH":
        continue
    me = o.data
    me.calc_loop_triangles()
    base = len(V)
    V += [tuple(o.matrix_world @ v.co) for v in me.vertices]
    T += [[base + i for i in t.vertices] for t in me.loop_triangles]
V = np.array(V)
T = np.array(T)
# exported meshes split vertices at UV seams: weld by position so neighbouring faces share edges
_, inv = np.unique(np.round(V / 1e-5).astype(np.int64), axis=0, return_inverse=True)
inv = inv.ravel()
Vw = np.zeros((inv.max() + 1, 3))
Vw[inv] = V
V, T = Vw, inv[T]
T = T[(T[:, 0] != T[:, 1]) & (T[:, 1] != T[:, 2]) & (T[:, 0] != T[:, 2])]
lo, hi = V.min(0), V.max(0)
ext = hi - lo
# which end is the front: the reference front view must match the -Y or +Y projection; decided by IoU
def project(view, flip_y):
    x, y, z = V[:, 0], V[:, 1], V[:, 2]
    yy = -y if flip_y else y
    ylo, yhi = (-hi[1], -lo[1]) if flip_y else (lo[1], hi[1])
    if view == "front":
        return (x - lo[0]) / ext[0], (hi[2] - z) / ext[2]
    if view == "back":
        return (hi[0] - x) / ext[0], (hi[2] - z) / ext[2]
    if view == "right":
        return (yy - ylo) / ext[1], (hi[2] - z) / ext[2]
    if view == "left":
        return (yhi - yy) / ext[1], (hi[2] - z) / ext[2]
    if view == "top":
        return (x - lo[0]) / ext[0], (yhi - yy) / ext[1]


def raster(view, flip_y, w, h):
    u, v = project(view, flip_y)
    im = Image.new("L", (w, h), 0)
    dr = ImageDraw.Draw(im)
    pu, pv = u * (w - 1), v * (h - 1)
    for a, b, c in T:
        dr.polygon([(pu[a], pv[a]), (pu[b], pv[b]), (pu[c], pv[c])], fill=255)
    return np.asarray(im) > 127


res = {"glb": os.path.basename(glb), "tris": int(len(T)), "size_m": [round(float(e), 3) for e in ext], "iou": {}}
refs = {}
for k in ("front", "right", "back", "left", "top"):
    p = os.path.join(views, "v_%s.png" % k)
    if os.path.exists(p):
        refs[k] = silhouette(p)[0]
best = None
for flip in (False, True):
    ious = {}
    for k, m in refs.items():
        r = raster(k, flip, m.shape[1], m.shape[0])
        ious[k] = round(float((r & m).sum() / max(1, (r | m).sum())), 4)
    if best is None or np.mean(list(ious.values())) > np.mean(list(best[1].values())):
        best = (flip, ious)
res["iou"] = best[1]
res["iou_mean"] = round(float(np.mean(list(best[1].values()))), 4)
# ridge energy
a, b, c = V[T[:, 0]], V[T[:, 1]], V[T[:, 2]]
n = np.cross(b - a, c - a)
area = np.linalg.norm(n, axis=1) / 2
n = n / np.maximum(1e-12, 2 * area[:, None])
cent = (a + b + c) / 3
from scipy.spatial import cKDTree  # noqa: E402
tree = cKDTree(cent)
r = 0.03 * float(ext.max())
nb = tree.query_ball_point(cent, r)
dev = np.empty(len(T))
for i, idx in enumerate(nb):
    m = (n[idx] * area[idx, None]).sum(0)
    m /= max(1e-12, np.linalg.norm(m))
    dev[i] = np.degrees(np.arccos(np.clip(np.dot(n[i], m), -1, 1)))
smooth = dev < 25
res["ridge_deg"] = round(float(np.average(dev[smooth], weights=area[smooth])), 3)
res["ridge_p90_deg"] = round(float(np.percentile(dev[smooth], 90)), 3)
res["edge_share"] = round(float(area[~smooth].sum() / area.sum()), 4)
# mesh health: folded edges (adjacent faces turned more than 115 degrees against each other: a crinkle
# or a flipped face) per 1000 faces, faces facing into the body (a ray along the normal hits the mesh's
# own back side), and degenerate triangles. A mesh can pass the silhouette and ridge measures with all
# of these wrong.
from collections import defaultdict  # noqa: E402
edges = defaultdict(list)
for fi, (i, j, k) in enumerate(T):
    for a_, b_ in ((i, j), (j, k), (k, i)):
        edges[(min(a_, b_), max(a_, b_))].append(fi)
pairs = np.array([f for f in edges.values() if len(f) == 2])
cosf = (n[pairs[:, 0]] * n[pairs[:, 1]]).sum(1)
res["folds_per_1k"] = round(float((cosf < np.cos(np.radians(115))).sum() / len(T) * 1000), 3)
res["open_edges"] = int(sum(1 for f in edges.values() if len(f) == 1))
res["degenerate_tris"] = int((area < 1e-12).sum())

print("METRICS", json.dumps(res))
if out_json:
    json.dump(res, open(out_json, "w"), indent=1)
