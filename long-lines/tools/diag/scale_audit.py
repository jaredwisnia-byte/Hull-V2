"""Human-scale audit of built props: does what we built fit a person?

For each library prop whose kind has handbook contacts (factory/reference_handbook.json), the
contacts are measured on the built mesh and solved like a drawing (propkit/human_scale.py). A scale of
1.00 means the prop is the size a person needs; 1.10 means it should be 10% bigger. Nothing is changed.

    blender -b --factory-startup -P tools/diag/scale_audit.py -- NAME [NAME ...] [--json OUT]

Measures on a mesh: whole width / depth / height (its box), and for a "seat": the up-facing level open to
the sky with the most area in the middle third of the width (top_height) and that level's front-to-back extent
(depth).
"""
import json
import os
import sys

import bpy
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from propkit import handbook as HB, human_scale as HS  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:]
out_json = None
if "--json" in argv:
    out_json = argv[argv.index("--json") + 1]
    argv = argv[:argv.index("--json")]


def kind_entry(name):
    for k, v in HB.data()["objects"].items():
        for a in [k] + v.get("aka", []):
            if a in name:
                return HB.entry(k)
    return None


def load(name):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=os.path.join(ROOT, "assets", "props", name, name + ".glb"))
    V, F, N, A = [], [], [], []
    for o in bpy.context.scene.objects:
        if o.type != "MESH":
            continue
        mw = o.matrix_world
        base = len(V)
        V += [tuple(mw @ v.co) for v in o.data.vertices]
        for p in o.data.polygons:
            F.append([base + i for i in p.vertices])
            N.append(tuple((mw.to_3x3() @ p.normal).normalized()))
            A.append(p.area)
    return np.array(V), F, np.array(N), np.array(A)


def measure(c, V, F, N, A):
    lo, hi = V.min(0), V.max(0)
    W, D, H = hi - lo
    if c["part"] == "whole":
        return {"width": W, "depth": D, "height": H}.get(c["measure"])
    if c["part"] == "seat":
        cen = np.array([V[f].mean(0) for f in F])
        mid = (np.abs(cen[:, 0] - (lo[0] + hi[0]) / 2) < W / 6) & (N[:, 2] > 0.9) & (cen[:, 2] - lo[2] < 0.8 * H)
        # only what is open to the sky: the platform under the cushions is flat and big, but nobody sits on it
        from mathutils import Vector
        from mathutils.bvhtree import BVHTree
        tree = BVHTree.FromPolygons([tuple(v) for v in V], F)
        for i in np.nonzero(mid)[0]:
            if tree.ray_cast(Vector(cen[i]) + Vector((0, 0, 1e-3)), Vector((0, 0, 1)), 10)[0] is not None:
                mid[i] = False
        if not mid.any():
            return None
        z = cen[mid, 2] - lo[2]
        bins = np.round(z / 0.02)
        levels, inv = np.unique(bins, return_inverse=True)
        area = np.bincount(inv, weights=A[mid])
        top = levels[np.argmax(area)]
        sel = bins == top
        if c["measure"] == "top_height":
            return float(np.average(z[sel], weights=A[mid][sel]))
        if c["measure"] == "depth":
            ys = cen[mid, 1][sel]
            return float(ys.max() - ys.min())
    return None


rows = {}
for name in argv:
    e = kind_entry(name)
    if not e or not HB.contacts(e):
        rows[name] = {"skipped": "no handbook contacts for this kind"}
        continue
    V, F, N, A = load(name)
    anchors, unmeasured = [], []
    for c in HB.contacts(e):
        v = measure(c, V, F, N, A)
        if v:
            anchors.append(HS.anchor(c, v))
        else:
            unmeasured.append("%s %s" % (c["part"], c["measure"]))
    if not anchors:
        rows[name] = {"kind": e["name"], "skipped": "no contact measurable", "unmeasured": unmeasured}
        continue
    k, rep = HS.solve(anchors)
    rows[name] = dict(kind=e["name"], built_m=[round(float(x), 3) for x in V.max(0) - V.min(0)],
                      human_scale_factor=round(k, 3), unmeasured=unmeasured, **rep)
    rows[name].pop("scale_range")
    print("SCALE %-20s x%.2f  %s" % (name, k, "; ".join("%s %s mm (%s-%s)%s" % (
        r["contact"], round(r["measured"] * 1000), r["human_range_mm"][0], r["human_range_mm"][1],
        "" if r["agrees"] else " OFF") for r in rep["contacts"])))
print("SCALE_AUDIT " + json.dumps(rows))
if out_json:
    json.dump(rows, open(out_json, "w"), indent=1)
