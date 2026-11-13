"""The asset factory: work orders in, game-ready assets out, every run measured.

Run under Blender (all stations share one process):
    blender -b --factory-startup -P tools/factory.py -- intake IMAGE NAME --category tv [--height 0.5]
    blender -b --factory-startup -P tools/factory.py -- intake_sheet SHEET_SPEC.json --source-dir DIR
    blender -b --factory-startup -P tools/factory.py -- intake_set MANIFEST.json [--category fridge] [--name N]
    blender -b --factory-startup -P tools/factory.py -- build NAME... | --pending | --all-orders
    blender -b --factory-startup -P tools/factory.py -- qa NAME... | --library
    blender -b --factory-startup -P tools/factory.py -- report

Stations: intake (classify the reference, split views, size from the category table,
write a work order) -> build (the order's production line) -> bake/export (propkit.bake)
-> gate (propkit.qa against factory/standards.json, one codified automatic correction,
then flag for a person) -> ledger (factory/ledger.jsonl) -> report (factory/REPORT.md).
Work orders live in factory/orders/<name>.json; lines read them, so a new asset needs
no code. See factory/README.md.
"""
import glob
import copy
import hashlib
import importlib
import json
import os
import tempfile
import pkgutil
import shutil
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ROOT = os.path.normpath(os.path.join(HERE, ".."))
FACT = os.path.join(ROOT, "factory")
ORDERS = os.path.join(FACT, "orders")
LEDGER = os.path.join(FACT, "ledger.jsonl")
LIB = os.path.join(ROOT, "assets", "props")
SRC = os.path.join(ROOT, "assets", "source_textures")
STANDARDS = json.load(open(os.path.join(FACT, "standards.json")))
CATS = json.load(open(os.path.join(FACT, "categories.json")))

import propkit  # noqa: E402
from propkit import bake, core, mats, qa  # noqa: E402
import props  # noqa: E402

for _m in pkgutil.iter_modules(props.__path__):
    importlib.import_module("props." + _m.name)


def load_order(name):
    p = os.path.join(ORDERS, name + ".json")
    return json.load(open(p)) if os.path.exists(p) else None


def save_order(o):
    os.makedirs(ORDERS, exist_ok=True)
    with open(os.path.join(ORDERS, o["name"] + ".json"), "w") as f:
        json.dump(o, f, indent=1)


def ledger(entry):
    entry["t"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    with open(LEDGER, "a") as f:
        f.write(json.dumps(entry) + "\n")


def file_hash(paths):
    h = hashlib.sha1()
    for p in sorted(paths):
        if os.path.exists(p):
            with open(p, "rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    h.update(chunk)
    return h.hexdigest()[:12]


# ------------------------------------------------------------------ intake

def split_views(image_path, out_dir):
    """Finds the top row of object views on a reference sheet (REFERENCE_SPEC.md) and
    saves them as v_front/right/back/left/top. Returns the list of views found."""
    import numpy as np
    from PIL import Image
    from scipy import ndimage
    im = Image.open(image_path).convert("RGB")
    a = np.asarray(im).astype(int)
    border = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])
    bg = np.median(border, axis=0)
    mask = np.abs(a - bg).sum(2) > 40
    mask = ndimage.binary_closing(mask, iterations=3)
    lab, n = ndimage.label(mask)
    boxes = ndimage.find_objects(lab)
    H, W = mask.shape
    blobs = []
    for i, sl in enumerate(boxes):
        if sl is None:
            continue
        ys, xs = sl
        h, w = ys.stop - ys.start, xs.stop - xs.start
        if h * w > H * W * 0.004 and h > H * 0.06:
            blobs.append((ys.start, ys.stop, xs.start, xs.stop))
    if not blobs:
        return []
    top = min(b[0] for b in blobs)
    row_h = max(b[1] - b[0] for b in blobs if b[0] < top + H * 0.08)
    row = sorted([b for b in blobs if b[0] < top +
                 row_h * 0.5], key=lambda b: b[2])
    names = ["front", "right", "back", "left", "top"]
    os.makedirs(out_dir, exist_ok=True)
    found = []
    for nm, (y0, y1, x0, x1) in zip(names, row):
        pad = 4
        im.crop((max(0, x0 - pad), max(0, y0 - pad), min(W, x1 + pad),
                min(H, y1 + pad))).save(os.path.join(out_dir, "v_%s.png" % nm))
        found.append(nm)
    return found


def intake(image, name, category, height=None, notes=""):
    cat = CATS[category]
    line = cat["line"]
    order = {"name": name, "category": category, "line": line, "source": os.path.basename(image),
             "class": cat.get("class"), "assumptions": [], "status": "pending", "notes": notes}
    if line == "hull":
        d = os.path.join(SRC, name)
        found = split_views(image, d)
        order["views_folder"] = name
        order["views"] = found
        order["height_m"] = height or cat["height_m"]
        if height is None:
            order["assumptions"].append(
                "height %.2f m from category '%s' (typical period size)" % (cat["height_m"], category))
        order["hull"] = dict(cat.get("hull", {}))
        missing = [v for v in ("front", "right", "top") if v not in found]
        if missing:
            order["assumptions"].append(
                "views missing: %s (fewer constraints on shape)" % ", ".join(missing))
        if "front" not in found or ("right" not in found and "left" not in found):
            order["status"] = "needs_person"
            order["assumptions"].append(
                "sheet does not follow REFERENCE_SPEC: need front and a side view")
    save_order(order)
    print("ORDER", json.dumps(order))
    return order


def automatic_build(image, output, cad_export=False, view_distance_m=None):
    """Compatibility entry point for the image-only orchestration station."""
    from propkit.pipeline import build_image
    return build_image(
        image, output, cad_export=cad_export, view_distance_m=view_distance_m,
        build_order=build, library_root=LIB,
        render_script=os.path.join(HERE, "render_turnaround.py"),
        export_model=bake.export_textured,
    )


def reference_views(order):
    """Parts orders keep the complete reference in their assembly subfolder."""
    if not order.get('views_folder'):
        return None
    folder = os.path.join(SRC, order['views_folder'])
    if order.get('layout') == 'parts':
        folder = os.path.join(folder, order.get('assembly', 'assembly'))
    return folder


def intake_sheet(spec_path, source_dir):
    """A multi-asset sheet spec: one work order per listed item. Facade items crop an
    elevation; atlas items keep the whole parts sheet and name which numbered panel
    (propkit.atlas.panels) is which face. Sources go to source_textures/<name>/."""
    import shutil
    from PIL import Image
    spec = json.load(open(spec_path))
    out = []
    for name, it in spec["items"].items():
        category = it.get("category", spec.get("category"))
        cat = CATS[category]
        line = it.get("line", cat["line"])
        d = os.path.join(SRC, name)
        os.makedirs(d, exist_ok=True)
        if line == "facade":
            Image.open(os.path.join(source_dir, it["sheet"])).convert(
                "RGB").crop(tuple(it["box"])).save(os.path.join(d, "facade.png"))
        else:  # one shared copy of the sheet; many assets come from it
            shared = os.path.join(SRC, "_sheets")
            os.makedirs(shared, exist_ok=True)
            if not os.path.exists(os.path.join(shared, it["sheet"])):
                shutil.copy(os.path.join(
                    source_dir, it["sheet"]), os.path.join(shared, it["sheet"]))
        with open(os.path.join(d, "SOURCE.md"), "w") as f:
            f.write("From Jared's painted sheet %s (%s).\n" %
                    (it["sheet"], os.path.basename(spec_path)))
        order = dict(it)
        order.update({"name": name, "category": category, "line": line, "source": it["sheet"],
                      "class": it.get("class", cat.get("class")), "views_folder": name, "status": "pending",
                      "assumptions": [], "notes": it.get("notes", "")})
        if line == "facade":
            order.setdefault("facade", dict(cat.get("facade", {})))
            order["assumptions"].append(
                "storey height 3.4 m (lower Manhattan loft/tenement)")
        else:
            order.setdefault("height_m", cat["height_m"])
            if cat.get("depth_m"):
                order.setdefault("cat_depth_m", cat["depth_m"])
            order["assumptions"].append(
                "height %.2f m from category '%s'" % (order["height_m"], category))
        save_order(order)
        out.append(name)
    print("ORDERS", out)
    return out


def intake_set(manifest, category=None, name=None):
    """A v2 sheet set (painted + depth + part map + section + manifest, REFERENCE_SPEC.md):
    files copied to source_textures/<name>/, size from the manifest's dimensions."""
    import shutil
    m = json.load(open(manifest))
    name = name or m["asset_id"]
    d = os.path.join(SRC, name)
    os.makedirs(d, exist_ok=True)
    src = os.path.dirname(os.path.abspath(manifest))
    for k in ("painted_sheet", "depth_map", "part_map", "section"):
        if k in m:
            shutil.copy(os.path.join(
                src, m[k]["filename"]), os.path.join(d, m[k]["filename"]))
    shutil.copy(manifest, os.path.join(d, "manifest.json"))
    dims = m.get("dimensions_cm", {})
    category = category or m.get("object_type")
    order = {"name": name, "category": category, "line": "sheetset", "source": os.path.basename(manifest),
             # size class from the real size
             "class": None, "views_folder": name, "status": "pending",
             "height_m": dims.get("height", 100) / 100, "depth_m": dims.get("depth", 60) / 100,
             "object_type": m.get("object_type"), "notes": m.get("display_name", ""),
             "assumptions": ["size from the manifest (%s)" % ("approximate" if dims.get("approximate") else "given")]}
    from propkit import sizing   # factory/sizing_manual.json: is this a believable size?
    for w in sizing.envelope(category, dims.get("width", 0) / 100 or None, order["depth_m"], order["height_m"]):
        order["assumptions"].append("check size: " + w)
    save_order(order)
    print("ORDER", json.dumps(order))
    return order


# ------------------------------------------------------------------ lines

def human_scale_height(order, views):
    """The height a hull order's views imply under human scale (propkit/human_scale.py): each whole-object
    contact measured in the views (front height = 1), solved and cross-checked. Returns (height_m, report)."""
    from propkit import handbook as HB, human_scale as HS
    from propkit.hull import silhouette
    fm, _ = silhouette(views["front"])
    side = views.get("right") or views.get("left")
    W = fm.shape[1] / fm.shape[0]
    D = None
    if side:
        sm, _ = silhouette(side)
        D = sm.shape[1] / sm.shape[0]
    e = HB.entry(order["handbook"])
    anchors = []
    for c in HB.contacts(e):
        if c["part"] == "whole":
            v = {"height": 1.0, "width": W, "depth": D}.get(c["measure"])
            if v:
                anchors.append(HS.anchor(c, v))
    k, rep = HS.solve(anchors)
    rep["size_from"] = "human scale (%d of %d contacts agree): %.3f x %.3f x %.3f m" % (
        rep["agreeing"], rep["of"], W * k, (D or 0) * k, k)
    if e.get("assumption"):
        rep["assumption"] = e["assumption"]
    return k, {"scale": rep}


def diagnostic_root(order):
    return os.path.join(order['run_directory'], 'diagnostics') if order.get('run_directory') else os.path.join(ROOT, 'docs', 'inference', order['name'])


def run_line(order):
    """Builds the order's geometry in the current scene. One function per line."""
    line = order["line"]
    if line == "hull_parts":     # an object from its parts, each a hull from its own views
        from propkit.hull_assembly import build as hull_parts_build
        order["measured"] = hull_parts_build(order, SRC)
        return
    if line == "hull":
        from propkit.hull import hull_prop
        d = os.path.join(SRC, order["views_folder"])
        views = {k: os.path.join(d, "v_%s.png" % k)
                 for k in order.get("views", [])}
        original_views = dict(views)
        hp = dict(order.get("hull", {}))
        # "paint": "project" blends every view by how squarely each face sees it (texturing.project, as
        # hull_parts does). The default paints each face from one view only, which streaks slanted faces
        # (glass, hoods, chamfers). Use "project" for new orders.
        blended = hp.get("paint") == "project"
        if blended:
            hp["paint"] = False
        height = order.get("height_m")
        if order.get("reconcile"):
            # make the sheet's views agree before building (propkit/reconcile.py): sizes decided, mirrored
            # views flipped, views that contradict the rest only paint
            from propkit import reconcile
            allv = dict(views)
            bp = os.path.join(d, "v_bottom.png")
            if os.path.exists(bp):
                allv["bottom"] = bp
            fixed, size, po, rrep = reconcile.run(allv, order.get(
                "sheet_dims_mm"), tmp=os.path.join(tempfile.gettempdir(), "_rec_" + order["name"]))
            views = {k: fixed[k] for k in views}
            if size:
                height = size["height_m"]
                hp["width_m"], hp["depth_m"] = size["width_m"], size["depth_m"]
            hp["paint_only"] = sorted(set(hp.get("paint_only", [])) | {
                                      k for k in po if k in views})
            order.setdefault("measured", {})["reconcile"] = rrep
            od = diagnostic_root(order)
            os.makedirs(od, exist_ok=True)
            json.dump(rrep, open(os.path.join(
                od, "reconcile.json"), "w"), indent=1)
        if not height and order.get("handbook"):
            # human scale: the views give proportions, the handbook's contacts give the size
            height, order["measured"] = human_scale_height(order, views)
        paint_only = tuple(hp.get('paint_only', ()))
        order.setdefault('measured', {})['paint_only'] = list(paint_only)
        geometry_views = {view: path for view, path in views.items()
                          if view not in paint_only}
        if hp.pop("guides", False):
            # removable construction guides (propkit/guides.py): cross-section rings make their band round
            from propkit import guides
            rb = guides.round_band(d)
            if rb:
                v_top, v_bottom, grep_ = rb
                order.setdefault("measured", {})["guides"] = grep_
                hp["voxel_hook"] = guides.round_hook(v_top, v_bottom, grep_)
        if order.get('build_scope') == 'outer_body_only':
            from propkit.silhouette import observed_silhouettes
            hp['sil_override'], openings_report = observed_silhouettes(views)
            order.setdefault('measured', {})['observed_openings'] = openings_report
        if hp.pop("relief", False):
            # carving inside the outline, read from the painting (propkit/relief.py)
            from propkit import relief
            from propkit.hull import silhouette as _sil
            fm_, _ = _sil(views["front"])
            sm_, _ = _sil(views.get("right") or views["left"])
            W_ = hp.get("width_m") or height * fm_.shape[1] / fm_.shape[0]
            D_ = hp.get("depth_m") or height * sm_.shape[1] / sm_.shape[0]
            order.setdefault("measured", {})["relief"] = rrep = {}
            if order.get('automatic_depth'):
                from propkit import surface_detail, process_planner, drawing_traces
                trace_folder = os.path.join(diagnostic_root(order), 'technical-traces')
                source_drawing = drawing_traces.infer(
                    views, trace_folder,
                    construction_masks=hp.get('sil_override'),
                    opening_report=order['measured'].get('observed_openings'),
                    view_consistency=(order['measured'].get('reconcile') or
                                      order.get('view_consistency')),
                    geometry_views=geometry_views,
                    source_views=original_views)
                order.setdefault('measured', {})['source_drawing'] = {
                    'stage': 'before_geometry',
                    'sheet': os.path.join(trace_folder, 'technical-traces.png'),
                    'traces': os.path.join(trace_folder, 'technical-traces.json'),
                    'geometry_inferences': 0,
                    'status': 'source contours and opposing-mask opening candidates; physical meaning unresolved',
                    'opening_candidates': source_drawing['build_constraints'],
                    'view_conflicts_in_use': source_drawing['view_conflicts_in_use'],
                    'reconciled_views_without_source_pixel_map':
                        source_drawing['reconciled_views_without_source_pixel_map'],
                    'paired_elevation_measurements': len(
                        source_drawing['paired_elevation_envelopes']),
                    'path_counts': {view: {'outer': record['outer_path_count'],
                                           'internal': record['internal_path_count'],
                                           'opposed_mask_openings': record['opposed_mask_opening_count']}
                                    for view, record in source_drawing['observations'].items()}}
                methods, section_bands = process_planner.plan_methods(geometry_views)
                order.setdefault('measured', {})['construction_methods'] = methods
                methods['source_drawing'] = {
                    'traces': order['measured']['source_drawing']['traces'],
                    'consumed_constraints': [constraint['id'] for constraint in
                                             source_drawing['build_constraints']],
                    'reason': 'opposing-mask openings feed the base hull, but physical through-holes remain unverified; other internal traces lack physical interpretation'}
                methods['order_overrides'] = {
                    key: hp[key] for key in ('revolve', 'sections') if key in hp}
                hp.setdefault('revolve', methods['method'].startswith('lathe_'))
                hp.setdefault('sections', methods['method'] == 'sectioned_field')
                methods['effective_operations'] = {
                    'revolve': bool(hp['revolve']), 'sections': bool(hp['sections'])}
                if section_bands is not None and hp['sections']:
                    hp['section_bands'] = section_bands
                profile_model, route = process_planner.propose(geometry_views, height)
                order.setdefault('measured', {})['process_plan'] = route
                detail_plan = surface_detail.analyse(
                    geometry_views, (W_, D_, height), rrep,
                    silhouettes=hp.get('sil_override'),
                    memory_mode=order.get('reconstruction_memory_mode', 'learning'))
                if order.get('_frozen_source_evidence') is not None:
                    detail_plan['frozen_source_evidence'] = order['_frozen_source_evidence']
                else:
                    # A run-local retry must test a new construction decision
                    # against the same source estimates. Shared learning may
                    # change between attempts, so retain the first estimates
                    # in memory for this build only.
                    detail_plan['source_evidence_sink'] = (
                        lambda evidence: order.__setitem__(
                            '_frozen_source_evidence', evidence))
                if order.get('relief_retry'):
                    detail_plan['retry_targets'] = order['relief_retry']
                detail_plan['cad_export'] = bool(order.get('cad_export'))
                detail_plan['diagnostic_folder'] = os.path.join(diagnostic_root(order), 'shading')
                use_profile = (order.get('construction_mode') == 'profile_trial'
                               and profile_model is not None)
                route['applied'] = bool(use_profile)
                if use_profile:
                    detail_plan['post_detail_envelope'] = (
                        lambda base, detailed: detailed +
                        process_planner.replace_envelope(
                            base, profile_model, (W_, D_, height)) - base)
                from propkit.correction_review import Rejected
                def build_detail_field(field):
                    try:
                        detailed = surface_detail.apply_field(field, detail_plan)
                    except Rejected as exc:
                        if order.get('build_scope') != 'outer_body_only':
                            raise
                        # Keep a diagnostic body without silently accepting a
                        # destructive relief correction or promoting the asset.
                        detail_plan['report']['topology'] = {
                            'status': 'rejected', 'reason': str(exc),
                            'review': exc.report,
                            'fallback': 'unchanged base field'}
                        order.setdefault('inference_warnings', []).append(
                            'unsafe_inferred_detail_discarded')
                        detailed = field
                    if profile_model is not None and not use_profile:
                        preflight = process_planner.preflight_field(
                            field, detailed, profile_model, (W_, D_, height))
                        route['field_preflight'] = preflight
                        if not preflight['accepted']:
                            route['choice'] = 'continuous_field'
                            route['reason'] = preflight['reason']
                    return detailed
                hp['field_hook'] = build_detail_field
                hp['mesh_hook'] = lambda obj: surface_detail.capture_high(
                    obj, detail_plan)
                # Detail is already part of the shared zero surface. Do not
                # smooth/decimate it away before feature-aware simplification.
                hp['smooth_iters'] = 0
                hp['decimate'] = 1.
            else:
                hp["mesh_hook"] = relief.hook(views, W_, D_, height, rrep)
        from propkit.hull import HULL_REPORT
        HULL_REPORT.pop("sections", None)
        obj = hull_prop(views, height, name=order["name"], **hp)
        order.setdefault('measured', {})['field'] = dict(
            HULL_REPORT.get('field', {}))
        print('RECONSTRUCTION_FIELD',
              order['name'], order['measured']['field'], flush=True)
        if HULL_REPORT.get("sections"):
            # inferred cross-sections: summary in the order, overlays (the fitted sections drawn in each view's
            # pixels, transparent) in docs/inference/<name>/ for switching on over the painting
            from propkit import sections as _sec
            srep = HULL_REPORT["sections"]
            order.setdefault("measured", {})["sections"] = {
                "curved_runs": srep["curved_runs"],
                "bands": [{k: b.get(k) for k in ("v", "best_n", "curved", "confidence", "decided_by", "gain")}
                          for b in srep["bands"]]}
            od = diagnostic_root(order)
            os.makedirs(od, exist_ok=True)
            for k, vp in views.items():
                if k in ("front", "back", "left", "right"):
                    _sec.overlay(vp, srep["bands"], os.path.join(
                        od, "sections_%s.png" % k))
            json.dump(srep, open(os.path.join(od, "sections.json"),
                      "w"), indent=1, default=str)
        manufactured = [obj]
        if blended and order.get("automatic_depth"):
            order.setdefault('measured', {})['construction'] = {
                'physical_regions': 1,
                'computational_features': len(order['measured'].get('relief', {}).get('features', [])),
                'selection': 'one continuous implicit surface; no physical joint evidence',
                'policy': 'explicit physical parts or disconnected solids may separate; curvature bands do not'}
        if blended and (order.get("automatic_depth") or order.get("budget") == "screen"):
            from propkit.simplification import screen_tolerance, decimate_to_error, refresh_normals
            tolerance = screen_tolerance(
                STANDARDS, order.get("kind", "static"), order.get('view_distance_m'))
            totals = {}
            if tolerance:
                for part in manufactured:
                    detail = order.get('measured', {}).get('relief', {})
                    from propkit import surface_detail
                    protected = surface_detail.protected_samples(
                        part, detail, geometry_tolerance=tolerance) if detail.get('probes') else None
                    if order.get('_construction_trial_autogenerated'):
                        from propkit.process_planner import dense_gate
                        gate = dense_gate(order.get('_baseline_dense_failures'),
                                          len(detail.get('unmet_before_reduction', ())))
                        order.setdefault('measured', {})['process_plan']['dense_gate'] = gate
                        if not gate['accepted']:
                            from propkit.correction_review import Rejected
                            raise Rejected(gate)
                    part['protected_surface_features'] = protected is not None
                    if part.get("preserve_profile_features"):
                        triangles = sum(len(face.vertices) -
                                        2 for face in part.data.polygons)
                        error = 0.0
                    else:
                        triangles, error = decimate_to_error(
                            part, tolerance, protected=protected)
                    refresh_normals(part, planar=bool(
                        order.get('automatic_depth')))
                    totals[part.name] = {
                        "triangles": triangles, "surface_error_m": error}
                    if part.get('simplification_correction_reviews'):
                        totals[part.name]['correction_reviews'] = json.loads(part['simplification_correction_reviews'])
                order.setdefault("measured", {})["simplification"] = {
                    "parts": totals, "triangles": sum(p["triangles"] for p in totals.values()),
                    "tolerance_m": tolerance, "stage": "independent regions before projection and baking"}
                print('SIMPLIFIED_SURFACE',
                      order['name'], order['measured']['simplification'], flush=True)
        if blended:
            from propkit import texturing
            from propkit.hull_assembly import paint_views
            tmp = os.path.join(tempfile.gettempdir(), "_hull_" + order["name"])
            for part in manufactured:
                W, D, H = part["hull_frame"]
                texturing.project(part, paint_views(views, tmp, "p"), W, D, H,
                                  others=[
                                      other for other in manufactured if other != part],
                                  name=part.name, rough=hp.get("rough", .5),
                                  camera_fit=None)
    elif line == "car":
        from props.cars_painted import painted_car
        painted_car(order["name"], order.get("body", "car_coupe"))
    elif line == "can":
        from props.goods_painted import painted_can
        painted_can(order["label"], order["radius_m"], order["height_m"])
    elif line == "facade":
        from propkit.facade import facade_prop
        info = facade_prop(os.path.join(SRC, order["views_folder"], "facade.png"), order["name"],
                           storeys=order.get("storeys"), **order.get("facade", {}))
        order["measured"] = info
    elif line == "atlas":
        from propkit.atlas import appliance
        d = os.path.join(SRC, order["views_folder"])
        order["measured"] = appliance(os.path.join(
            SRC, "_sheets", order["sheet"]), order, d, order["height_m"])
    elif line == "extrude":
        from propkit import extrude
        d = os.path.join(SRC, order["views_folder"])
        sheet = os.path.join(SRC, "_sheets", order["sheet"])
        if order["category"] == "moulding":
            order["measured"] = extrude.moulding(sheet, order["strip"], order.get("profile"), order["kind"],
                                                 order["height_m"], d, order.get(
                                                     "strip_frac"), order["name"],
                                                 order.get("section_tolerance", 1.0))
        else:
            order["measured"] = extrude.frame(sheet, order["panel"], order["height_m"], d,
                                              order.get(
                                                  "depth_m", 0.022), order["name"],
                                              order.get("opening_mode", "strict"))
    elif line == "sheetset":
        from propkit.sheetset import build_set
        d = os.path.join(SRC, order["views_folder"])
        order["measured"] = build_set(os.path.join(d, "manifest.json"), order["name"], order["height_m"],
                                      order["depth_m"], order.get("object_type"))
    elif line == "kit":
        from propkit.kit import build as kit_build
        d = os.path.join(SRC, order["views_folder"])
        order["measured"] = kit_build(os.path.join(
            SRC, "_sheets", order["sheet"]), order, d)
    elif line == "recipe":
        propkit.PROPS[order["name"]]["fn"]()
    else:
        raise ValueError("unknown line " + line)


def correct(order, result):
    """Codified corrections for known failure modes (docs/LESSONS.md). Returns True if
    the order was changed and is worth one more attempt."""
    changed = False
    fails = " ".join(result["fails"])
    if order.get('automatic_depth') and (result.get('correction_review_failure') or
                                        any(term in fails for term in (' outline', 'holes'))):
        # Dropping a view or filling all holes changes construction assumptions.
        # A failed gauge is not evidence authorizing either semantic correction.
        result.setdefault('correction_reviews', []).append({
            'problem': fails, 'action': 'drop view or fill holes', 'accepted': False,
            'decision': 'reject_and_rollback',
            'reasons': ['No independent evidence authorizes changing silhouette/opening constraints'],
            'uses_llm': False, 'physical_geometry_verified': False})
        return False
    if (order.get('automatic_depth') and not order.get('construction_mode')
            and order.get('measured', {}).get('process_plan', {}).get('choice') == 'profile_shaft_candidate'
            and ('missing shading depth:' in fails or 'triangle budget' in fails)):
        order['construction_mode'] = 'profile_trial'
        order['_construction_trial_autogenerated'] = True
        order.setdefault('corrections', []).append(
            {'action': 'compare fitted profile envelope with continuous field'})
        return True
    if order.get('automatic_depth') and 'triangle budget' in fails:
        # The implicit path intentionally preserves detected geometry. The
        # legacy decimation-ratio retry is overridden there and does no work.
        return False
    if (order.get('automatic_depth') and not order.get('relief_retry')
            and 'missing shading depth:' in fails):
        diagnostics = order.get('measured', {}).get('relief', {}).get('probe_diagnostics', {})
        failed_ids = {item.split('missing shading depth: ', 1)[1]
                      for item in result['fails'] if item.startswith('missing shading depth: ')}
        supported = [item for item in diagnostics.get('probes', ())
                     if item['status'] == 'supported_unmet' and item['id'] in failed_ids]
        if supported:
            order['relief_retry'] = supported
            order.setdefault('corrections', []).append(
                {'action': 'local supported-view retry', 'probe_ids': [p['id'] for p in supported]})
            return True
    if order["line"] == "hull":
        h = order.setdefault("hull", {})
        for v in ("back", "left", "right", "top"):
            if (v + " outline") in fails and v not in h.get("paint_only", []):
                # unreliable view: paint, don't carve
                h.setdefault("paint_only", []).append(v)
                changed = True
        if "holes" in fails and not h.get("convex"):
            h["convex"] = True
            changed = True
        if "triangle budget" in fails:
            h["decimate"] = round(h.get("decimate", 0.35) * 0.5, 3)
            changed = True
    if order["line"] == "extrude":
        if "trim section differs" in fails and order.get("profile") is not None:
            if order.get("section_tolerance", 1.0) > 0.31:
                # follow the drawing more closely
                order["section_tolerance"] = 0.3
                changed = True
        if "frame reference opening not found" in fails or "frame opening is blocked" in fails:
            if order.get("opening_mode", "strict") != "interior":
                order["opening_mode"] = "interior"
                changed = True
    if changed:
        order.setdefault("corrections", []).append(result["fails"])
    return changed


def tex_for(order):
    if order.get("tex"):          # an order may ask for a bigger atlas (many parts, keep their detail)
        return int(order["tex"])
    cls = order.get("class") or "medium"
    return STANDARDS["size_classes"].get(cls, STANDARDS["size_classes"]["medium"])["tex"]


def render_trim_preview(name, library_root=None):
    """Always make a PNG turnaround of a shipped extruded asset. No source sheets."""
    import bpy
    import subprocess
    from propkit.warehouse import asset_directory
    script = os.path.join(HERE, "preview_trim.py")
    out = str(asset_directory(library_root, name) / '_preview.png') if library_root else os.path.abspath(os.path.join(HERE, '..', '..', '.hull-maintenance', 'previews', name, '_preview.png'))
    proc = subprocess.run([bpy.app.binary_path, "-b", "--factory-startup", "--python-use-system-env", "--python-exit-code", "1",
                           "-P", script, "--", name], text=True, capture_output=True,
                          timeout=180, env=dict(os.environ, HULL_LIBRARY_ROOT=str(library_root or LIB), HULL_PREVIEW_OUTPUT=out))
    if proc.returncode:
        raise RuntimeError("preview Blender failed: " +
                           (proc.stderr or proc.stdout)[-1200:])
    if not os.path.exists(out):
        raise RuntimeError("render completed but preview PNG is missing")
    return out


def _local_retry_review(before, after, targets, before_measured, measured):
    """Accept a second build only if exported geometry improves safely."""
    from propkit.correction_review import assess, same_source_probes
    target_ids = {item['id'] for item in targets}

    def target_misses(result):
        return {item.split('missing shading depth: ', 1)[1]
                for item in result.get('fails', ())
                if item.startswith('missing shading depth: ')} & target_ids

    old, new = before.get('metrics', {}), after.get('metrics', {})
    old_outline = old.get('silhouette_iou', {})
    new_outline = new.get('silhouette_iou', {})
    delta = min((new_outline.get(view, -1) - value
                 for view, value in old_outline.items()), default=-1.)
    extra_fails = set(after.get('fails', ())) - set(before.get('fails', ()))
    retry_applied = measured.get('relief', {}).get('local_retry', {}).get('applied') is True
    source_evidence_same = same_source_probes(
        before_measured.get('relief', {}), measured.get('relief', {}))
    before_metrics = {'missing_target_details': len(target_misses(before))}
    after_metrics = {
        'missing_target_details': len(target_misses(after)),
        'new_final_failures': len(extra_fails),
        'extreme_fold_count': new.get('extreme_folds', {}).get('count'),
        'extreme_folds_per_1k': new.get('extreme_folds', {}).get('per_1k'),
        'geometric_components': new.get('geometric_components'),
        'triangle_count': new.get('tris'),
        'minimum_silhouette_delta': delta,
        'same_source_probes': int(source_evidence_same),
        'field_retry_applied': int(retry_applied)}
    limits = {'new_final_failures': (0, 0),
              'extreme_fold_count': (0, old.get('extreme_folds', {}).get('count', -1)),
              'extreme_folds_per_1k': (0, old.get('extreme_folds', {}).get('per_1k', -1)),
              'geometric_components': (1, old.get('geometric_components', 0)),
              'triangle_count': (0, old.get('tris', 0) * 1.05),
              'minimum_silhouette_delta': (-.005, 1.),
              'same_source_probes': (1, 1),
              'field_retry_applied': (1, 1)}
    return assess('supported relief missing after view fusion',
                  'accept isolated local view ownership on exported asset',
                  before_metrics, after_metrics,
                  improve=['missing_target_details'], limits=limits)


def _build_candidate(order, run, samples=16):
    t0 = time.time()
    attempt, result, stages = 0, None, {}
    previous = None
    while True:
        attempt += 1
        library_root = str(run / ("attempt-%03d" % attempt) / "library")
        order["run_directory"] = str(run / ("attempt-%03d" % attempt))
        try:
            from propkit.pathing import check_blender_export_paths
            check_blender_export_paths(library_root, order['name'])
            if order.get('_input_views_snapshot'):
                working = run / ("attempt-%03d" % attempt) / 'inputs'
                shutil.copytree(order['_input_views_snapshot'], working)
                order['views_folder'] = str(working.resolve())
            core.reset()
            mats.reset()
            ts = time.time()
            run_line(order)
            stages = {"geometry_and_paint": round(time.time() - ts, 1)}
            ts = time.time()
            # standards.json mounting: by tag
            mount_tags = ["wall"] if order.get("mount") == "wall" else []
            info = bake.finish(order["name"], library_root, tex_for(
                order), samples, tags=[order["category"]] + mount_tags,
                owned_projection=bool(order.get('automatic_depth')))
            stages["bake_and_export"] = round(time.time() - ts, 1)
            ts = time.time()
            info.update({"tags": [order["category"], "factory"], "desc": order.get("notes") or order["name"],
                         "kind": order.get("kind", "static"), "run_id": run.name})
            bake.update_manifest(os.path.join(
                library_root, "library.json"), order["name"], info)
            vd = reference_views(order)
            result = qa.check(order["name"], vd, order.get("class"),
                              tuple(order.get('measured', {}).get('paint_only',
                                    order.get("hull", {}).get("paint_only", ()))),
                              solid=order["line"] in STANDARDS["solid_lines"], mount=order.get("mount", "floor"),
                              trim_order=order, library_root=library_root)
            stages["qa"] = round(time.time() - ts, 1)
        except Exception as e:
            traceback.print_exc()
            result = {"pass": False, "fails": [
                "build error: %s" % e], "metrics": {}}
            from propkit.correction_review import Rejected
            if isinstance(e, Rejected):
                result['correction_review_failure'] = e.report
        if previous is not None:
            old_result, old_measured, old_library, old_directory, old_views = previous
            if order.get('construction_mode') == 'profile_trial':
                from propkit.process_planner import compare_exports
                review = compare_exports(old_result, result, old_measured,
                                         order.get('measured', {}))
                review['dense_gate'] = order.get('measured', {}).get(
                    'process_plan', {}).get('dense_gate')
            else:
                review = _local_retry_review(old_result, result,
                                             order.get('relief_retry', ()),
                                             old_measured,
                                             order.get('measured', {}))
            if not review['accepted']:
                result = old_result
                order['measured'] = old_measured
                order['run_directory'] = old_directory
                order['views_folder'] = old_views
                library_root = old_library
            result.setdefault('correction_reviews', []).append(review)
            break
        if result['pass'] or attempt > STANDARDS['minimum_acceptable']['max_retries']:
            break
        prior = (copy.deepcopy(result), copy.deepcopy(order.get('measured', {})),
                 library_root, order['run_directory'], order.get('views_folder'))
        if not correct(order, result):
            break
        if order.get('relief_retry'):
            previous = prior
        elif order.get('_construction_trial_autogenerated'):
            order['_baseline_dense_failures'] = len(
                prior[1].get('relief', {}).get('unmet_before_reduction', ()))
            previous = prior
    if result["pass"] and order["line"] == "extrude":
        try:
            preview = render_trim_preview(order["name"], library_root)
            result["metrics"]["preview_png"] = os.path.relpath(preview, ROOT)
        except Exception as e:
            result["pass"] = False
            result["fails"].append("preview generation failed: %s" % e)
    inferred = order.get('measured', {}).get('relief', {}).get('features', [])
    result['inference_warnings'] = [
        'surface depths are inverse-shading estimates; lighting and material ambiguity remain'] if inferred else []
    if order.get('automatic_depth'):
        from propkit import stage_review
        review_folder = diagnostic_root(order)
        result['stage_review'] = stage_review.inspect(
            result, order.get('measured', {}), os.path.join(review_folder, 'shading'))
        result['stage_review_path'] = stage_review.write(
            result['stage_review'], os.path.join(review_folder, 'stage-review.json'))
        if result['stage_review']['status'] == 'needs_review':
            result['inference_warnings'].append(
                'stage-evidence review identified unresolved reconstruction issues')
        from propkit.memory_outcomes import record
        result['build_memory']=record(result,{'asset':order['name'],'source':str(order.get('source','')),
            'region_keys':[region.get('memory_key') for view in order.get('measured',{}).get('relief',{}).get('views',{}).values()
                           for region in view.get('regional_relief',{}).get('regions',[]) if region.get('memory_key')]})
    result.update(attempts=attempt, seconds=round(time.time()-t0, 2), stage_seconds=stages,
                  artifact_library_root=library_root)
    order.pop('_frozen_source_evidence', None)
    return result


def build(order, samples=16):
    """Build isolated candidates; publish only a qualified immutable version."""
    from pathlib import Path
    import bpy
    from propkit import maintenance, warehouse
    repo = Path(ROOT).parent
    started = time.time()
    inputs = list((repo / 'long-lines/tools').rglob('*.py')) + list(Path(FACT).glob('*.json'))
    inputs += list(repo.glob('requirements*.txt'))
    views = Path(SRC) / order['views_folder'] if order.get('views_folder') else None
    if views and views.is_dir():
        inputs += [p for p in views.rglob('*') if p.is_file() and p.suffix != '.import']
    source = order.get('source')
    if source and Path(source).is_file():
        inputs.append(Path(source))
    required = warehouse.required_capabilities(order)
    required_checks = [
        {'id': check['id'], 'capability': check['capability']}
        for check in maintenance.load_plan(repo)['checks']
        if check['capability'] in required
    ]
    local_runtime = maintenance.doctor(repo, required, blender=bpy.app.binary_path)
    source_hashes = maintenance.source_identity(repo)
    file_hashes = {str(p.resolve()): warehouse.digest(p) for p in inputs}
    file_hashes.update({str((repo / name).resolve()): digest
                        for name, digest in source_hashes.items()})
    context = {
        'file_hashes': file_hashes,
        'source_hashes': source_hashes,
        'required_capabilities': required,
        'required_checks': required_checks,
        'runtime': {'pass': local_runtime['pass'],
                    'python': local_runtime['python'],
                    'packages': local_runtime['packages'],
                    'blender_path': str(Path(bpy.app.binary_path).resolve()),
                    'blender_version': bpy.app.version_string},
    }
    run = warehouse.create(os.environ.get('HULL_RUN_ROOT', repo / '.hull-runs'), order, context)
    original_views_folder = order.get('views_folder')
    try:
        if views and views.is_dir():
            snapshot = run / 'inputs' / 'original_views'
            shutil.copytree(views, snapshot)
            order['_input_views_snapshot'] = str(snapshot)
        result = _build_candidate(order, run, samples)
        # Legacy guide cleanup is allowed only in working copies. Preserve the
        # raw snapshot and the actual prepared references in the run identity.
        prepared = list((run / 'inputs').rglob('*'))
        for attempt_inputs in run.glob('attempt-*/inputs'):
            prepared.extend(attempt_inputs.rglob('*'))
        context['file_hashes'].update({str(p.resolve()): warehouse.digest(p) for p in prepared if p.is_file()})
        warehouse.atomic_json(run / 'run.json', dict(json.loads((run / 'run.json').read_text(encoding='utf-8')), context=context))
        receipt = warehouse.seal(run, order, result, result['artifact_library_root'])
        result['candidate_receipt'] = str(run / 'receipt.json')
        result['artifact_audit'] = receipt['audit']
        result['run_id'] = run.name
        result['disposition'] = receipt['state']
        if receipt['state'] == 'qualified_candidate' and os.environ.get('HULL_RELEASE_POLICY', 'auto') == 'auto':
            # A build that passed QA and its artifact audit ships to the library. Teams that want
            # every release tied to a qualified toolchain set HULL_REQUIRE_QUALIFICATION=1 (and
            # HULL_QUALIFICATION_PATH from `hull.py qualify`).
            qualification = os.environ.get('HULL_QUALIFICATION_PATH')
            strict = os.environ.get('HULL_REQUIRE_QUALIFICATION') == '1'
            if qualification or not strict:
                try:
                    warehouse.promote(run / 'receipt.json', LIB, qualification or None,
                                      allow_unqualified=not strict)
                    result['disposition'] = 'released'
                except (OSError, ValueError, RuntimeError) as error:
                    result['release_hold_reason'] = str(error)
            else:
                result['release_hold_reason'] = 'Matching toolchain qualification required'
        order['status'] = 'shipped' if result['disposition'] == 'released' else ('qualified_candidate' if receipt['audit']['pass'] else 'needs_person')
    except Exception as error:
        traceback.print_exc()
        result = {'pass': False, 'fails': ['candidate/release error: ' + str(error)], 'metrics': {},
                  'inference_warnings': [], 'run_id': run.name, 'disposition': 'quarantined',
                  'candidate_receipt': str(run / 'receipt.json')}
        warehouse.atomic_json(run / 'failure.json', result)
        order['status'] = 'needs_person'
    finally:
        order.pop('_input_views_snapshot', None)
        order.pop('_frozen_source_evidence', None)
        # This is a run-local second attempt, not a lasting instruction in
        # the source order. A future rebuild must earn the retry anew.
        order.pop('relief_retry', None)
        if order.pop('_construction_trial_autogenerated', False):
            order.pop('construction_mode', None)
        order.pop('_baseline_dense_failures', None)
        if original_views_folder is not None:
            order['views_folder'] = original_views_folder
    order['attempts'] = result.get('attempts', 0)
    result.setdefault('seconds', round(time.time() - started, 2))
    result.setdefault('attempts', 0)
    result.setdefault('stage_seconds', {})
    order['last_run'] = str(run)
    save_order(order)
    ledger(dict(op='build', name=order['name'], line=order['line'],
                auto=result.get('disposition') == 'released' and result.get('attempts') == 1,
                input_hash=warehouse.digest(run / 'input-order.json'),
                output_hash=file_hash(glob.glob(os.path.join(result.get('artifact_library_root', ''), order['name'], '*.glb'))),
                gauge_hash=hashlib.sha1(json.dumps([result['metrics'].get(k) for k in ('tris', 'size_m', 'silhouette_iou', 'geometry_signature', 'texture_signature', 'trim_section_iou', 'frame_opening_occlusion', 'trim_colour_difference')], sort_keys=True).encode()).hexdigest()[:12],
                **{k: result.get(k) for k in ('pass','fails','metrics','seconds','attempts','stage_seconds','inference_warnings','run_id','disposition','candidate_receipt')}))
    warehouse.atomic_json(run / 'result.json', result)
    print('BUILT' if order['status'] == 'shipped' else 'FLAGGED', order['name'], result['fails'])
    return result


def mount_of(name):
    mt = STANDARDS["mounting"]
    if name in mt["by_name"]:
        return mt["by_name"][name]
    tags = json.load(open(os.path.join(LIB, "library.json"))
                     ).get(name, {}).get("tags", [])
    for t, m in mt["by_tag"].items():
        if t in tags:
            return m
    return "floor"


def gate(names):
    for n in names:
        t0 = time.time()
        o = load_order(n) or {}
        vd = reference_views(o)
        line = o.get("line") or ("painted" if n.startswith(
            ("car_coupe", "can_", "tv_painted", "range_")) else "recipe")
        try:
            r = qa.check(n, vd, o.get("class"),
                         tuple(o.get('measured', {}).get('paint_only',
                               o.get("hull", {}).get("paint_only", ()))),
                         solid=line in STANDARDS["solid_lines"] and n not in STANDARDS["open_by_design"]["names"],
                         mount=mount_of(n), trim_order=o)
        except Exception as e:
            r = {"pass": False, "fails": ["qa error: %s" % e], "metrics": {}}
        ledger({"op": "qa", "name": n, "line": line, "pass": r["pass"], "seconds": round(time.time() - t0, 1),
                "fails": r["fails"], "metrics": r["metrics"]})
        print("PASS" if r["pass"] else "FAIL", n, r["fails"])


def report():
    rows = [json.loads(l)
            for l in open(LEDGER)] if os.path.exists(LEDGER) else []
    latest = {}
    # deleted assets stay in the ledger's history only
    current = set(json.load(open(os.path.join(LIB, "library.json"))))
    for r in rows:
        if r["name"] in current:
            latest[(r["op"], r["name"])] = r
    builds = [r for (op, _), r in latest.items() if op == "build"]
    reps = {}
    for r in rows:
        if r["op"] == "build" and r.get("gauge_hash"):
            reps.setdefault((r["name"], r["input_hash"]),
                            set()).add(r["gauge_hash"])
    repeated = [v for v in reps.values()]
    repro = sum(1 for v in repeated if len(v) == 1)
    qas = [r for (op, _), r in latest.items() if op == "qa"]
    assets = {}
    for r in qas + builds:  # a build result supersedes a gate-only result
        assets[r["name"]] = r
    vals = list(assets.values())
    passed = [r for r in vals if r["pass"]]
    tris = sorted(r["metrics"].get("tris", 0)
                  for r in vals if r["metrics"].get("tris"))
    fail_kinds = {}
    for r in vals:
        for f in r["fails"]:
            k = f.split(":")[0].split(" (")[0]
            k = " ".join(w for w in k.split() if not any(c.isdigit()
                         for c in w))
            fail_kinds[k] = fail_kinds.get(k, 0) + 1
    by_line = {}
    for r in vals:
        b = by_line.setdefault(r.get("line", "?"), [0, 0])
        b[0] += 1
        b[1] += r["pass"]
    lines = ["# Factory report", "", "Generated from `factory/ledger.jsonl` (latest result per asset).", "",
             "| Measure | Value |", "| --- | --- |",
             "| Assets measured | %d |" % len(vals),
             "| Pass the minimum standard | %d (%.0f%%) |" % (
                 len(passed), 100 * len(passed) / max(len(vals), 1)),
             "| Factory builds | %d |" % len(builds),
             "| Factory builds passing with no correction | %d |" % sum(
                 1 for r in builds if r.get("auto")),
             "| Factory builds needing a person | %d |" % sum(
                 1 for r in builds if not r["pass"]),
             "| Mean build time (s) | %.0f |" % (
                 sum(r.get("seconds") or 0 for r in builds) / max(len(builds), 1)),
             "| Same inputs -> same gauges | %d of %d order/input pairs |" % (
                 repro, len(repeated)),
             "| Median triangles | %d |" % (
                 tris[len(tris) // 2] if tris else 0),
             "| Max triangles | %d |" % (tris[-1] if tris else 0), "",
             "## By production line", "", "| Line | Assets | Passing |", "| --- | --- | --- |"]
    lines += ["| %s | %d | %d |" % (k, v[0], v[1])
              for k, v in sorted(by_line.items())]
    lines += ["", "## Failure kinds", "",
              "| Failure | Count |", "| --- | --- |"]
    lines += ["| %s | %d |" %
              (k, v) for k, v in sorted(fail_kinds.items(), key=lambda kv: -kv[1])]
    lines += ["", "## Failing assets", ""]
    lines += ["- **%s** (%s): %s" % (r["name"], r.get("line", "?"),
                                     "; ".join(r["fails"])) for r in vals if not r["pass"]]
    open(os.path.join(FACT, "REPORT.md"), "w").write("\n".join(lines) + "\n")
    print("\n".join(lines[:16]))


if __name__ == "__main__":
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    cmd, rest = (a[0], a[1:]) if a else ("report", [])
    if cmd == 'auto':
        distance = float(rest[rest.index('--view-distance') + 1]) if '--view-distance' in rest else None
        result = automatic_build(rest[0], rest[rest.index('--output') + 1],
                                 cad_export='--cad' in rest, view_distance_m=distance)
        sys.exit(0 if result['status'] == 'complete' else 2)
    elif cmd == "intake":
        kw = {}
        if "--height" in rest:
            kw["height"] = float(rest[rest.index("--height") + 1])
        intake(rest[0], rest[1], rest[rest.index("--category") + 1], **kw)
    elif cmd == "intake_set":
        intake_set(rest[0], rest[rest.index("--category") + 1] if "--category" in rest else None,
                   rest[rest.index("--name") + 1] if "--name" in rest else None)
    elif cmd == "intake_sheet":
        intake_sheet(rest[0], rest[rest.index("--source-dir") + 1])
    elif cmd == "build":
        if "--pending" in rest or "--all-orders" in rest:
            names = [os.path.basename(
                p)[:-5] for p in sorted(glob.glob(os.path.join(ORDERS, "*.json")))]
            if "--pending" in rest:
                names = [n for n in names if load_order(
                    n)["status"] == "pending"]
        else:
            names = rest
        for n in names:
            build(load_order(n))
        report()
    elif cmd == "preview":
        for n in rest:
            print("PREVIEW", render_trim_preview(n))
    elif cmd == "qa":
        names = sorted(json.load(open(os.path.join(LIB, "library.json")))
                       ) if "--library" in rest else rest
        gate(names)
        report()
    else:
        report()
