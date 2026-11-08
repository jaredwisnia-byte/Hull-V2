"""The factory's quality gate: measures a built prop against factory/standards.json.

check(name, views_dir=None, category=None) -> {"pass": bool, "fails": [...], "metrics": {...}}

Fast (ray casts and mesh statistics, no rendering), so the whole library can be gated
in one Blender process. The visual turnaround stays in tools/critique.py and is only
rendered for failures or spot checks: the gate enforces a minimum standard, not polish.
"""
import json
import os

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
LIB = os.path.join(ROOT, "assets", "props")
STANDARDS = json.load(open(os.path.join(ROOT, "factory", "standards.json")))
MIN = STANDARDS["minimum_acceptable"]


def size_class(max_dim, category_class=None):
    if category_class:
        return category_class
    for k, v in STANDARDS["size_classes"].items():
        if max_dim <= v["max_dim_m"]:
            return k
    return "building"


def _load(name):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=os.path.join(LIB, name, name + ".glb"))
    return [o for o in bpy.data.objects if o.type == "MESH"]


def check(name, views_dir=None, category_class=None, paint_only=(), solid=False, mount="floor"):
    m, fails = {}, []
    d = os.path.join(LIB, name)
    for suffix in (".glb", "_albedo.png", "_normal.png", "_orm.png"):
        if not os.path.exists(os.path.join(d, name + suffix)):
            fails.append("missing file " + name + suffix)
    if fails:
        return {"pass": False, "fails": fails, "metrics": m}
    try:
        objs = _load(name)
    except Exception as e:  # file integrity
        return {"pass": False, "fails": ["GLB does not load: %s" % e], "metrics": m}
    dg = bpy.context.evaluated_depsgraph_get()
    verts, polys, area, uv_area = [], [], 0.0, 0.0
    for o in objs:
        me = o.evaluated_get(dg).to_mesh()
        base = len(verts)
        verts += [o.matrix_world @ v.co for v in me.vertices]
        polys += [[base + i for i in p.vertices] for p in me.polygons]
        uv = me.uv_layers.active
        for p in me.polygons:
            area += p.area
            if uv:
                pts = [uv.data[li].uv for li in p.loop_indices]
                uv_area += 0.5 * abs(sum(pts[i].x * pts[(i + 1) % len(pts)].y - pts[(i + 1) % len(pts)].x * pts[i].y
                                         for i in range(len(pts))))
    tris = sum(len(p) - 2 for p in polys)
    lo = Vector([min(v[i] for v in verts) for i in range(3)])
    hi = Vector([max(v[i] for v in verts) for i in range(3)])
    size = hi - lo
    tex = Image.open(os.path.join(d, name + "_albedo.png")).size[0]
    cls = size_class(max(size), category_class)
    budget = STANDARDS["size_classes"][cls]["tri_budget"]
    density = tex * (uv_area / area) ** 0.5 if area > 0 and uv_area > 0 else 0
    m.update({"tris": tris, "size_m": [round(s, 3) for s in size], "class": cls, "tex": tex,
              "texel_density": round(density), "lowest_z": round(lo.z, 4)})
    if tris > budget:
        fails.append("over triangle budget: %d > %d (%s)" % (tris, budget, cls))
    lo_d, hi_d = STANDARDS["size_classes"][cls].get("texel_density_px_per_m", MIN["texel_density_px_per_m"])
    if not lo_d <= density <= hi_d:
        fails.append("texel density %d px/m outside %d-%d" % (density, lo_d, hi_d))
    from .texturing import uv_quality
    uq = {}
    for o in objs:
        q = uv_quality(o)
        if q:
            uq = q if not uq or q["distorted_area_fraction"] > uq["distorted_area_fraction"] else uq
    m.update(uq)
    if uq and uq["distorted_area_fraction"] > MIN.get("max_uv_distorted_fraction", 1.0):
        fails.append("UV stretch: %.0f%% of the surface is distorted more than 2x" % (uq["distorted_area_fraction"] * 100))
    m["mount"] = mount
    if mount == "floor" and abs(lo.z) > MIN["floor_tolerance_m"]:
        fails.append("not standing on z = 0 (lowest point %.3f m)" % lo.z)

    tree = BVHTree.FromPolygons(verts, polys)
    views = {
        "front": (Vector((0, 1, 0)), lambda u, v: Vector((lo.x + u * size.x, lo.y - 1, lo.z + v * size.z)), size.z / max(size.x, 1e-6)),
        "back": (Vector((0, -1, 0)), lambda u, v: Vector((hi.x - u * size.x, hi.y + 1, lo.z + v * size.z)), size.z / max(size.x, 1e-6)),
        "right": (Vector((-1, 0, 0)), lambda u, v: Vector((hi.x + 1, lo.y + u * size.y, lo.z + v * size.z)), size.z / max(size.y, 1e-6)),
        "left": (Vector((1, 0, 0)), lambda u, v: Vector((lo.x - 1, hi.y - u * size.y, lo.z + v * size.z)), size.z / max(size.y, 1e-6)),
        "top": (Vector((0, 0, -1)), lambda u, v: Vector((lo.x + u * size.x, hi.y - v * size.y, hi.z + 1)), size.y / max(size.x, 1e-6)),
    }
    back_hits, hits = 0, 0
    sil = {}
    for k, (direc, origin, aspect) in views.items():
        n = 72
        w, h = n, max(6, min(240, int(n * aspect)))
        got = np.zeros((h, w), bool)
        for j in range(h):
            for i in range(w):
                loc, nor, idx, dist = tree.ray_cast(origin((i + 0.5) / w, 1 - (j + 0.5) / h), direc, 10)
                if loc is not None:
                    got[j, i] = True
                    hits += 1
                    if nor.dot(direc) > 0:
                        back_hits += 1
        sil[k] = got
    back_frac = back_hits / max(hits, 1)
    m["backfacing_fraction"] = round(back_frac, 3)
    if solid and back_frac > MIN["max_backfacing_fraction"]:  # thin leaves and cloth have no inside
        fails.append("%.0f%% of visible faces point inward (flipped normals or open mesh)" % (back_frac * 100))
    from scipy import ndimage
    holes = ndimage.binary_fill_holes(sil["front"]) & ~sil["front"]
    m["front_hole_fraction"] = round(float(holes.mean()), 4)
    allow = MIN["max_hole_fraction"]
    man = os.path.join(views_dir, "manifest.json") if views_dir else None
    if man and os.path.exists(man):   # a sheet set: compare with the holes the reference really has
        try:
            mj = json.load(open(man))
            x0, y0, x1, y1 = mj["part_map"]["view_bboxes_px"]["front"]
            pm = np.asarray(Image.open(os.path.join(views_dir, mj["part_map"]["filename"])).convert("L").crop((x0, y0, x1, y1 - 3))) > 30
            ys_, xs_ = np.nonzero(pm)
            pm = pm[ys_.min():ys_.max() + 1, xs_.min():xs_.max() + 1]
            ref_holes = float((ndimage.binary_fill_holes(pm) & ~pm).mean())
            m["reference_hole_fraction"] = round(ref_holes, 4)
            allow = max(allow, ref_holes * 1.5 + 0.002)
        except Exception:
            pass
    if solid and holes.mean() > allow:
        fails.append("see-through holes in the front")
    if views_dir:
        from .hull import silhouette
        ious = {}
        for k, got in sil.items():
            p = os.path.join(views_dir, "v_%s.png" % k)
            if k in paint_only or not os.path.exists(p):
                continue
            mask, _ = silhouette(p)
            ref = np.asarray(Image.fromarray(mask.astype(np.uint8) * 255).resize((got.shape[1], got.shape[0]))) > 127
            lab = ndimage.label(got & ~ref)[0]
            sizes = np.bincount(lab.ravel())
            bumps = np.isin(lab, [i for i, c in enumerate(sizes) if i and c < got.sum() * 0.03])
            core = got & ~bumps
            ious[k] = round(float((ref & core).sum() / max((ref | core).sum(), 1)), 3)
            if ious[k] < MIN["silhouette_iou"]:
                fails.append("%s outline matches the reference only %.0f%%" % (k, ious[k] * 100))
        m["silhouette_iou"] = ious
    return {"pass": not fails, "fails": fails, "metrics": m}
