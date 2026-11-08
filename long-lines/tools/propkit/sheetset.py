"""Sheetset line: an object from a v2 sheet set (factory/REFERENCE_SPEC.md):
painted views + aligned depth map + aligned part map (+ section), with a manifest
giving view boxes and real dimensions.

1. Outlines come from the part map (exact, no guessing from the painting). Parts that
   stick out are left out of the carve, so a handle seen side-on doesn't become a slab
   across the whole front (the visual hull's classic artefact).
2. The body is carved and painted by the hull line.
3. Every region of the part map is a part. Its class (handle, hinge, foot, seam, vent,
   dispenser...) comes from its colour, shape and position; its geometry is the region's
   own outline, extruded out or cut in.
4. How far: measured in the side view where the part shows in profile; else the depth
   map's relief, scaled by the measured parts; always clamped to the sizing manual
   (factory/sizing_manual.json, via sizing.py), which says what is believable for that
   kind of part. The manual also says where each kind can be (feet at the floor corners,
   handles longer than a palm...): a part found somewhere it can't be is renamed.
"""
import json
import os

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
from . import sizing  # noqa: E402

CATALOG = sizing.catalogue()
CLASSES = {"body": 1, "panel": 2, "out": 3, "in": 4, "glass": 5, "soft": 6}
LEGEND = [((0, 0, 0), 0), ((255, 255, 255), 1), ((0, 255, 0), 2), ((0, 192, 0), 2), ((255, 0, 0), 3),
          ((0, 0, 255), 4), ((255, 255, 0), 5), ((255, 165, 0), 6), ((255, 128, 0), 6)]
# Evidence first: the reference decides whether a part exists, the sizing manual only how big
# it is. A region needs this much depth-map relief (0..1 units) to become geometry when the
# side view can't measure it; below that it stays painted.
EVIDENCE = 0.02
# What a large recess on the front is, by object type (the rest default to "recess").
LARGE_IN = {"fridge": "dispenser", "refrigerator": "dispenser", "building": "window"}


def load(manifest_path):
    m = json.load(open(manifest_path))
    d = os.path.dirname(manifest_path)
    return m, {k: Image.open(os.path.join(d, m[k]["filename"])).convert("RGB")
               for k in ("painted_sheet", "depth_map", "part_map") if k in m}


def classify_pixels(im):
    a = np.asarray(im).astype(np.int32)
    cols = np.array([c for c, _ in LEGEND])
    ids = np.array([i for _, i in LEGEND])
    dist = ((a[:, :, None, :] - cols[None, None]) ** 2).sum(-1)
    return ids[np.argmin(dist, -1)]


def view(m, imgs, name):
    """Crops of one view, all aligned: painted image, depth (0..1), part classes,
    object mask and carve mask, cropped to the object (parts included)."""
    from scipy import ndimage
    x0, y0, x1, y1 = m["painted_sheet"]["view_bboxes_px"][name]
    y1 -= 3                                     # the ground line is drawn in the part map
    box = (x0, y0, x1, y1)
    cls = classify_pixels(imgs["part_map"].crop(box))
    obj = ndimage.binary_opening(cls > 0, iterations=1)
    lab, n = ndimage.label(obj)
    if n:
        obj = lab == (np.argmax(np.bincount(lab.ravel())[1:]) + 1)
    ys, xs = np.nonzero(obj)
    bb = (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1)
    sl = (slice(bb[1], bb[3]), slice(bb[0], bb[2]))
    obj, cls = obj[sl], np.where(obj, cls, 0)[sl]
    # The shell is continuous. A protruding part (handle, hinge) is taken off only where it
    # lies outside the body's outline, and the outline at each row is judged from the rows
    # around it: so a handle seen side-on goes, a hinge overlapping the edge leaves neither a
    # notch nor a ridge, and nothing cuts through the whole object.
    body = ndimage.binary_fill_holes(obj & (cls != CLASSES["out"]))
    Hc = body.shape[0]
    lft = np.full(Hc, body.shape[1]); rgt = np.full(Hc, -1)
    for rr in range(Hc):
        xs_ = np.nonzero(body[rr])[0]
        if len(xs_):
            lft[rr], rgt[rr] = xs_[0], xs_[-1]
    win = max(3, int(0.06 * Hc))
    exp = np.zeros_like(body)
    for rr in range(Hc):
        lo_, hi_ = max(0, rr - win), min(Hc, rr + win + 1)
        l_, r_ = lft[lo_:hi_].min(), rgt[lo_:hi_].max()
        if r_ >= l_:
            exp[rr, l_:r_ + 1] = True
    carve = ndimage.binary_fill_holes(obj & exp)
    paint = imgs["painted_sheet"].crop(box).crop(bb)
    # Pad the painting past the outline with the object's own colours, so rounded edges never
    # pick up the sheet background (the dark band along the top).
    pa = np.asarray(paint).copy()
    idx = ndimage.distance_transform_edt(~ndimage.binary_erosion(obj, iterations=2), return_distances=False,
                                         return_indices=True)
    pa = pa[idx[0], idx[1]]
    paint = Image.fromarray(pa)
    depth = np.asarray(imgs["depth_map"].crop(box).crop(bb).convert("L")).astype(np.float32) / 255.0
    return {"paint": paint, "depth": depth, "cls": cls, "obj": obj, "carve": carve}


def _kind(sign, comp, cls_view, W_px, H_px, object_type, area_frac):
    ys, xs = np.nonzero(comp)
    h, w = ys.max() - ys.min() + 1, xs.max() - xs.min() + 1
    fill = comp.sum() / (h * w)
    aspect = max(h, w) / max(1, min(h, w))
    if sign > 0:
        if ys.max() >= H_px - 0.05 * H_px:
            return "foot"
        if fill < 0.3:
            return "trim"
        if (xs.min() <= 0.05 * W_px or xs.max() >= 0.95 * W_px) and area_frac < 0.01:
            return "hinge"
        if aspect > 2.5:
            return "handle"
        if aspect < 1.4 and fill > 0.6 and area_frac < 0.01:
            return "knob"
        return "trim"
    if area_frac < 0.0006:
        return "pit"
    if min(h, w) <= max(4, 0.02 * W_px) and aspect > 6:
        return "vent" if max(h, w) < 0.35 * W_px else "seam"
    if aspect > 4:
        return "vent"
    if area_frac > 0.015:
        return LARGE_IN.get(object_type, "recess")
    return "recess"


def parts(v, sign, object_type, view_name="front", size=None):
    """Regions of one class sign in a view: [(mask, kind, relief)]. sign +1 out, -1 in,
    0 panels that open. Assembly rules (sizing_manual.json): the kick plate is one part;
    side views don't rebuild what the front and back views already built. size = (view
    width m, height m): each part's first guess is then checked against the sizing manual's
    placement rules and renamed when it can't be what it was taken for."""
    from scipy import ndimage
    H_px, W_px = v["cls"].shape
    side = "out" if sign > 0 else "in"
    out = []
    bottom = np.zeros_like(v["obj"])
    bottom[int(0.9 * H_px):] = True
    if sign == 0:
        if view_name not in ("front", "back"):
            return []
        lab, n = ndimage.label(v["cls"] == CLASSES["panel"])
        for i in range(1, n + 1):
            comp = lab == i
            if comp.sum() > 0.02 * H_px * W_px:
                # Evidence: the door must stand out from the cabinet body (white) next to it.
                # No visible cabinet face (a fridge front is all doors) = nothing to stand proud of.
                ring = ndimage.binary_dilation(comp, iterations=8) & ~comp & (v["cls"] == CLASSES["body"])
                if ring.sum() < 0.1 * comp.sum() ** 0.5 * 4:
                    return []        # one door with no cabinet face to stand out from: doors are built alike
                rel = float(np.median(v["depth"][comp]) - np.median(v["depth"][ring]))
                if rel <= EVIDENCE:
                    return []
                out.append({"mask": comp, "kind": "panel", "relief": rel})
        return out
    sel = v["cls"] == (CLASSES["out"] if sign > 0 else CLASSES["in"])
    if sign > 0 and view_name == "front":
        base = ndimage.binary_closing((v["cls"] == CLASSES["out"]) | (v["cls"] == CLASSES["in"]), iterations=3) & bottom
        lab_b, nb = ndimage.label(base)
        if nb:
            b = lab_b == (np.argmax(np.bincount(lab_b.ravel())[1:]) + 1)
            if b.sum() > 0.01 * H_px * W_px:
                ring = ndimage.binary_dilation(b, iterations=6) & ~b & v["obj"]
                rel = float(np.median(v["depth"][b]) - (np.median(v["depth"][ring]) if ring.any() else 0))
                out.append({"mask": b, "kind": "kick_plate", "relief": rel})
                sel = sel & ~ndimage.binary_dilation(b, iterations=2)
    lab, n = ndimage.label(sel)
    target = None
    for i in range(1, n + 1):
        comp = lab == i
        ys_c = np.nonzero(comp.any(1))[0]
        if comp.sum() < 6 or ys_c.max() - ys_c.min() < 2:
            continue                       # a sliver, not a part
        ring = ndimage.binary_dilation(comp, iterations=4) & ~comp & v["obj"]
        rel = float(np.median(v["depth"][comp]) - (np.median(v["depth"][ring]) if ring.any() else 0))
        area = comp.sum() / (H_px * W_px)
        kind = _kind(sign, comp, v["cls"], W_px, H_px, object_type, area)
        if view_name != "front" and kind in ("foot", "kick_plate"):
            continue                       # one base, built from the front
        if view_name in ("right", "left"):
            xs_ = np.nonzero(comp.any(0))[0]
            edge = xs_.min() < 0.12 * W_px if view_name == "right" else xs_.max() > 0.88 * W_px
            if edge and sign > 0:
                continue                   # the front's hinges and handles seen side-on
        prt = {"mask": comp, "kind": kind, "relief": rel, "area": area}
        if size:
            ys, xs = np.nonzero(comp)
            span, Hm = size[0] * 1000, size[1] * 1000
            prt["box"] = {"x0": xs.min() / W_px * span, "x1": (xs.max() + 1) / W_px * span,
                          "z0": (1 - (ys.max() + 1) / H_px) * Hm, "z1": (1 - ys.min() / H_px) * Hm,
                          "span": span, "height": Hm}
            prt["kind"], why = sizing.place(side, kind, prt["box"], object_type, view_name)
            if why:
                prt["was"], prt["because"] = kind, why
        out.append(prt)
    if size:   # e.g. a view shows two feet: keep the biggest, rename the rest
        for kind in {p["kind"] for p in out if "box" in p}:
            cap = sizing.max_per_view(side, kind, object_type)
            same = sorted((p for p in out if p["kind"] == kind and "box" in p), key=lambda p: -p["area"])
            for p in same[cap or len(same):]:
                nk, why = sizing.place(side, sizing.fallback(side, kind, object_type) or kind,
                                       p["box"], object_type, view_name)
                p.setdefault("was", kind)
                p["because"] = p.get("because", []) + ["%s: more than %d in one view" % (kind, cap)] + why
                p["kind"] = nk
    return out


def side_profile_mm(front_part, front, side, D_m):
    """How far a front part sticks out, measured in the side view: the width of 'out'
    pixels ahead of the body over the part's height."""
    ys = np.nonzero(front_part["mask"].any(1))[0]
    H_f, H_s = front["cls"].shape[0], side["cls"].shape[0]
    r0, r1 = int(ys.min() / H_f * H_s), int((ys.max() + 1) / H_f * H_s)
    best = 0
    for r in range(r0, max(r0 + 1, r1)):
        row_obj = np.nonzero(side["obj"][r])[0]
        if not len(row_obj):
            continue
        c0 = row_obj[0]                                   # right view: the front is at the left
        c = c0
        while c < side["obj"].shape[1] and side["cls"][r, c] == CLASSES["out"]:
            c += 1
        best = max(best, c - c0)                          # the run of "sticks out" pixels
    return best / side["cls"].shape[1] * D_m * 1000 if best > 0 else None


def build_set(manifest_path, name, height_m=None, depth_m=None, object_type=None):
    import bmesh
    import bpy
    from skimage.measure import approximate_polygon, find_contours
    from . import core, mats
    from .hull import hull_prop
    m, imgs = load(manifest_path)
    dims = m.get("dimensions_cm", {})
    H = height_m or dims.get("height", 100) / 100
    D = depth_m or dims.get("depth", 60) / 100
    otype = object_type or m.get("object_type", "")
    names = [k for k in ("front", "right", "back", "left", "top") if k in m["painted_sheet"]["view_bboxes_px"]]
    V = {k: view(m, imgs, k) for k in names}
    tmp = os.path.join("/tmp", "_set_" + name)
    os.makedirs(tmp, exist_ok=True)
    sil = {}
    for k, v in V.items():
        p = os.path.join(tmp, "v_%s.png" % k)
        v["paint"].save(p)
        v["path"] = p
        sil[k] = (v["carve"], v["paint"])
    body = hull_prop({k: v["path"] for k, v in V.items()}, H, res=140, name=name, features=False,
                     sil_override=sil, depth_m=D, decimate=0.5, grime=0.0)
    W = H * V["front"]["obj"].shape[1] / V["front"]["obj"].shape[0]

    # Where each view's surface is, row by row (from the perpendicular view's body outline).
    def surface(k, frac_z):
        if k in ("front", "back"):
            s = V["right"]["carve"]
            r = min(s.shape[0] - 1, int(frac_z * s.shape[0]))
            cols = np.nonzero(s[r])[0]
            if not len(cols):
                return -D / 2 if k == "front" else D / 2
            c = cols[0] if k == "front" else cols[-1] + 1
            return (c / s.shape[1] - 0.5) * D
        f = V["front"]["carve"]
        r = min(f.shape[0] - 1, int(frac_z * f.shape[0]))
        cols = np.nonzero(f[r])[0]
        if not len(cols):
            return W / 2 if k == "right" else -W / 2
        c = cols[-1] + 1 if k == "right" else cols[0]
        return (c / f.shape[1] - 0.5) * W

    def place(k, u, w, depth_off):
        """View pixel fractions (u across, w down) + offset along the outward normal -> 3D."""
        z = (1 - w) * H
        s = surface(k, w)
        if k == "front":
            return ((u - 0.5) * W, s - depth_off, z)
        if k == "back":
            return ((0.5 - u) * W, s + depth_off, z)
        if k == "right":
            return (s + depth_off, (u - 0.5) * D, z)
        return (s - depth_off, (0.5 - u) * D, z)

    # Calibrate the depth map: millimetres per unit of relief, from parts measured side-on.
    measured = {}
    span = {"front": W, "back": W, "right": D, "left": D}
    found = {k: {+1: parts(V[k], +1, otype, k, (span[k], H)), -1: parts(V[k], -1, otype, k, (span[k], H)),
                 0: parts(V[k], 0, otype, k)}
             for k in names if k != "top"}
    ks = []
    for i, prt in enumerate(found.get("front", {}).get(+1, [])):
        mm = side_profile_mm(prt, V["front"], V["right"], D) if "right" in V else None
        if mm:
            measured[i] = mm
            if prt["relief"] > 0.02:
                ks.append(mm / prt["relief"])
    k_mm = float(np.median(ks)) if ks else None

    report, cutters = [], []
    for k, signs in found.items():
        v = V[k]
        Hp, Wp = v["cls"].shape
        img_mat = mats.image(v["path"], rough=0.45, grime=0.0, name="set_%s_%s" % (name, k))  # the painting has its wear
        for sign, plist in signs.items():
            for i, prt in enumerate(plist):
                rule = CATALOG["out" if sign >= 0 else "in"][prt["kind"]]
                lo, hi = rule["depth_mm"]
                measured_here = k == "front" and sign > 0 and i in measured
                if sign != 0 and not measured_here and sign * prt["relief"] <= EVIDENCE:
                    report.append({"view": k, "kind": prt["kind"], "mm": 0, "from": "painted only (no depth evidence)"})
                    continue
                if sign == 0:
                    mm, src = (prt["relief"] * k_mm, "depth map") if k_mm else (rule["default"], "catalogue")
                elif k == "front" and sign > 0 and i in measured:
                    mm, src = measured[i], "side view"
                elif k_mm and abs(prt["relief"]) > 0.02 and np.sign(prt["relief"]) == sign:
                    mm, src = abs(prt["relief"]) * k_mm, "depth map"
                else:
                    mm, src = rule["default"], "catalogue"
                mm_c = float(np.clip(mm, lo, hi))
                ys_, xs_ = np.nonzero(prt["mask"])
                box_fill = prt["mask"].sum() / ((ys_.ptp() + 1) * (xs_.ptp() + 1))
                if sign < 0 or (sign == 0 and box_fill > 0.8):   # closed boxes: recesses, and panels that are rectangles
                    ys_, xs_ = np.nonzero(prt["mask"])
                    u0, u1 = xs_.min() / Wp, (xs_.max() + 1) / Wp
                    w0, w1 = ys_.min() / Hp, (ys_.max() + 1) / Hp
                    if prt["kind"] == "seam":   # a seam is at least a fingernail wide
                        min_w = CATALOG["in"]["seam"]["width_min_mm"] / 1000
                        span = (W if k in ("front", "back") else D)
                        if (u1 - u0) * span < min_w and (w1 - w0) > (u1 - u0):
                            c_ = (u0 + u1) / 2
                            u0, u1 = c_ - min_w / span / 2, c_ + min_w / span / 2
                        if (w1 - w0) * H < min_w and (u1 - u0) > (w1 - w0):
                            c_ = (w0 + w1) / 2
                            w0, w1 = c_ - min_w / H / 2, c_ + min_w / H / 2
                    uv = [(u0, w0), (u1, w0), (u1, w1), (u0, w1)]
                    if sign == 0:   # doors keep their painted corner radius
                        m_ = prt["mask"][ys_.min():ys_.max() + 1, xs_.min():xs_.max() + 1]
                        q = max(2, min(m_.shape) // 4)
                        cut = np.mean([1 - c.mean() for c in (m_[:q, :q], m_[:q, -q:], m_[-q:, :q], m_[-q:, -q:])])
                        rpx = float(np.sqrt(max(cut, 0) * q * q / (1 - np.pi / 4)))
                        ru, rw = rpx / Wp, rpx / Hp
                        if ru > 0.002:
                            uv = []
                            for (cu, cw, a0) in ((u1 - ru, w1 - rw, 0), (u0 + ru, w1 - rw, 90), (u0 + ru, w0 + rw, 180), (u1 - ru, w0 + rw, 270)):
                                for t in range(5):
                                    ang = np.radians(a0 + t * 22.5)
                                    uv.append((cu + ru * np.cos(ang), cw + rw * np.sin(ang)))
                else:
                    c = max(find_contours(np.pad(prt["mask"], 1).astype(float), 0.5), key=len)
                    c = approximate_polygon(c, tolerance=0.8)[:-1]
                    if len(c) < 3:
                        continue
                    uv = [((cc - 1) / Wp, (rr - 1) / Hp) for rr, cc in c]
                bm = bmesh.new()
                if sign >= 0:
                    a = [bm.verts.new(place(k, u, w, -0.003)) for u, w in uv]
                    b = [bm.verts.new(place(k, u, w, mm_c / 1000)) for u, w in uv]
                else:
                    a = [bm.verts.new(place(k, u, w, 0.01)) for u, w in uv]
                    b = [bm.verts.new(place(k, u, w, -mm_c / 1000)) for u, w in uv]
                n = len(a)
                for j in range(n):
                    try:
                        bm.faces.new((a[j], a[(j + 1) % n], b[(j + 1) % n], b[j]))
                    except ValueError:
                        pass
                try:
                    bm.faces.new(a)
                    bm.faces.new(list(reversed(b)))
                except ValueError:
                    pass
                bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
                o = core.mesh_obj("%s_%s_%s%d" % (name, k, prt["kind"], i), bm)
                o.data.materials.append(img_mat)
                attr = o.data.color_attributes.new("label_uv", "FLOAT_COLOR", "CORNER")
                for li, loop in enumerate(o.data.loops):
                    vi = loop.vertex_index % n
                    u, w = uv[vi]
                    attr.data[li].color = (u, 1 - w, 0, 1)
                if sign < 0:
                    core.PARTS.remove(o)
                    cutters.append((o, prt["kind"], k))
                entry = {"view": k, "kind": prt["kind"], "mm": round(mm_c, 1), "from": src, "why": rule["why"]}
                if "was" in prt:
                    entry["was"], entry["because"] = prt["was"], prt["because"]
                report.append(entry)
    # Cut recesses one at a time; a cut that damages the body (changes its size) is undone.
    rejected = 0
    for cut, kind, k in cutters:
        before = body.data.copy()
        dims = tuple(body.dimensions)
        mod = body.modifiers.new("recess", "BOOLEAN")
        mod.operation = "DIFFERENCE"
        mod.solver = "EXACT"
        mod.object = cut
        mod.material_mode = "TRANSFER"
        try:
            core.apply_mods(body)
            ok = all(abs(a - b) <= 0.01 * max(b, 0.05) for a, b in zip(body.dimensions, dims)) and len(body.data.polygons) > 0
        except RuntimeError:
            ok = False
        if not ok:
            old_me = body.data
            body.data = before
            bpy.data.meshes.remove(old_me)
            rejected += 1
        else:
            bpy.data.meshes.remove(before)
        bpy.data.objects.remove(cut)
    summary = {}
    for r in report:
        key = "%s %s" % (r["view"], r["kind"])
        summary.setdefault(key, []).append(r["mm"])
    print("SHEETSET", name, json.dumps({k: [len(v), min(v), max(v)] for k, v in summary.items()}),
          "k_mm=%s" % (round(k_mm, 1) if k_mm else None))
    return {"width_m": round(W, 3), "depth_m": D, "height_m": H, "parts": len(report),
            "by_kind": {k: len(v) for k, v in summary.items()},
            "depth_scale_mm_per_unit": round(k_mm, 1) if k_mm else None, "recess_cuts_undone": rejected,
            "sources": {s: sum(1 for r in report if r["from"] == s) for s in ("side view", "depth map", "catalogue", "painted only (no depth evidence)")},
            "renamed": {"%s -> %s" % (r["was"], r["kind"]): sum(1 for q in report if q.get("was") == r["was"] and q["kind"] == r["kind"])
                        for r in report if "was" in r},
            "size_warnings": sizing.envelope(otype, W, D, H)}
