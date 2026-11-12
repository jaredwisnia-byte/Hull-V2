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
from . import trim_checks

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


def _load(name, library_root=None):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    from .warehouse import asset_directory
    bpy.ops.import_scene.gltf(filepath=str(asset_directory(library_root or LIB, name) / (name + '.glb')))
    return [o for o in bpy.data.objects if o.type == "MESH"]


def glb_normal_disagreement(path):
    """Share of the GLB's triangles with a stored vertex normal more than 72 degrees off the triangle's
    own facing (read from the file itself, not through an importer): stale or reversed normals render
    as dark streaks however the geometry looks."""
    import json as _json
    import struct
    b = open(path, "rb").read()
    jl = struct.unpack("<I", b[12:16])[0]
    js = _json.loads(b[20:20 + jl])
    bl = struct.unpack("<I", b[20 + jl:24 + jl])[0]
    bin_ = b[28 + jl:28 + jl + bl]

    def acc(i):
        a = js["accessors"][i]
        bv = js["bufferViews"][a["bufferView"]]
        n = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[a["type"]]
        dt = {5126: np.float32, 5125: np.uint32,
              5123: np.uint16, 5121: np.uint8}[a["componentType"]]
        arr = np.frombuffer(
            bin_, dtype=dt, count=a["count"] * n, offset=bv.get("byteOffset", 0) + a.get("byteOffset", 0))
        return arr.reshape(-1, n) if n > 1 else arr
    tot = bad = 0
    for mesh in js.get("meshes", []):
        for prim in mesh["primitives"]:
            if "NORMAL" not in prim["attributes"] or "indices" not in prim:
                continue
            P, N = acc(prim["attributes"]["POSITION"]), acc(
                prim["attributes"]["NORMAL"])
            I = acc(prim["indices"]).reshape(-1, 3)
            a, b_, c = P[I[:, 0]], P[I[:, 1]], P[I[:, 2]]
            fn = np.cross(b_ - a, c - a)
            # degenerate slivers have no facing
            ok = np.linalg.norm(fn, axis=1) > 1e-12
            fn = fn[ok] / np.linalg.norm(fn[ok], axis=1, keepdims=True)
            worst = np.minimum.reduce(
                [(N[I[ok, k]] * fn).sum(1) for k in range(3)])
            tot += int(ok.sum())
            bad += int((worst < 0.3).sum())
    return bad / max(1, tot)


def check(name, views_dir=None, category_class=None, paint_only=(), solid=False, mount="floor", trim_order=None, library_root=None):
    m, fails = {}, []
    from .warehouse import asset_directory
    library_root = library_root or LIB
    d = str(asset_directory(library_root, name))
    for suffix in (".glb", "_albedo.png", "_normal.png", "_orm.png"):
        if not os.path.exists(os.path.join(d, name + suffix)):
            fails.append("missing file " + name + suffix)
    if fails:
        return {"pass": False, "fails": fails, "metrics": m}
    try:
        objs = _load(name, library_root)
    except Exception as e:  # file integrity
        return {"pass": False, "fails": ["GLB does not load: %s" % e], "metrics": m}
    dg = bpy.context.evaluated_depsgraph_get()
    verts, polys, area, uv_area = [], [], 0.0, 0.0
    face_owners = []
    identity_path = os.path.join(d, name + '_parts.json')
    identities = json.load(open(identity_path)).get(
        'owners', []) if os.path.isfile(identity_path) else []
    for o in objs:
        me = o.evaluated_get(dg).to_mesh()
        base = len(verts)
        verts += [o.matrix_world @ v.co for v in me.vertices]
        polys += [[base + i for i in p.vertices] for p in me.polygons]
        native = me.attributes.get('_HULL_OWNER')
        for polygon in me.polygons:
            values = {round(native.data[i].value)
                      for i in polygon.vertices} if native else set()
            face_owners.append(next(iter(values)) if len(values) == 1 else -1)
        uv = me.uv_layers.active
        for p in me.polygons:
            area += p.area
            if uv:
                pts = [uv.data[li].uv for li in p.loop_indices]
                uv_area += 0.5 * abs(sum(pts[i].x * pts[(i + 1) % len(pts)].y - pts[(i + 1) % len(pts)].x * pts[i].y
                                         for i in range(len(pts))))
    tris = sum(len(p) - 2 for p in polys)
    if trim_order and trim_order.get('automatic_depth'):
        from .mesh_health import folded_edges
        m['extreme_folds'] = folded_edges(verts, polys)
        m['extreme_folds']['limit_per_1k'] = MIN['max_extreme_folds_per_1k']
        if m['extreme_folds']['per_1k'] > MIN['max_extreme_folds_per_1k']:
            fails.append('extreme local surface folds: %.1f per 1000 triangles' %
                         m['extreme_folds']['per_1k'])
    if trim_order and trim_order.get('automatic_depth'):
        from .local_features import geometry_components
        m['geometric_components'] = geometry_components(verts, polys)
        if trim_order.get('line') == 'hull' and m['geometric_components'] != 1:
            fails.append(
                'single physical surface contains disconnected geometric islands')
    library_path = os.path.join(library_root, 'library.json')
    if trim_order and trim_order.get('automatic_depth') and os.path.isfile(library_path):
        projection = json.load(open(library_path)).get(
            name, {}).get('texture_ownership', {})
        m['texture_ownership'] = projection
        if projection.get('needs_review'):
            fails.append(
                'projected surfaces have no valid texture source for their physical owner')
    construction = (trim_order or {}).get('measured', {}).get('construction')
    detail = (trim_order or {}).get('measured', {}).get('relief', {})
    library_entry = json.load(open(library_path)).get(
        name, {}) if os.path.isfile(library_path) else {}
    shift = np.asarray(library_entry.get(
        'manufacturing_translation_m', [0, 0, 0]))

    def placed_report(report):
        matrix = np.asarray(report.get('matrix_world', np.eye(4))).copy()
        matrix[:3, 3] += shift
        return dict(report, matrix_world=matrix.tolist())
    m['reconstruction_field'] = (trim_order or {}).get(
        'measured', {}).get('field', {})
    if detail.get('probes'):
        from .local_features import check_surface_features
        local_surface = check_surface_features(
            verts, polys, placed_report(detail))
        m['surface_features'] = local_surface
        fails.extend(local_surface['fails'])
    for part, part_detail in (trim_order or {}).get('measured', {}).get('surface_details', {}).items():
        from .local_features import check_surface_features
        owner = part_detail.get('physical_owner')
        if owner in identities:
            owner_id = identities.index(owner)
            owned_polys = [face for face, identifier in zip(
                polys, face_owners) if identifier == owner_id]
            if not owned_polys:
                fails.append(part + ': physical owner geometry is missing')
                continue
        else:
            owned_polys = polys
        local_surface = check_surface_features(
            verts, owned_polys, placed_report(part_detail))
        m.setdefault('part_surface_features', {})[part] = local_surface
        fails.extend(
            part + ': ' + failure for failure in local_surface['fails'])
    if construction and construction.get('spline_profile'):
        from .local_features import check_channels
        local = check_channels(verts, polys, construction)
        m['local_features'] = local
        fails.extend(local['fails'])
    # Reproducibility must include actual topology, not just size and triangle count.
    m["geometry_signature"] = trim_checks.geometry_signature(verts, polys)
    lo = Vector([min(v[i] for v in verts) for i in range(3)])
    hi = Vector([max(v[i] for v in verts) for i in range(3)])
    size = hi - lo
    albedo_path = os.path.join(d, name + "_albedo.png")
    tex = Image.open(albedo_path).size[0]
    m["texture_signature"] = trim_checks.colour_signature(albedo_path)
    cls = size_class(max(size), category_class)
    budget = STANDARDS["size_classes"][cls]["tri_budget"]
    density = tex * (uv_area / area) ** 0.5 if area > 0 and uv_area > 0 else 0
    m.update({"tris": tris, "size_m": [round(s, 3) for s in size], "class": cls, "tex": tex,
              "texel_density": round(density), "lowest_z": round(lo.z, 4)})
    if tris > budget:
        fails.append("over triangle budget: %d > %d (%s)" %
                     (tris, budget, cls))
    lo_d, hi_d = STANDARDS["size_classes"][cls].get(
        "texel_density_px_per_m", MIN["texel_density_px_per_m"])
    if not lo_d <= density <= hi_d:
        fails.append("texel density %d px/m outside %d-%d" %
                     (density, lo_d, hi_d))
    from .texturing import uv_quality
    uq = {}
    for o in objs:
        q = uv_quality(o)
        if q:
            uq = q if not uq or q["distorted_area_fraction"] > uq["distorted_area_fraction"] else uq
    m.update(uq)
    if uq and uq["distorted_area_fraction"] > MIN.get("max_uv_distorted_fraction", 1.0):
        fails.append("UV stretch: %.0f%% of the surface is distorted more than 2x" % (
            uq["distorted_area_fraction"] * 100))
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
    strict_geometry = bool(trim_order and trim_order.get("automatic_depth"))
    if strict_geometry:
        views["bottom"] = (Vector((0, 0, 1)), lambda u, v: Vector(
            (lo.x + u * size.x, lo.y + v * size.y, lo.z - 1)), size.y / max(size.x, 1e-6))
    back_hits, hits = 0, 0
    sil = {}
    for k, (direc, origin, aspect) in views.items():
        n = 144 if strict_geometry else 72
        w, h = n, max(6, min(480 if strict_geometry else 240, int(n * aspect)))
        got = np.zeros((h, w), bool)
        for j in range(h):
            for i in range(w):
                loc, nor, idx, dist = tree.ray_cast(
                    origin((i + 0.5) / w, 1 - (j + 0.5) / h), direc, 10)
                if loc is not None:
                    got[j, i] = True
                    hits += 1
                    if nor.dot(direc) > 0:
                        back_hits += 1
        sil[k] = got
    back_frac = back_hits / max(hits, 1)
    m["backfacing_fraction"] = round(back_frac, 3)
    nd = glb_normal_disagreement(os.path.join(d, name + ".glb"))
    m["normal_disagreement"] = round(nd, 4)
    if nd > 0.01:
        fails.append(
            "%.1f%% of triangles have normals that disagree with their facing (stale or reversed normals)" % (nd * 100))
    # thin leaves and cloth have no inside
    if solid and back_frac > MIN["max_backfacing_fraction"]:
        fails.append("%.0f%% of visible faces point inward (flipped normals or open mesh)" % (
            back_frac * 100))
    from scipy import ndimage
    holes = ndimage.binary_fill_holes(sil["front"]) & ~sil["front"]
    m["front_hole_fraction"] = round(float(holes.mean()), 4)
    allow = MIN["max_hole_fraction"]
    man = os.path.join(views_dir, "manifest.json") if views_dir else None
    # a sheet set: compare with the holes the reference really has
    if man and os.path.exists(man):
        try:
            mj = json.load(open(man))
            x0, y0, x1, y1 = mj["part_map"]["view_bboxes_px"]["front"]
            pm = np.asarray(Image.open(os.path.join(views_dir, mj["part_map"]["filename"])).convert(
                "L").crop((x0, y0, x1, y1 - 3))) > 30
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
        raw_ious = {}
        for k, got in sil.items():
            p = os.path.join(views_dir, "v_%s.png" % k)
            if k in paint_only or not os.path.exists(p):
                continue
            mask, _ = silhouette(p)
            ref = np.asarray(Image.fromarray(mask.astype(
                np.uint8) * 255).resize((got.shape[1], got.shape[0]))) > 127
            raw_ious[k] = round(
                float((ref & got).sum() / max((ref | got).sum(), 1)), 3)
            if strict_geometry and raw_ious[k] < MIN["silhouette_iou"]:
                fails.append("%s full geometry outline matches only %.0f%%" % (
                    k, raw_ious[k] * 100))
            lab = ndimage.label(got & ~ref)[0]
            sizes = np.bincount(lab.ravel())
            bumps = np.isin(lab, [i for i, c in enumerate(
                sizes) if i and c < got.sum() * 0.03])
            core = got & ~bumps
            ious[k] = round(float((ref & core).sum() /
                            max((ref | core).sum(), 1)), 3)
            if ious[k] < MIN["silhouette_iou"]:
                fails.append(
                    "%s outline matches the reference only %.0f%%" % (k, ious[k] * 100))
        m["silhouette_iou"] = ious
        m["silhouette_iou_raw"] = raw_ious
        m["silhouette_raster_width"] = n
        if trim_order and trim_order.get('vision_generated'):
            missing = set(('front', 'back', 'left',
                          'right', 'top')) - set(ious)
            if missing:
                fails.append(
                    'automatic reference comparison missing: ' + ', '.join(sorted(missing)))
    # The generic gate only checks v_front/v_side reference views. Trim orders
    # are produced from p_section/p_strip/p_front and need their own checks.
    if trim_order is None:
        order_path = os.path.join(ROOT, "factory", "orders", name + ".json")
        if os.path.exists(order_path):
            with open(order_path) as fh:
                trim_order = json.load(fh)
    if trim_order and trim_order.get("line") == "extrude":
        source = os.path.join(ROOT, "assets", "source_textures",
                              trim_order.get("views_folder", name))
        category = trim_order.get("category")
        if category == "moulding" and trim_order.get("profile") is not None:
            p = os.path.join(source, "p_section.png")
            if not os.path.isfile(p):
                fails.append("trim section reference is missing")
            else:
                match = trim_checks.section_match(p, verts, polys)
                if match is None:
                    fails.append(
                        "trim exported section cannot be compared to reference")
                else:
                    iou, ratio_error = match
                    m["trim_section_iou"] = iou
                    m["trim_section_ratio_error"] = ratio_error
                    if iou < MIN["trim"]["section_iou_min"] or ratio_error > MIN["trim"]["section_ratio_error_max"]:
                        fails.append("trim section differs from reference: IoU %.2f, ratio error %.2f" %
                                     (iou, ratio_error))
        elif category == "moulding":
            m["trim_section_reference"] = "default profile; no drawn section supplied"

        # Doors and window surrounds must have real negative space, not simply
        # a dark rectangle painted on an opaque slab.
        needs_opening = (name.startswith(("door_casing_", "window_casing_", "window_trim_",
                                          "closet_trim_")))
        if category == "frame" and needs_opening:
            p = os.path.join(source, "p_front.png")
            if not os.path.isfile(p):
                fails.append("frame painted reference is missing")
            else:
                opening = trim_checks.opening_from_paint(
                    p, trim_order.get("opening_mode", "strict"))
                m["reference_opening"] = list(opening) if opening else None
                if opening is None:
                    fails.append("frame reference opening not found")
                else:
                    x0, y0, x1, y1 = opening
                    fg = sil["front"]
                    H, W = fg.shape
                    left = max(0, min(W - 1, int((x0 + (x1 - x0) * .2) * W)))
                    right = max(
                        left + 1, min(W, int((x1 - (x1 - x0) * .2) * W)))
                    top = max(0, min(H - 1, int((y0 + (y1 - y0) * .2) * H)))
                    bottom = max(
                        top + 1, min(H, int((y1 - (y1 - y0) * .2) * H)))
                    occlusion = float(fg[top:bottom, left:right].mean())
                    m["frame_opening_occlusion"] = round(occlusion, 3)
                    if occlusion > MIN["trim"]["frame_opening_occlusion_max"]:
                        fails.append("frame opening is blocked by mesh: %.0f%% occupied" %
                                     (occlusion * 100))

        reference = os.path.join(source, "p_strip.png" if category == "moulding"
                                 else "p_front.png")
        if not os.path.isfile(reference):
            fails.append("trim painted reference is missing")
        else:
            difference = trim_checks.texture_difference(reference, albedo_path)
            m["trim_colour_difference"] = difference
            if difference is None or difference > MIN["trim"]["colour_difference_max"]:
                fails.append(
                    "trim baked colour differs from painted reference: %s" % difference)
    return {"pass": not fails, "fails": fails, "metrics": m}
