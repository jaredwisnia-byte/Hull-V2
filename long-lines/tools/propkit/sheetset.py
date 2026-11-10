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
from .runtime import scratch_dir

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
    soft_all = cls == CLASSES["soft"]          # cords and cables are their own geometry
    obj = ndimage.binary_opening((cls > 0) & ~soft_all, iterations=1)
    lab, n = ndimage.label(obj)
    if n:
        obj = lab == (np.argmax(np.bincount(lab.ravel())[1:]) + 1)
    ys, xs = np.nonzero(obj)
    bb = (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1)
    sl = (slice(bb[1], bb[3]), slice(bb[0], bb[2]))
    soft = soft_all[sl]
    obj, cls = obj[sl], np.where(obj, cls, 0)[sl]
    # The shell is continuous. A protruding part (handle, hinge) is taken off only where it
    # lies outside the body's outline, and the outline at each row is judged from the rows
    # around it: so a handle seen side-on goes, a hinge overlapping the edge leaves neither a
    # notch nor a ridge, and nothing cuts through the whole object.
    # Only compact parts can stick out of an outline (handles, hinges, knobs). A rim or frame
    # running along the edge (the back panel's raised border) is on the surface: removing it
    # would shave the outline (it pulled one side of the fridge in by 27 mm).
    lab_o, n_o = ndimage.label(cls == CLASSES["out"])
    removable = np.zeros_like(obj)
    for i_, sl_ in enumerate(ndimage.find_objects(lab_o), 1):
        comp_ = lab_o[sl_] == i_
        if comp_.mean() >= 0.3 and comp_.sum() < 0.05 * obj.sum():
            removable[sl_] |= comp_
    # Big separate parts (a handset on its cradle) are their own assembly: carved on their own,
    # and taken out of the body (protocol rule 3). They touch the outline's top or sides.
    assy = np.zeros_like(obj)
    for i_, sl_ in enumerate(ndimage.find_objects(lab_o), 1):
        comp_ = lab_o[sl_] == i_
        if comp_.sum() >= 0.08 * obj.sum() and comp_.mean() >= 0.3:
            assy[sl_] |= comp_
    obj_b = obj & ~assy
    body = ndimage.binary_fill_holes(obj_b & ~removable)
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
    # ...and the same judged column by column, so feet below the body don't become legs.
    Wc = body.shape[1]
    top_ = np.full(Wc, Hc); bot_ = np.full(Wc, -1)
    for cc_ in range(Wc):
        ys_ = np.nonzero(body[:, cc_])[0]
        if len(ys_):
            top_[cc_], bot_[cc_] = ys_[0], ys_[-1]
    winc = max(3, int(0.06 * Wc))
    expc = np.zeros_like(body)
    for cc_ in range(Wc):
        lo_, hi_ = max(0, cc_ - winc), min(Wc, cc_ + winc + 1)
        t_, b_ = top_[lo_:hi_].min(), bot_[lo_:hi_].max()
        if b_ >= t_:
            expc[t_:b_ + 1, cc_] = True
    # A cord or another part passing in front of the body hides body, it doesn't make a hole: cord pixels inside
    # the body's outline count as body (a cord hanging outside it is excluded by the outline).
    soft_c = soft
    # Same for a separate assembly in front of the body (the handset hiding the base's back
    # corner in the side view): inside the body's outline it hides body.
    carve = ndimage.binary_fill_holes((obj_b | soft_c | assy) & exp & expc)
    # Where two rounded doors meet, the outline pinches in; the cabinet behind them doesn't.
    # Bridge short pinches vertically (convex top and bottom corners are unaffected).
    vh = max(5, int(0.05 * Hc))
    padc = np.pad(carve, vh)
    carve = ndimage.binary_closing(padc, structure=np.ones((2 * vh + 1, 1)))[vh:-vh, vh:-vh] | carve
    paint = imgs["painted_sheet"].crop(box).crop(bb)
    # Pad the painting past the outline with the object's own colours, so rounded edges never
    # pick up the sheet background (the dark band along the top).
    pa = np.asarray(paint).copy()
    idx = ndimage.distance_transform_edt(~ndimage.binary_erosion(obj, iterations=2), return_distances=False,
                                         return_indices=True)
    pa = pa[idx[0], idx[1]]
    paint = Image.fromarray(pa)
    depth = np.asarray(imgs["depth_map"].crop(box).crop(bb).convert("L")).astype(np.float32) / 255.0
    return {"paint": paint, "depth": depth, "cls": cls, "obj": obj, "carve": carve, "removable": removable,
            "soft": soft, "soft_full": soft_all, "bb": bb, "assy": assy}


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
        if aspect < 1.4 and fill > 0.86 and area_frac < 0.01:
            return "key"                       # square and full: a key (a round knob fills ~79%)
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
    if sign > 0:   # what is carved into the body (handset, big housings) is not built a second time
        sel = sel & v["removable"]
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


def ndimage_fill(m):
    from scipy import ndimage
    return ndimage.binary_fill_holes(m)


def _skeleton_by_row(mask):
    """The cord's centre line, row by row: mean column of the cord pixels, smoothed. Rows
    where the cord runs sideways (a wide run) are skipped: only the hanging part is traced."""
    from scipy import ndimage
    rows = np.nonzero(mask.any(1))[0]
    if not len(rows):
        return {}
    width = np.median([mask[r].sum() for r in rows])
    out = {}
    for r in rows:
        xs = np.nonzero(mask[r])[0]
        if len(xs) <= 3 * width and np.ptp(xs) <= 4 * width:
            out[int(r)] = float(xs.mean())
    if len(out) > 5:
        ks = sorted(out)
        sm = ndimage.uniform_filter1d(np.array([out[k] for k in ks]), 9)
        out = dict(zip(ks, sm.tolist()))
    return out


def _cord(V, W, D, H):
    import math
    from mathutils import Vector
    from . import core, mats
    f = V.get("front")
    side = max((k for k in ("left", "right") if k in V), key=lambda k: V[k]["soft"].sum(), default=None)
    if f is None or side is None or f["soft_full"].sum() < 30 or V[side]["soft_full"].sum() < 30:
        return None
    # Full-view cord masks (a cord hangs outside the body's box), scaled by the body's box.
    fr, sr = _skeleton_by_row(f["soft_full"]), _skeleton_by_row(V[side]["soft_full"])
    fb, sbb = f["bb"], V[side]["bb"]
    Hf, Wf = fb[3] - fb[1], fb[2] - fb[0]
    Hs, Ws = sbb[3] - sbb[1], sbb[2] - sbb[0]
    fr = {r - fb[1]: c - fb[0] for r, c in fr.items()}
    sr = {r - sbb[1]: c - sbb[0] for r, c in sr.items()}
    pts = []
    for r in sorted(fr):
        z = (1 - r / Hf) * H
        rs = int(round(r / Hf * Hs))
        near = [k for k in sr if abs(k - rs) <= 3]
        if not near:
            continue
        cs = np.mean([sr[k] for k in near])
        x = (fr[r] / Wf - 0.5) * W
        y = (cs / Ws - 0.5) * D if side == "right" else (0.5 - cs / Ws) * D
        pts.append(Vector((x, y, z)))
    if len(pts) < 6:
        return None
    pts = pts[::max(1, len(pts) // 40)]
    thick = min(0.02, max(0.004, 0.6 * f["soft_full"].sum() / max(1, len(fr)) / Wf * W))
    col = np.asarray(f["paint"]).reshape(-1, 3).mean(0) / 255
    path = []                               # a coil round the centre line
    for i in range(len(pts) - 1):
        a, b = pts[i], pts[i + 1]
        ax = (b - a)
        if ax.length < 1e-6:
            continue
        e1 = ax.cross(Vector((0, 0, 1)) if abs(ax.normalized().z) < 0.9 else Vector((1, 0, 0))).normalized()
        e2 = ax.cross(e1).normalized()
        n = max(1, int(ax.length / 0.008 * 6))
        for t in range(n):
            ang = (len(path) / 6) * 2 * math.pi
            path.append(a + ax * (t / n) + (e1 * math.cos(ang) + e2 * math.sin(ang)) * thick * 0.35)
    core.tube(path, thick * 0.18, mats.plain(tuple(col), rough=0.5, name="set_cord"), sides=6, name="cord")
    return round(thick * 1000, 1)


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
    tmp = scratch_dir("sheetset_" + name)
    os.makedirs(tmp, exist_ok=True)
    sil = {}
    for k, v in V.items():
        p = os.path.join(tmp, "v_%s.png" % k)
        v["paint"].save(p)
        v["path"] = p
        sil[k] = (v["carve"], v["paint"])
    from .hull import polygon_hull
    Wb = H * V["front"]["obj"].shape[1] / V["front"]["obj"].shape[0]
    # Exact polygonal hull: flat faces and straight slopes (voxels left a staircase on slopes).
    body = polygon_hull({k: v["carve"] for k, v in V.items()}, Wb, D, H, name=name)
    W = H * V["front"]["obj"].shape[1] / V["front"]["obj"].shape[0]
    assy_views = {k: v for k, v in V.items() if v["assy"].any()}
    if len(assy_views) >= 3 and "front" in assy_views:
        asil = {}
        for k, v in V.items():
            m_ = v["assy"] if v["assy"].any() else v["obj"]
            asil[k] = (ndimage_fill(m_), v["paint"])
        # A long thin assembly (handset, bar) is lofted with rounded sections from the front and
        # top views; anything else is the exact polygonal hull of its outlines.
        from .hull import loft_from_views
        fa, sa = asil["front"][0], asil.get("right", asil.get("left"))[0]
        fl = np.ptp(np.nonzero(fa.any(0))[0]) / fa.shape[1] * W
        fh = np.ptp(np.nonzero(fa.any(1))[0]) / fa.shape[0] * H
        sd = np.ptp(np.nonzero(sa.any(0))[0]) / sa.shape[1] * D
        assy_obj = None
        if "top" in asil and fl > 2.0 * fh:   # long in front view; the top view gives width per station
            assy_obj = loft_from_views(fa, asil["top"][0], W, D, H, name=name + "_assy")
        if assy_obj is None:
            assy_obj = polygon_hull({k: a_[0] for k, a_ in asil.items()}, W, D, H, name=name + "_assy")
    else:
        assy_obj = None
    # Texture manufacturing: each assembly coloured from blended views, the others occluding it.
    from . import texturing
    shells = [o for o in (body, assy_obj) if o is not None]
    tex_report = {}
    for o in shells:
        tex_report[o.name] = texturing.project(o, {k: v["path"] for k, v in V.items()}, W, D, H,
                                               others=[x for x in shells if x is not o], name=o.name)

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
    def zband(prt):
        ys = np.nonzero(prt["mask"].any(1))[0]
        return ys.min() / prt["mask"].shape[0], (ys.max() + 1) / prt["mask"].shape[0]
    fb = [zband(p) for kk in ("front", "back") for p in found.get(kk, {}).get(+1, [])]
    def sticks_out_sideways(kk, z0, z1):
        """Cross-view check (protocol rule 4): does the front view show anything past that side
        edge at this height? If not, a side-view part is a front part seen edge-on."""
        f = V["front"]
        r0, r1 = int(z0 * f["obj"].shape[0]), max(int(z0 * f["obj"].shape[0]) + 1, int(z1 * f["obj"].shape[0]))
        best = 0
        for r in range(r0, min(r1, f["obj"].shape[0])):
            # only compact protruding parts count (a handset overhanging the base does not)
            o_, c_ = np.nonzero(f["removable"][r])[0], np.nonzero(f["carve"][r])[0]
            if len(o_) and len(c_):
                best = max(best, (o_.max() - c_.max()) if kk == "right" else (c_.min() - o_.min()))
        return best >= 2
    for kk in ("right", "left"):
        if kk in found:
            keep = []
            for p in found[kk][+1]:
                z0, z1 = zband(p)
                if any(min(z1, b1) - max(z0, b0) > 0.5 * (z1 - z0) for b0, b1 in fb):
                    continue   # the same physical part as one seen from the front or back
                if "front" in V and not sticks_out_sideways(kk, z0, z1):
                    continue
                keep.append(p)
            found[kk][+1] = keep
    ks = []
    for i, prt in enumerate(found.get("front", {}).get(+1, [])):
        mm = side_profile_mm(prt, V["front"], V["right"], D) if "right" in V else None
        if mm:
            measured[i] = mm
            if prt["relief"] > 0.02:
                ks.append(mm / prt["relief"])
    k_mm = float(np.median(ks)) if ks else None

    from mathutils import Vector as _V
    from mathutils.bvhtree import BVHTree
    _tree = BVHTree.FromPolygons([body.matrix_world @ vv.co for vv in body.data.vertices],
                                 [pp.vertices for pp in body.data.polygons])
    _dirs = {"front": _V((0, 1, 0)), "back": _V((0, -1, 0)), "right": _V((-1, 0, 0)), "left": _V((1, 0, 0))}

    def project(k, u, w):
        """Where a view pixel lands on the body, and the surface direction there."""
        x, y, z = place(k, u, w, 0.0)
        o = {"front": _V((x, -2, z)), "back": _V((x, 2, z)), "right": _V((2, y, z)), "left": _V((-2, y, z))}[k]
        loc, nor, _, _ = _tree.ray_cast(o, _dirs[k], 5)
        return loc, nor

    side_feet = []
    if "right" in V:
        rv = V["right"]
        lab_f, nf = __import__("scipy.ndimage", fromlist=["label"]).label(
            (rv["cls"] == CLASSES["out"]) & (np.arange(rv["cls"].shape[0])[:, None] > 0.9 * rv["cls"].shape[0]))
        for i_ in range(1, nf + 1):
            xs_ = np.nonzero((lab_f == i_).any(0))[0]
            side_feet.append(((xs_.min() / rv["cls"].shape[1] - 0.5) * D, ((xs_.max() + 1) / rv["cls"].shape[1] - 0.5) * D))
    if not side_feet:
        side_feet = [(-D / 2 + 0.1 * D, -D / 2 + 0.25 * D), (D / 2 - 0.25 * D, D / 2 - 0.1 * D)]
    body_min_z = min((body.matrix_world @ vv.co).z for vv in body.data.vertices)
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
                if src in ("depth map", "side view") and (mm <= lo or mm >= hi):
                    src += " (clamped: low confidence)"   # the evidence hit the believable limit
                ys_, xs_ = np.nonzero(prt["mask"])
                box_fill = prt["mask"].sum() / ((np.ptp(ys_) + 1) * (np.ptp(xs_) + 1))
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
                if prt["kind"] == "foot" and k == "front":
                    # Feet stand under the body: x from the front view, y from the side view.
                    ys_m, xs_m = np.nonzero(prt["mask"])
                    x0_, x1_ = (xs_m.min() / Wp - 0.5) * W, ((xs_m.max() + 1) / Wp - 0.5) * W
                    for y0_, y1_ in side_feet:
                        ft = core.box((x1_ - x0_, y1_ - y0_, max(body_min_z, 0.004) + 0.003),
                                      ((x0_ + x1_) / 2, (y0_ + y1_) / 2, max(body_min_z, 0.004) / 2), img_mat,
                                      bevel=0.001, name="foot")
                        core.planar_uv(ft, 0, 2, W, H)
                    report.append({"view": k, "kind": "foot", "mm": round(body_min_z * 1000, 1), "from": "front + side view"})
                    continue
                bm = bmesh.new()
                hits = [project(k, u, w) for u, w in uv] if sign >= 0 else []
                if sign >= 0 and all(hh[0] is not None for hh in hits):
                    # Raised parts sit on the real surface and stand out along its direction
                    # (keys on a sloped keypad stand up from the slope, not straight out).
                    nrm = sum((hh[1] for hh in hits), _V()).normalized()
                    a = [bm.verts.new(hh[0] - nrm * 0.003) for hh in hits]
                    b = [bm.verts.new(hh[0] + nrm * (mm_c / 1000)) for hh in hits]
                elif sign >= 0:
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
    # Cords: soft parts rebuilt as a 3D curve from two views (front x(z) matched by height to the
    # side view's y(z)), with a coil when the painting shows one.
    cord = _cord(V, W, D, H)
    if cord:
        report.append({"view": "front+side", "kind": "cord", "mm": cord, "from": "two-view curve"})
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
    # Shell continuity: slice the body by height; within the middle of the object, the width and
    # depth should not jump (a bump or groove the reference doesn't show). Catches the 27 mm
    # shaved side and the seam-height groove that a person found by eye.
    shell = []
    vz = np.array([list(v.co) for v in body.data.vertices])
    if len(vz):
        # Compare each height slice with the reference outline at that height (front view for
        # width, side view for depth), not with the median: a phone narrows on purpose, a bump or
        # groove the reference doesn't show is what we're after.
        def ref_extent(mask, span, z):
            r = min(mask.shape[0] - 1, max(0, int((1 - z / H) * mask.shape[0])))
            cols = np.nonzero(mask[r])[0]
            return (cols.max() + 1 - cols.min()) / mask.shape[1] * span if len(cols) else None
        side_k = "right" if "right" in V else ("left" if "left" in V else None)
        import bmesh as _bm
        from mathutils import Vector as _V2
        for z0 in np.linspace(0.12 * H, 0.88 * H, 40):
            # A true planar cut (a polygon mesh has no vertices in the middle of its faces).
            bmc = _bm.new()
            bmc.from_mesh(body.data)
            res_ = _bm.ops.bisect_plane(bmc, geom=bmc.verts[:] + bmc.edges[:] + bmc.faces[:],
                                        plane_co=_V2((0, 0, z0)), plane_no=_V2((0, 0, 1)))
            pts = [v.co for v in res_["geom_cut"] if isinstance(v, _bm.types.BMVert)]
            sl = np.array([[p_.x, p_.y, p_.z] for p_ in pts])
            bmc.free()
            if len(sl) <= 3:
                continue
            for axis, nm, mask, span in ((0, "width", V["front"]["carve"], W),
                                         (1, "depth", V[side_k]["carve"] if side_k else None, D)):
                if mask is None:
                    continue
                exp_ = ref_extent(mask, span, z0)
                got = sl[:, axis].max() - sl[:, axis].min()
                if exp_ is not None and abs(got - exp_) > max(0.008, 0.04 * span):
                    shell.append("%s %.0f mm off the reference at %.2f m" % (nm, (got - exp_) * 1000, z0))
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
            "size_warnings": sizing.envelope(otype, W, D, H), "shell_warnings": shell[:8],
            "texturing": tex_report}
