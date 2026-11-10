"""Hull assembly line: an object built from its parts, each part a soft hull from its own views.

A parts sheet gives the whole object in five views plus every part on its own (seat cushion,
back cushion, arm, leg...). Each part's own views are larger and cleaner, so each part is
built as its own hull (soft shapes, its own paint); the whole-object views say where each part
goes and how big it is:

- the whole-object front view's top outline has a flat stretch at each end: the side parts (arms),
  giving their width and height;
- the painted seams in the band above the seat split the middle into the repeated parts (cushions);
- a back part's depth comes from its own side view; it stands on the seat deck, a few cm in front of
  the back (the frame keeps a back panel there); a seat part's top is where the blade rule met the
  front-view edge, its thickness from its own front view;
- feet: shapes under the body in the front and side views; each foot's top goes 1.5 cm into the
  body above it, so it is attached by construction. Feet painted on a part's own views are trimmed
  off when the sheet has separate foot views;
- the frame is the whole-object hull kept only under and behind the parts (base, back panel).

No object names: parts are found and placed by those rules, and the order only says which folder
holds which part's views.
"""
import json
import os
import tempfile

import numpy as np
from PIL import Image
from scipy import ndimage

from . import blades, edge_guide, texturing
from .hull import HULL_REPORT, hull_prop, silhouette

FOOT_SINK = 0.015
OVERLAP = float(os.environ.get("HULLASM_OVERLAP", 0.015))       # neighbouring parts reach this far into each other: rounded hulls never leave a crevice
MAX_GAP = 0.004       # the gap check fails a build whose parts are further apart than this at a contact
SUPPORT_REACH = 0.06  # m: body this close along a direction can carry a part
SUPPORT_SHARE = 0.3   # of the part's vertices facing that way
MIN_TOUCH = 0.4       # share of a seated part's near layer (facing vertices) within MAX_GAP of the body
NEAR_LAYER = 0.01     # m: the facing surface this close to the closest approach is expected to touch
TOP_AGREE = 0.15      # a top view carves only if its proportions agree with the front/side views this closely
SAME_PAINT = 0.6      # colour overlap above which parts are found by subtraction, not colour
SNAP_SINK = 0.003     # an attached part sinks this far into the body it rests on / hangs from


def strip_feet(path, out_path):
    """Remove shapes hanging below a part's body (painted feet) and save the view."""
    im = Image.open(path).convert("RGB")
    a = np.asarray(im).copy()
    m, _ = silhouette(path)
    full = np.zeros(a.shape[:2], bool)
    big = np.abs(a.astype(int) - a[0, 0].astype(int)).sum(2) > 30
    lab, n = ndimage.label(big)
    if n:
        sizes = ndimage.sum(big, lab, range(1, n + 1))
        full = lab == (int(np.argmax(sizes)) + 1)
    rows = full.sum(1)
    # the body ends where rows stop being (nearly) full width: painted legs start there
    body_rows = np.nonzero(rows > 0.85 * rows.max())[0]
    if len(body_rows):
        a[body_rows[-1] + 1:] = 0
    Image.fromarray(a).save(out_path)
    return out_path


def drop_ground_lines(path):
    """Delete thin full-width lines (a drawn ground line) from a view, in place."""
    im = Image.open(path).convert("RGB")
    a = np.asarray(im).copy()
    ink = np.abs(a.astype(int)).sum(2) > 40
    fill = ink.mean(1)
    for y in range(a.shape[0]):
        # a ground line is a thin full-width row with (nearly) nothing just above or below it
        above = fill[max(0, y - 6):max(0, y - 2)]
        below = fill[y + 3:y + 7]
        if fill[y] > 0.8 and (not len(above) or above.max() < 0.3) and (not len(below) or below.max() < 0.3):
            a[max(0, y - 2):y + 3] = 0
    Image.fromarray(a).save(path)


def mirror_views(views, out_dir):
    """Views of the mirror-image part (a right arm from a left one)."""
    os.makedirs(out_dir, exist_ok=True)
    out = {}
    swap = {"left": "right", "right": "left", "outer": "outer_m"}
    for k, p in views.items():
        im = Image.open(p).transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        q = os.path.join(out_dir, "v_%s.png" % k)
        im.save(q)
        out[swap.get(k, k)] = q
    return out


def overlap(a, b):
    """Overlap of two [lo, hi] ranges as a share of the shorter one."""
    inter = min(a[1], b[1]) - max(a[0], b[0])
    return max(0.0, inter) / max(1e-9, min(a[1] - a[0], b[1] - b[0]))


OPPOSITE = {"front": "back", "back": "front", "left": "right", "right": "left"}


def confirmed_holes(holes, view, views):
    """Holes that really are background seen through the object. Painted areas close to the sheet's
    background colour (black plastic, a dark bezel) are flagged as holes too; a see-through hole must also
    show from the opposite side, so where an opposite view exists, a hole counts only where that view (mirrored)
    shows background or a hole as well. With no opposite view every flagged hole counts, as before."""
    opp = OPPOSITE.get(view)
    if not opp or opp not in views:
        return holes
    om, _, obox = silhouette(views[opp], with_box=True)
    see = ~om
    oh = os.path.join(os.path.dirname(views[opp]), "h_%s.png" % os.path.basename(views[opp])[2:-4])
    if os.path.exists(oh):
        h2 = np.asarray(Image.open(oh).convert("L").crop(obox)) > 127
        if h2.shape == om.shape:
            see |= h2
    see = np.asarray(Image.fromarray(see.astype(np.uint8) * 255).resize((holes.shape[1], holes.shape[0]))) > 127
    return holes & ndimage.binary_dilation(see[:, ::-1], iterations=3)


def paint_views(views, out_dir, tag):
    """Views cropped to the object (the frame texturing.project maps to), paint padded past the outline
    with the object's own colours so rounded edges never pick up the sheet background."""
    os.makedirs(out_dir, exist_ok=True)
    out = {}
    for k, p in views.items():
        m, img, box = silhouette(p, with_box=True)
        a = np.asarray(img).copy()
        paintable = ndimage.binary_erosion(m, iterations=2)
        hp = os.path.join(os.path.dirname(p), "h_%s.png" % os.path.basename(p)[2:-4])
        if os.path.exists(hp):
            # background seen through a hole (split_parts_sheet's h_ mask) is not the object's paint:
            # fill it from the object's own colours around it
            holes = np.asarray(Image.open(hp).convert("L").crop(box)) > 127
            if holes.shape == m.shape:
                holes = confirmed_holes(holes, k, views)
                paintable &= ~ndimage.binary_dilation(holes, iterations=2)
        idx = ndimage.distance_transform_edt(~paintable, return_distances=False, return_indices=True)
        a = a[idx[0], idx[1]]
        q = os.path.join(out_dir, "%s_%s.png" % (tag, k))
        Image.fromarray(a).save(q)
        out[k] = q
    return out


def orient_top(path, w, d, out_path):
    """Sheets often draw a long part's top view turned sideways (an arm's top drawn wide). If the
    view only fits the part's footprint (w across, d deep) when turned 90 degrees, turn it."""
    m, _ = silhouette(path)
    a = m.shape[0] / m.shape[1]                 # drawn depth/width
    want = d / w
    if abs(np.log(1 / a / want)) < abs(np.log(a / want)):
        Image.open(path).transpose(Image.Transpose.ROTATE_90).save(out_path)
        return out_path, True
    return path, False


def fit_to_box(obj, w, d, h, touch):
    """A rounded hull falls short of its box. On every face that touches a neighbour (or the frame),
    stretch the surface out to the box face: measure where the face really is (median of the
    surface facing that way, away from the rounded edges) and map it onto the box plane. Outer faces
    are left exactly as built. Paint was projected before, so it moves with the surface."""
    me = obj.data
    me.update()
    co = np.array([v.co[:] for v in me.vertices])
    nrm = np.array([v.normal[:] for v in me.vertices])
    lo_t = {"x": -w / 2, "y": -d / 2, "z": 0.0}
    hi_t = {"x": w / 2, "y": d / 2, "z": h}
    k_of = {"x": 0, "y": 1, "z": 2}
    moved = {}
    for ax in "xyz":
        k = k_of[ax]
        others = [k_of[a] for a in "xyz" if a != ax]
        inner = np.ones(len(co), bool)
        for o in others:
            lo, hi = np.percentile(co[:, o], 15), np.percentile(co[:, o], 85)
            inner &= (co[:, o] >= lo) & (co[:, o] <= hi)
        cur_lo, cur_hi = co[:, k].min(), co[:, k].max()
        tgt_lo, tgt_hi = cur_lo, cur_hi
        if (ax, 0) in touch:
            sel = inner & (nrm[:, k] < -0.5)
            if sel.sum() >= 5:
                cur_lo = float(np.median(co[sel, k]))
                tgt_lo = lo_t[ax]
        if (ax, 1) in touch:
            sel = inner & (nrm[:, k] > 0.5)
            if sel.sum() >= 5:
                cur_hi = float(np.median(co[sel, k]))
                tgt_hi = hi_t[ax]
        if (tgt_lo, tgt_hi) == (co[:, k].min(), co[:, k].max()) or cur_hi - cur_lo < 1e-4:
            continue
        sc = (tgt_hi - tgt_lo) / (cur_hi - cur_lo)
        co[:, k] = tgt_lo + (co[:, k] - cur_lo) * sc
        moved[ax] = round(float(sc), 3)
    for v, c in zip(me.vertices, co):
        v.co = c
    me.update()
    return moved


def check_gaps(boxes, contacts, frame, rep):
    """For each contact, sample the first part's surface facing the second (away from the rounded
    edges) and measure how far it is from the second part (0 where it is inside it). Also each
    seat/back part against the frame below/behind it."""
    import bpy
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    bpy.context.view_layer.update()        # parts were just moved: world matrices must be current

    def tree(o):
        o.data.update()
        return BVHTree.FromPolygons([o.matrix_world @ v.co for v in o.data.vertices], [p.vertices for p in o.data.polygons])

    def inside(t, p):
        h = t.find_nearest(p)
        return h[0] is not None and (h[0] - p).dot(h[1]) > 0, (h[3] if h[0] is not None else 1e9)

    ax_i = {"x": 0, "y": 1, "z": 2}
    pairs = [(boxes[i], boxes[j], ax, pl, +1) for i, j, ax, pl in contacts if "obj" in boxes[i] and "obj" in boxes[j]
             and "foot" not in (boxes[i]["kind"], boxes[j]["kind"])]
    out = []
    ft = tree(frame)
    for A, B, ax, pl, sgn in pairs:
        ta, tb = tree(A["obj"]), tree(B["obj"])
        for P, Q, tq, s_ in ((A, B, tb, +1), (B, A, ta, -1)):
            k = ax_i[ax]
            others = [a for a in "xyz" if a != ax]
            lo = [max(P[a][0], Q[a][0]) + 0.03 for a in others]
            hi = [min(P[a][1], Q[a][1]) - 0.03 for a in others]
            if any(l >= h for l, h in zip(lo, hi)):
                continue
            ds = []
            for v in P["obj"].data.vertices:
                p = P["obj"].matrix_world @ v.co
                if abs(p[k] - pl) > 0.03 or any(not (l <= p[ax_i[a]] <= h) for a, l, h in zip(others, lo, hi)):
                    continue
                if (v.normal[k] * s_) < 0.5:          # only the side facing the neighbour
                    continue
                ins, d = inside(tq, p)
                ds.append(0.0 if ins else d)
            if len(ds) >= 5:
                out.append({"a": P["kind"], "b": Q["kind"], "axis": ax, "samples": len(ds),
                            "p90_mm": round(float(np.percentile(ds, 90)) * 1000, 1)})
    for b in boxes:                                    # resting on the frame
        if b["kind"] not in ("seat", "back") or "obj" not in b:
            continue
        ds = []
        for v in b["obj"].data.vertices:
            p = b["obj"].matrix_world @ v.co
            if p[2] > b["z"][0] + 0.02 or v.normal[2] > -0.5:
                continue
            if not (b["x"][0] + 0.03 <= p[0] <= b["x"][1] - 0.03 and b["y"][0] + 0.03 <= p[1] <= b["y"][1] - 0.03):
                continue
            ins, d = inside(ft, p)
            ds.append(0.0 if ins else d)
        if len(ds) >= 5:
            out.append({"a": b["kind"], "b": "frame", "axis": "z", "samples": len(ds),
                        "p90_mm": round(float(np.percentile(ds, 90)) * 1000, 1)})
    # feet: the top of each foot must be inside (or against) whatever is above it, frame or part
    above = [ft] + [tree(b["obj"]) for b in boxes if b["kind"] != "foot" and "obj" in b]
    for b in boxes:
        if b["kind"] != "foot" or "obj" not in b:
            continue
        ds = []
        for v in b["obj"].data.vertices:
            p = b["obj"].matrix_world @ v.co
            if v.normal[2] < 0.5 or p[2] < b["z"][1] - 0.02:
                continue
            best = 1e9
            for t in above:
                ins, d = inside(t, p)
                best = min(best, 0.0 if ins else d)
            ds.append(best)
        out.append({"a": "foot", "b": "body", "axis": "z", "samples": len(ds),
                    "p90_mm": round(float(np.percentile(ds, 90)) * 1000, 1) if len(ds) >= 3 else 1e3})
    return out


def part_views(folder):
    return {f[2:-4]: os.path.join(folder, f) for f in sorted(os.listdir(folder)) if f.startswith("v_") and f.endswith(".png")}


def aspect(path):
    m, _ = silhouette(path)
    return m.shape[0] / m.shape[1]          # height / width


def build(order, src_root):
    """Builds the assembly into the scene; returns a report dict."""
    if order.get("layout") == "attached":
        return build_attached(order, src_root)
    if order.get("layout") == "parts":
        from .parts_layout import build_parts
        return build_parts(order, src_root)
    root = os.path.join(src_root, order["views_folder"])
    W, D, H = order["width_m"], order["depth_m"], order["height_m"]
    parts = order["parts"]                  # {"side": folder, "seat": folder, "back": folder, "foot": folder}
    tmp = os.path.join(tempfile.gettempdir(), "_hullasm_" + order["name"])
    os.makedirs(tmp, exist_ok=True)
    asm_views = part_views(os.path.join(root, order["assembly"]))
    for p in asm_views.values():
        drop_ground_lines(p)
    for fold in parts.values():
        for p in part_views(os.path.join(root, fold)).values():
            drop_ground_lines(p)
    rep = {"parts": [], "edge_guides": {}}
    guides = {}                          # kind -> {view: registered guide}; filled per part below
    use_guides = bool(order.get("edge_guide"))
    guide_counts = {}

    def load_guides(kind, folder, views, strip=False, mirror=False, rename=None):
        """g_<view>.png beside each painted view -> registered labels + machine mask; a poor fit is not used."""
        out = {}
        if not use_guides:
            return out
        for gv in sorted(f[2:-4] for f in os.listdir(folder) if f.startswith("g_") and f.endswith(".png")):
            target = (rename or {}).get(gv, gv)
            if target not in views:
                continue
            r = edge_guide.prepare(os.path.join(folder, "g_%s.png" % gv), views[target], os.path.join(tmp, "edges"),
                                   "%s_%s%s" % (kind, target, "_m" if mirror else ""), strip_feet=strip, mirror=mirror)
            ok = r is not None and r["fit"] >= 0.85
            rep["edge_guides"]["%s/%s%s" % (kind, target, " (mirrored)" if mirror else "")] = r["fit"] if r else None
            if ok:
                if mirror:
                    target = {"left": "right", "right": "left"}.get(target, target)
                out[target] = r
        return out

    def guide_hook(g, w_, d_, h_):
        # red lines split the parts here (structural); creases and rounding go onto each part's mesh
        return edge_guide.mesh_hook(g, w_, d_, h_, guide_counts, cuts="structural") if g else None

    def guided_sil(views, g):
        """The cyan outline (registered) replaces the painted-mask silhouette where a guide fits."""
        if not g:
            return None
        sil = {}
        for k, p_ in views.items():
            m_, img_ = silhouette(p_)
            if k in g and g[k]["object"].shape == m_.shape:
                m_ = g[k]["object"]
            sil[k] = (m_, img_)
        return sil

    guides["assembly"] = load_guides("assembly", os.path.join(root, order["assembly"]), asm_views)
    asm_sil = guided_sil(asm_views, guides["assembly"])

    # 1. the whole object as a voxel hull, with blade carving; read the layout from it
    layout = {}

    def read_layout(keep, carve, W_, D_, H_):
        nx, ny, nz = keep.shape
        tm, timg = carve["top"]
        lab, ids = blades.regions(timg, tm)
        th, tw = tm.shape
        xs, ys, zs = (np.arange(nx) + 0.5) / nx, (np.arange(ny) + 0.5) / ny, (np.arange(nz) + 0.5) / nz
        col_lab = lab[np.clip(((1 - ys) * th).astype(int), 0, th - 1)[None, :],
                      np.clip((xs * tw).astype(int), 0, tw - 1)[:, None]]
        occ_x = np.nonzero(keep.any((1, 2)))[0]
        regs = []
        for i in ids:
            cx, cy = np.nonzero(col_lab == i)
            if len(cx) < 6:
                continue
            x0, x1 = xs[cx].min(), xs[cx].max()
            y0, y1 = ys[cy].min(), ys[cy].max()
            top = zs[np.nonzero(keep[cx, cy].any(0))[0].max()] if keep[cx, cy].any() else 0
            edge = cx.min() <= occ_x.min() + 0.03 * nx or cx.max() >= occ_x.max() - 0.03 * nx
            kind = "side" if edge else "seat" if y0 < 0.25 else "back" if (x1 - x0) < 0.45 else "frame"
            regs.append({"kind": kind, "x": [x0, x1], "y": [y0, y1], "top": float(top), "region": int(i)})
        layout["regions"] = regs
        layout["keep"] = keep.copy()
        return keep

    hull_prop(asm_views, H, res=order.get("res", 140), name=order["name"] + "_probe", width_m=W, depth_m=D,
              blades=True, features=False, paint=False, voxel_hook=read_layout, sil_override=asm_sil)
    import bpy
    probe = bpy.data.objects.get(order["name"] + "_probe")
    from . import core
    if probe:
        if probe in core.PARTS:
            core.PARTS.remove(probe)
        bpy.data.objects.remove(probe)
    carves = {c["region"]: c["to_z"] for c in HULL_REPORT.get("blade_carves", [])}
    keep = layout["keep"]
    nx, ny, nz = keep.shape

    # 2. feet: shapes under the body in the whole-object front and side views
    fm, _ = silhouette(asm_views["front"])
    side_key = "right" if "right" in asm_views else "left"
    sm, _ = silhouette(asm_views[side_key])

    def under_body(mask):
        rows = mask.sum(1)
        body = np.nonzero(rows > 0.6 * rows.max())[0]
        bottom = body[-1] + 1
        below = mask[bottom:]
        if below.size == 0 or not below.any():
            return [], 0.0
        lab, n = ndimage.label(below)
        slices = ndimage.find_objects(lab)
        widths = [sl[1].stop - sl[1].start for sl in slices]
        heights = [sl[0].stop - sl[0].start for sl in slices]
        comps = [((sl[1].start) / mask.shape[1], (sl[1].stop) / mask.shape[1]) for sl, w_, h_ in zip(slices, widths, heights)
                 if w_ >= 0.4 * max(widths) and h_ >= 0.5 * max(heights)]      # scraps are not feet
        return comps, 1 - bottom / mask.shape[0]
    feet_x, foot_top_f = under_body(fm)
    feet_y, foot_top_s = under_body(sm)
    if side_key == "left":
        feet_y = [(1 - b, 1 - a) for a, b in feet_y]
    tops_ = [t for t in (foot_top_f, foot_top_s) if t > 0]
    foot_top = (sum(tops_) / len(tops_)) * H if tops_ else 0.0
    boxes = []
    if "foot" in parts and feet_x and feet_y:
        for fx in feet_x:
            for fy in feet_y:
                boxes.append({"kind": "foot", "x": [fx[0] * W - W / 2, fx[1] * W - W / 2],
                              "y": [fy[0] * D - D / 2, fy[1] * D - D / 2], "z": [0.0, foot_top + FOOT_SINK]})

    # 3. part boxes, measured from the whole-object views like an engineer measures a drawing:
    #    the front view's top outline has a flat stretch at each end (side parts: width, height)
    #    and a middle stretch whose dips separate the repeated back parts; the side view's top rows
    #    give the back parts' depth; seat parts share the back parts' widths, their top is where
    #    the blade rule met the front-view edge and their thickness comes from their own views.
    fm_, _ = silhouette(asm_views["front"])
    prof = np.array([(1 - np.argmax(col) / fm_.shape[0]) if col.any() else 0 for col in fm_.T])  # top height per column
    prof = ndimage.uniform_filter1d(prof, max(3, len(prof) // 80))
    n = len(prof)
    end_level = np.median(np.r_[prof[: n // 25], prof[-n // 25:]])
    mid_level = np.percentile(prof[n // 4: 3 * n // 4], 90)
    side_parts = []
    if "side" in parts and mid_level - end_level > 0.05:
        thr = end_level + 0.4 * (mid_level - end_level)
        left_end = int(np.argmax(prof > thr))
        right_end = n - int(np.argmax(prof[::-1] > thr))
        side_parts = [(0.0, left_end / n, False), (right_end / n, 1.0, True)]
    inner0 = side_parts[0][1] if side_parts else 0.0
    inner1 = side_parts[1][0] if side_parts else 1.0
    # repeated back parts: the painted seams between them, i.e. columns of strong vertical edges in
    # the band above the seat (outline notches between cushions are too small to survive cleanup)
    _, fimg_ = silhouette(asm_views["front"])
    g = ndimage.gaussian_filter(np.asarray(fimg_.convert("L")).astype(float), 1.0)
    seat_row = int((1 - (np.median(list(carves.values())) if carves else 0.5)) * g.shape[0])
    band = np.abs(ndimage.sobel(g, 1))[: max(4, seat_row)]
    colstr = ndimage.uniform_filter1d(band.mean(0), 3)
    a0, a1 = int(inner0 * n) + n // 30, int(inner1 * n) - n // 30
    cuts = [inner0]
    if a1 - a0 > 10:
        seg = colstr[a0:a1]
        sep = max(6, int(0.12 * n))
        order_ = np.argsort(seg)[::-1]
        picked = []
        for i in order_:
            if seg[i] < 0.5 * seg.max():
                break
            if all(abs(i - j) >= sep for j in picked):
                picked.append(i)
        cuts += sorted((a0 + i) / n for i in picked)
    cuts.append(inner1)
    gfront = guides.get("assembly", {}).get("front")
    guide_seat_bottom = None
    if gfront is not None:
        # The guide says where components separate: long vertical red/purple lines between the side
        # parts are cushion joins (they replace the painted-seam guess); a long red horizontal line
        # below the seat top is the seat cushions' bottom.
        L = gfront["labels"]
        hh, ww = L.shape
        sep = (L == edge_guide.CLASSES["cut"]) | (L == edge_guide.CLASSES["crease"])
        c0, c1 = int(inner0 * ww) + ww // 30, int(inner1 * ww) - ww // 30
        colfrac = sep[:, c0:c1].sum(0) / hh
        xs_ = np.nonzero(colfrac >= 0.12)[0]
        gcuts, grp = [], []
        for x_ in xs_:
            if grp and x_ - grp[-1] > 3:
                gcuts.append(np.mean(grp))
                grp = []
            grp.append(x_)
        if grp:
            gcuts.append(np.mean(grp))
        if gcuts:
            cuts = [inner0] + [(c0 + x_) / ww for x_ in gcuts] + [inner1]
            rep["cushion_joins_from"] = "edge guide"
        red = L == edge_guide.CLASSES["cut"]
        rowfrac = red[:, c0:c1].sum(1) / max(1, c1 - c0)
        seat_row_g = int((1 - (np.median(list(carves.values())) if carves else 0.5)) * hh)
        cand = [y_ for y_ in range(seat_row_g, hh) if rowfrac[y_] >= 0.4]
        if cand:
            guide_seat_bottom = (1 - cand[0] / hh) * H
            rep["seat_bottom_from"] = "edge guide"
    # a slice much narrower than the others is an edge, not a seam: merge it into its neighbour
    while len(cuts) > 3:
        widths = np.diff(cuts)
        k = int(np.argmin(widths))
        if widths[k] >= 0.5 * np.median(widths):
            break
        cuts.pop(k + 1 if k + 1 < len(cuts) - 1 else k)
    sm_, _ = silhouette(asm_views[side_key])
    top_rows = sm_[: max(2, int(0.12 * sm_.shape[0]))]
    cols_ = np.nonzero(top_rows.any(0))[0]
    if side_key == "right":            # right view: image left = front
        by0, by1 = cols_.min() / sm_.shape[1], (cols_.max() + 1) / sm_.shape[1]
    else:
        by0, by1 = 1 - (cols_.max() + 1) / sm_.shape[1], 1 - cols_.min() / sm_.shape[1]
    seat_top = np.median(list(carves.values())) * H if carves else None
    for x0f, x1f, mir in side_parts:
        cols = slice(int(x0f * n), max(int(x0f * n) + 1, int(x1f * n)))
        boxes.append({"kind": "side", "x": [x0f * W - W / 2, x1f * W - W / 2], "y": [-D / 2, D / 2],
                      "z": [foot_top if "foot" in parts else 0.0, float(prof[cols].max()) * H], "mirror": mir})
    for c0, c1 in zip(cuts[:-1], cuts[1:]):
        x0, x1 = c0 * W - W / 2, c1 * W - W / 2
        cols = slice(int(c0 * n), max(int(c0 * n) + 1, int(c1 * n)))
        if "back" in parts:
            bv = part_views(os.path.join(root, parts["back"]))
            tall = aspect(bv["front"]) * (x1 - x0)
            top = float(prof[cols].max()) * H
            sv_ = bv.get("right") or bv.get("left")
            thick_b = (1 / aspect(sv_)) * tall if sv_ else (by1 - by0) * D     # its own side view: depth/height
            # stands in front of a back panel (the frame keeps it) and down on the seat deck
            yb1 = by1 * D - D / 2 - max(0.03, 0.05 * D)
            z0 = top - tall
            if "seat" in parts and seat_top is not None:
                sthick = aspect(part_views(os.path.join(root, parts["seat"]))["front"]) * (x1 - x0)
                z0 = min(z0, seat_top - sthick)
            boxes.append({"kind": "back", "x": [x0, x1], "y": [yb1 - thick_b, yb1], "z": [z0, top]})
            back_front = yb1 - thick_b
        if "seat" in parts and seat_top is not None:
            sv = part_views(os.path.join(root, parts["seat"]))
            thick = aspect(sv["front"]) * (x1 - x0)
            if guide_seat_bottom is not None and seat_top - guide_seat_bottom > 0.03:
                thick = seat_top - guide_seat_bottom
            yf = back_front if "back" in parts else by0 * D - D / 2
            boxes.append({"kind": "seat", "x": [x0, x1], "y": [-D / 2, yf], "z": [seat_top - thick, seat_top]})
    print("HULLASM boxes", [(b["kind"], [[round(v, 2) for v in b[a]] for a in "xyz"]) for b in boxes], "foot_top", round(foot_top, 3))
    # 3b. contacts: where two part boxes meet (or a part rests on / stands in front of the frame), both
    #     reach OVERLAP into each other. Each part is a rounded hull inside its box, so boxes that only
    #     touch leave crevices between the rounded surfaces (the sofa's arm/cushion gaps).
    contacts = []
    ax_i = {"x": 0, "y": 1, "z": 2}
    for i, A in enumerate(boxes):
        for j, B in enumerate(boxes):
            if j <= i:
                continue
            for ax in "xyz":
                others = [a for a in "xyz" if a != ax]
                ov = all(min(A[a][1], B[a][1]) - max(A[a][0], B[a][0]) > 0.02 for a in others)
                if not ov:
                    continue
                if abs(A[ax][1] - B[ax][0]) < 0.03:
                    contacts.append((i, j, ax, (A[ax][1] + B[ax][0]) / 2))
                elif abs(B[ax][1] - A[ax][0]) < 0.03:
                    contacts.append((j, i, ax, (B[ax][1] + A[ax][0]) / 2))
    for b in boxes:
        b["grown"] = {a: list(b[a]) for a in "xyz"}
    for b in boxes:
        b["touch"] = set()
    for lo_i, hi_i, ax, plane in contacts:   # lo box is below/left/in front of hi box along ax
        if "foot" in (boxes[lo_i]["kind"], boxes[hi_i]["kind"]):
            continue                          # feet already sink FOOT_SINK into the body
        boxes[lo_i]["grown"][ax][1] = plane + OVERLAP
        boxes[hi_i]["grown"][ax][0] = plane - OVERLAP
        boxes[lo_i]["touch"].add((ax, 1))
        boxes[hi_i]["touch"].add((ax, 0))
    for b in boxes:                            # parts on the frame: into the seat deck / back panel
        if b["kind"] in ("seat", "back"):
            b["grown"]["z"][0] -= OVERLAP
            b["touch"].add(("z", 0))
        if b["kind"] == "back":
            b["grown"]["y"][1] += OVERLAP
            b["touch"].add(("y", 1))
    rep["contacts"] = [{"a": boxes[i]["kind"], "b": boxes[j]["kind"], "axis": ax, "at_m": round(pl, 3)}
                       for i, j, ax, pl in contacts]

    # 4. the frame: whole-object hull minus the parts' spaces
    def minus_parts(keep_, carve, W_, D_, H_):
        k = keep_.copy()
        xs = (np.arange(nx) + 0.5) / nx * W - W / 2
        ys = (np.arange(ny) + 0.5) / ny * D - D / 2
        zs = (np.arange(nz) + 0.5) / nz * H
        for b in boxes:
            if b["kind"] == "foot":
                continue
            # shrunk by OVERLAP: the frame continues a little under each part instead of stopping short
            mx = (xs >= b["x"][0] + OVERLAP) & (xs <= b["x"][1] - OVERLAP)
            my = (ys >= b["y"][0] + OVERLAP) & (ys <= b["y"][1] - OVERLAP)
            mz = (zs >= b["z"][0] + OVERLAP) & (zs <= b["z"][1] - OVERLAP)
            k[np.ix_(mx, my, mz)] = False
        k[:, :, zs < foot_top] = False           # feet are their own parts
        # The frame is what lies under the parts and behind them; strips between part spaces that
        # no part claims (between an arm and the cushions) would show as lumps.
        under = [b["z"][0] for b in boxes if b["kind"] in ("seat", "back")]
        behind = [b["y"][1] for b in boxes if b["kind"] == "back"]
        if under:
            zcut = min(under) + OVERLAP
            yb = max(behind) if behind else D / 2
            kill = np.broadcast_to((zs[None, None, :] >= zcut) & (ys[None, :, None] < yb - OVERLAP), k.shape).copy()
            # side parts cover their own column; the frame stays (under the overlap) next to them
            for b in boxes:
                if b["kind"] == "side":
                    mx = (xs >= b["x"][0] + OVERLAP) & (xs <= b["x"][1] - OVERLAP)
                    kill[mx] = False
            k &= ~kill
        return k
    # 4b. the frame's shape first: parts resting on it are fitted to its real surface
    frame = hull_prop(asm_views, H, res=order.get("res", 140), name=order["name"] + "_frame", width_m=W, depth_m=D,
                      blades=True, features=False, rough=order.get("rough", 0.6), voxel_hook=minus_parts, paint=False,
                      sil_override=asm_sil,
                      mesh_hook=guide_hook(guides.get("assembly"), W, D, H))
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    frame.data.update()
    ftree = BVHTree.FromPolygons([frame.matrix_world @ v.co for v in frame.data.vertices], [p_.vertices for p_ in frame.data.polygons])

    def frame_level(b, ax, side):
        """Where the frame's surface really is under (z) / behind (y) a part's footprint."""
        hits = []
        for fx in np.linspace(0.2, 0.8, 5):
            for fy in np.linspace(0.2, 0.8, 5):
                x = b["x"][0] + fx * (b["x"][1] - b["x"][0])
                if ax == "z":
                    y = b["y"][0] + fy * (b["y"][1] - b["y"][0])
                    h_ = ftree.ray_cast(Vector((x, y, b["z"][1])), Vector((0, 0, -1)), 5.0)
                    if h_[0] is not None:
                        hits.append(h_[0].z)
                else:
                    z = b["z"][0] + fy * (b["z"][1] - b["z"][0])
                    h_ = ftree.ray_cast(Vector((x, b["y"][0], z)), Vector((0, 1, 0)), 5.0)
                    if h_[0] is not None:
                        hits.append(h_[0].y)
        return float(np.median(hits)) if len(hits) >= 5 else None

    # 5. every part as its own hull, sized to its box and moved into place
    placed = []
    for n, b in enumerate(boxes):
        fold = os.path.join(root, parts[b["kind"]])
        views = part_views(fold)
        rename = {"outer": "left", "side": "right"} if b["kind"] == "side" else {"side": "right"}
        w_, d_ = b["x"][1] - b["x"][0], b["y"][1] - b["y"][0]
        turned = False
        if "top" in views:
            views["top"], turned = orient_top(views["top"], w_, d_, os.path.join(tmp, "top_%d.png" % n))
            gt = os.path.join(fold, "g_top.png")
            if turned and os.path.exists(gt):        # the guide turns with its view
                tfold = os.path.join(tmp, "guide_%d" % n)
                os.makedirs(tfold, exist_ok=True)
                for f in os.listdir(fold):
                    if f.startswith("g_") and f.endswith(".png"):
                        im_ = Image.open(os.path.join(fold, f))
                        (im_.transpose(Image.Transpose.ROTATE_90) if f == "g_top.png" else im_).save(os.path.join(tfold, f))
                fold_guides = tfold
            else:
                fold_guides = fold
        else:
            fold_guides = fold
        rep.setdefault("turned_top_views", []).append(b["kind"]) if turned else None
        if b["kind"] == "side":
            views = {k: strip_feet(p, os.path.join(tmp, "side_%s.png" % k)) if "foot" in parts else p
                     for k, p in views.items()}
            views = {("left" if k == "outer" else k): p for k, p in views.items() if k != "bottom"}
            views.setdefault("right", views.get("left"))
            g = load_guides(b["kind"], fold_guides, views, strip="foot" in parts, mirror=b["mirror"], rename=rename)
            if b["mirror"]:
                views = mirror_views(views, os.path.join(tmp, "mirror_%d" % n))
                views.pop("outer_m", None)
        else:
            g = load_guides(b["kind"], fold_guides, views, rename=rename)
        views = {k: p for k, p in views.items() if k in ("front", "back", "left", "right", "top")}
        G = b["grown"]
        if b["kind"] in ("seat", "back"):                 # rest on the frame's real deck
            zf = frame_level(b, "z", 0)
            if zf is not None:
                G["z"][0] = zf - OVERLAP
        if b["kind"] == "back":                           # stand against the frame's real back panel
            yf = frame_level(b, "y", 1)
            if yf is not None:
                G["y"][1] = yf + OVERLAP
        w, d, h = G["x"][1] - G["x"][0], G["y"][1] - G["y"][0], G["z"][1] - G["z"][0]
        if min(w, d, h) <= 0.01:
            continue
        obj = hull_prop(views, h, res=order.get("part_res", 90), name="%s_%s_%d" % (order["name"], b["kind"], n),
                        width_m=w, depth_m=d, features=False, rough=order.get("rough", 0.6), paint=False,
                        sil_override=guided_sil(views, g), mesh_hook=guide_hook(g, w, d, h))
        # blended projection (facing^4 x visibility): no stretched streaks where a face is seen at a slant
        texturing.project(obj, paint_views(views, tmp, "p%d" % n), w, d, h, others=[], name=obj.name,
                          rough=order.get("rough", 0.6))
        # HULLASM_NOFIT=1 only to prove the gap check still catches unfitted parts
        b["fit"] = {} if os.environ.get("HULLASM_NOFIT") else fit_to_box(obj, w, d, h, b["touch"])
        print("HULLASM part", b["kind"], {a: [round(v, 3) for v in G[a]] for a in "xyz"}, "fit", b["fit"])
        obj.location = ((G["x"][0] + G["x"][1]) / 2, (G["y"][0] + G["y"][1]) / 2, G["z"][0])
        placed.append(obj)
        b["obj"] = obj
        rep["parts"].append({"kind": b["kind"], "box_m": [[round(v, 3) for v in b[a]] for a in ("x", "y", "z")]})
    # 6. the frame painted last, with the placed parts occluding it
    texturing.project(frame, paint_views(asm_views, tmp, "frame"), W, D, H, others=placed, name=frame.name,
                      rough=order.get("rough", 0.6))
    rep["guide_edits"] = guide_counts
    # 7. gap check: at every contact, how far apart the two built surfaces really are
    rep["gaps_mm"] = check_gaps(boxes, contacts, frame, rep)
    worst = max([g["p90_mm"] for g in rep["gaps_mm"]] or [0])
    if worst > MAX_GAP * 1000:
        bad = [g for g in rep["gaps_mm"] if g["p90_mm"] > MAX_GAP * 1000]
        raise RuntimeError("gaps between parts: " + "; ".join("%s-%s %.1f mm" % (g["a"], g["b"], g["p90_mm"]) for g in bad))

    return rep


# --------------------------------------------------------------------------------------------------
# Layout "attached": a body (housing) with distinct parts hung on it or standing in it (a coffee
# machine's basket and carafe). Furniture rules (arms, cushions) don't apply; parts are found by colour.

def colour_model(paths, bins=12):
    """Colour histogram of a part's own views (non-background pixels)."""
    h = np.zeros((bins, bins, bins))
    for p in paths:
        a = np.asarray(Image.open(p).convert("RGB")).reshape(-1, 3).astype(int)
        a = a[a.sum(1) > 40]
        idx = (a * bins // 256)
        np.add.at(h, (idx[:, 0], idx[:, 1], idx[:, 2]), 1)
    h = ndimage.gaussian_filter(h, 0.8)
    return h / max(h.sum(), 1e-9) + 1e-7


def locate_by_colour(view_path, models, bins=12):
    """Assign every pixel of a whole-object view to the part whose own views' colours explain it best;
    returns {part: (u0, u1, v0, v1)} as fractions of the view's object box (v from the top), or nothing
    for a part that isn't visible."""
    m, img = silhouette(view_path)
    a = np.asarray(img.convert("RGB")).astype(int)
    valid = m & (a.sum(2) > 40)
    idx = a * bins // 256
    names = list(models)
    like = np.stack([models[n][idx[..., 0], idx[..., 1], idx[..., 2]] for n in names], -1)
    best = np.argmax(like, -1)
    out = {}
    H_, W_ = m.shape
    for i, n in enumerate(names):
        # open hard enough to cut thin strands (a dark cavity edge touching dark glass), keep the one
        # biggest shape, and measure it on the 2nd-98th percentiles (stray pixels don't stretch the box)
        mask = ndimage.binary_opening(valid & (best == i), iterations=3)
        lab, k = ndimage.label(mask)
        if not k:
            continue
        sizes = ndimage.sum(mask, lab, range(1, k + 1))
        j = int(np.argmax(sizes)) + 1
        if sizes[j - 1] < 0.01 * m.sum():
            continue
        ys, xs = np.nonzero(lab == j)
        out[n] = (np.percentile(xs, 2) / W_, (np.percentile(xs, 98) + 1) / W_,
                  np.percentile(ys, 2) / H_, (np.percentile(ys, 98) + 1) / H_)
    return out


def colour_overlap(h1, h2):
    """Shared share of two colour histograms (1 = identical palettes). Parts painted like the body
    (a harvest-gold handset on a harvest-gold phone) can't be found by colour."""
    return float(np.minimum(h1 / h1.sum(), h2 / h2.sum()).sum())


def match_into(big, small, scales=None):
    """Where the outline `small` sits inside the outline `big` (both masks): the scale and offset
    that put the most of it on `big` and the least outside it (FFT correlation over scales).
    Returns (scale, x0, y0, placed mask in big's pixels)."""
    from scipy.signal import fftconvolve
    H_, W_ = big.shape
    h, w = small.shape
    base = H_ / h
    best = None
    big_edge = ndimage.binary_dilation(big & ~ndimage.binary_erosion(big), iterations=2).astype(float)
    for f in (scales or np.linspace(0.55, 1.0, 19)):
        sh, sw = max(4, int(round(h * base * f))), max(4, int(round(w * base * f)))
        if sh > H_ or sw > W_:
            continue
        t = np.asarray(Image.fromarray(small.astype(np.uint8) * 255).resize((sw, sh))) > 127
        on = fftconvolve(big.astype(float), t[::-1, ::-1].astype(float), mode="valid")
        # cover the big outline and never stick out of it; then (the tie-breaker: every placement fully
        # inside scores the same) the small outline's edges must lie on the big outline's edges
        te = t & ~ndimage.binary_erosion(t)
        edge_on = fftconvolve(big_edge, te[::-1, ::-1].astype(float), mode="valid")
        score = on - 2.0 * (t.sum() - on) + 4.0 * edge_on
        j = np.unravel_index(int(np.argmax(score)), score.shape)
        if best is None or score[j] > best[0]:
            best = (score[j], f * base, int(j[1]), int(j[0]), t)
    _, sc, x0, y0, t = best
    placed = np.zeros_like(big)
    placed[y0:y0 + t.shape[0], x0:x0 + t.shape[1]] = t
    return sc, x0, y0, placed


def locate_by_subtraction(view_path, body_view_path):
    """The body's own view fitted into the whole-object view (match_into); what the body doesn't
    explain is the attached parts. Returns (body box, [part regions largest first]) with boxes as
    fractions of the view's object box (u0, u1, v0, v1; v from the top) and each region's mask."""
    m, _ = silhouette(view_path)
    b, _ = silhouette(body_view_path)
    sc, x0, y0, placed = match_into(m, b)
    H_, W_ = m.shape
    ys, xs = np.nonzero(placed)
    body_box = (xs.min() / W_, (xs.max() + 1) / W_, ys.min() / H_, (ys.max() + 1) / H_)
    rest = ndimage.binary_opening(m & ~ndimage.binary_dilation(placed, iterations=2), iterations=2)
    lab, k = ndimage.label(rest)
    regions = []
    for i in range(1, k + 1):
        r = lab == i
        if r.sum() < 0.01 * m.sum():
            continue
        ys, xs = np.nonzero(r)
        # an edge of the region pressed against the fitted body may continue in front of it (a
        # handset's cups over the body's edge): that edge is hidden in this view
        touch = r & ndimage.binary_dilation(placed, iterations=5)
        hidden = set()
        if touch.any():
            ty, tx = np.nonzero(touch)
            w_, h_ = xs.max() - xs.min() + 1, ys.max() - ys.min() + 1
            if tx.mean() > xs.mean() + 0.15 * w_:
                hidden.add("right")
            if tx.mean() < xs.mean() - 0.15 * w_:
                hidden.add("left")
            if ty.mean() > ys.mean() + 0.15 * h_:
                hidden.add("bottom")
            if ty.mean() < ys.mean() - 0.15 * h_:
                hidden.add("top")
        regions.append({"mask": r, "box": (np.percentile(xs, 1) / W_, (np.percentile(xs, 99) + 1) / W_,
                                           np.percentile(ys, 1) / H_, (np.percentile(ys, 99) + 1) / H_),
                        "share": float(r.sum() / m.sum()), "hidden": sorted(hidden)})
    regions.sort(key=lambda r_: -r_["share"])
    return body_box, regions, {"scale": round(float(sc), 3), "fit_outside": round(float((placed & ~m).sum() / max(1, placed.sum())), 3)}


def orient_like(path, ref_path, out_path):
    """Turn/flip a part's view (0, 180 degrees, mirrored) to best match the same view of the whole
    object (outline IoU at the reference's size): sheets draw a part's top view upside down."""
    a, img = silhouette(path)
    r, _ = silhouette(ref_path)
    best = None
    ops = {"as drawn": lambda im: im, "turned 180": lambda im: im.rotate(180),
           "mirrored": lambda im: im.transpose(Image.Transpose.FLIP_LEFT_RIGHT),
           "flipped": lambda im: im.transpose(Image.Transpose.FLIP_TOP_BOTTOM)}
    for name, op in ops.items():
        t = np.asarray(op(Image.fromarray(a.astype(np.uint8) * 255)).resize(r.shape[::-1])) > 127
        iou = float((t & r).sum() / max(1, (t | r).sum()))
        if best is None or iou > best[1] + 0.02:            # keep the drawing unless clearly better
            best = (name, iou, op)
    if best[0] == "as drawn":
        return path, None
    best[2](Image.open(path)).save(out_path)
    return out_path, "%s (outline IoU %.2f with the whole-object view)" % (best[0], best[1])


def body_front_rule(views, tmp):
    """A body's front view much narrower (for its height) than its back view is a partial view (the
    sheet drew only what is left behind the attached parts): carve with the back's outline instead."""
    if "front" not in views or "back" not in views:
        return views, None
    fm, _ = silhouette(views["front"])
    bm, _ = silhouette(views["back"])
    fa, ba = fm.shape[1] / fm.shape[0], bm.shape[1] / bm.shape[0]
    if fa < 0.8 * ba:
        q = os.path.join(tmp, "body_front_from_back.png")
        Image.open(views["back"]).transpose(Image.Transpose.FLIP_LEFT_RIGHT).save(q)
        v = dict(views)
        v["front"] = q
        return v, "front view %.2f wide vs back %.2f: carved with the back's outline" % (fa, ba)
    return views, None


def build_attached(order, src_root):
    import bpy
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    root = os.path.join(src_root, order["views_folder"])
    W, D, H = order["width_m"], order["depth_m"], order["height_m"]
    tmp = os.path.join(tempfile.gettempdir(), "_hullasm_" + order["name"])
    os.makedirs(tmp, exist_ok=True)
    rep = {"layout": "attached", "parts": [], "skipped": order.get("skip", {})}
    asm_views = part_views(os.path.join(root, order["assembly"]))
    body_views = part_views(os.path.join(root, order["body"]))
    body_views = {k: p for k, p in body_views.items() if k in ("front", "back", "left", "right", "top")}
    body_views, note = body_front_rule(body_views, tmp)
    if note:
        rep["body_front"] = note
    if "top" in body_views and "top" in asm_views:
        q, note_t = orient_like(body_views["top"], asm_views["top"], os.path.join(tmp, "body_top.png"))
        if note_t:
            body_views["top"] = q
            rep["body_top"] = note_t
    body_own = {k: p for k, p in part_views(os.path.join(root, order["body"])).items()}
    attached = order["attached"]                  # [folder, ...]
    pviews = {f: {k: p for k, p in part_views(os.path.join(root, f)).items()
                  if k in ("front", "back", "left", "right", "top")} for f in attached}
    # 2. where each part is. By colour when the parts are painted unlike the body (an orange basket, a
    #    dark carafe on an almond housing); by subtraction when they share its paint (a harvest-gold
    #    handset on a harvest-gold phone): the body's own outline fitted into each whole-object view,
    #    and what it doesn't explain is the parts.
    models = {f: colour_model(list(pviews[f].values())) for f in attached}
    models["_body"] = colour_model(list(body_own.values()))
    overlaps = {f: round(colour_overlap(models[f], models["_body"]), 3) for f in attached}
    mode = "subtraction" if max(overlaps.values()) > SAME_PAINT else "colour"
    rep["locate"] = {"mode": mode, "colour_overlap_with_body": overlaps}
    boxes = {}                                    # part -> (x0, x1, y0, y1, z0, z1, located_top, top_from)
    body_box = None
    if mode == "colour":
        loc = {vw: locate_by_colour(asm_views[vw], models) for vw in ("front", "right", "left") if vw in asm_views}
        rep["located"] = {vw: {k: [round(x, 3) for x in b_] for k, b_ in d.items()} for vw, d in loc.items()}
        for f in attached:
            fr = loc.get("front", {}).get(f)
            sides = []
            if f in loc.get("right", {}):
                u0, u1, v0, v1 = loc["right"][f]
                sides.append((u0, u1, v0, v1))           # right view: image left = front
            if f in loc.get("left", {}):
                u0, u1, v0, v1 = loc["left"][f]
                sides.append((1 - u1, 1 - u0, v0, v1))
            if fr is None or not sides:
                rep["skipped"][f] = "not visible in the whole-object front and side views"
                continue
            y0 = float(np.median([s_[0] for s_ in sides])) * D - D / 2
            y1 = float(np.median([s_[1] for s_ in sides])) * D - D / 2
            zs_ = [(1 - fr[3], 1 - fr[2])] + [(1 - s_[3], 1 - s_[2]) for s_ in sides]
            z0 = float(np.median([z[0] for z in zs_])) * H
            located_top = float(np.median([z[1] for z in zs_])) * H
            x0, x1 = fr[0] * W - W / 2, fr[1] * W - W / 2
            # The bottom edge is reliable (a part against the body's colour). The top is trusted when
            # every view agrees on it (the orange basket); when they disagree it has merged with
            # something dark above it (the carafe under the filter holder): its own proportions decide.
            tops = [z[1] for z in zs_]
            top_from = "views agree"
            z1 = located_top
            if max(tops) - min(tops) > 0.03 and "front" in pviews[f]:
                z1 = z0 + aspect(pviews[f]["front"]) * (x1 - x0)
                top_from = "own proportions (views disagree by %.0f%% of the height)" % ((max(tops) - min(tops)) * 100)
            boxes[f] = (x0, x1, y0, y1, z0, z1, located_top, top_from)
    else:
        sub = {vw: locate_by_subtraction(asm_views[vw], body_own[vw]) for vw in ("front", "right", "left")
               if vw in asm_views and vw in body_own}
        if "front" not in sub or not ({"right", "left"} & set(sub)):
            raise RuntimeError("subtraction needs the body's own front and a side view")
        rep["located"] = {vw: {"body": [round(x, 3) for x in v[0]], "fit": v[2],
                               "regions": [[round(x, 3) for x in r_["box"]] + r_["hidden"] for r_ in v[1]]} for vw, v in sub.items()}
        fm_, _ = silhouette(asm_views["front"])
        sk = "right" if "right" in sub else "left"
        sm_, _ = silhouette(asm_views[sk])
        if order.get("body_width_m"):
            # one real dimension (the body's width) scales the whole drawing
            bu0, bu1 = sub["front"][0][:2]
            px = order["body_width_m"] / ((bu1 - bu0) * fm_.shape[1])
            W, H = fm_.shape[1] * px, fm_.shape[0] * px
            D = sm_.shape[1] * H / sm_.shape[0]
            rep["size_from"] = "body width %.3f m; whole object %.3f x %.3f x %.3f m from the views" % (
                order["body_width_m"], W, D, H)
        fb = sub["front"][0]
        side_boxes = []
        for vw in ("right", "left"):
            if vw in sub:
                u0, u1 = sub[vw][0][:2]
                side_boxes.append((u0, u1) if vw == "right" else (1 - u1, 1 - u0))
        body_box = (fb[0] * W - W / 2, fb[1] * W - W / 2,
                    float(np.median([b_[0] for b_ in side_boxes])) * D - D / 2,
                    float(np.median([b_[1] for b_ in side_boxes])) * D - D / 2,
                    (1 - fb[3]) * H, (1 - fb[2]) * H)
        for n, f in enumerate(attached):
            # Each edge of the part's box comes from a view where it is visible (not pressed against the
            # body); the top is the median of the visible tops, the bottom the highest visible bottom
            # (a cord dangling below only ever adds); hidden extents come from the part's own proportions.
            edges = {"x0": [], "x1": [], "y0": [], "y1": [], "top": [], "bottom": []}
            for vw, (bb, regs, _) in sub.items():
                if n >= len(regs):
                    continue
                u0, u1, v0, v1 = regs[n]["box"]
                hid = set(regs[n]["hidden"])
                lo_k, hi_k = ("x0", "x1") if vw == "front" else ("y0", "y1")
                span = W if vw == "front" else D
                if vw == "left":                        # left view: image left = back
                    u0, u1 = 1 - u1, 1 - u0
                    hid = {{"left": "right", "right": "left"}.get(e, e) for e in hid}
                if "left" not in hid:
                    edges[lo_k].append(u0 * span - span / 2)
                if "right" not in hid:
                    edges[hi_k].append(u1 * span - span / 2)
                if "top" not in hid:
                    edges["top"].append((1 - v0) * H)
                if "bottom" not in hid:
                    edges["bottom"].append((1 - v1) * H)
            if not edges["top"] or not edges["bottom"]:
                rep["skipped"][f] = "no visible top or bottom left over by the body"
                continue
            z1 = float(np.median(edges["top"]))
            z0 = float(max(edges["bottom"]))
            located_top, top_from = z1, "visible edges"
            pv = pviews[f]
            fa = aspect(pv["front"]) if "front" in pv else None                   # height / width
            sa = aspect(pv.get("left") or pv.get("right")) if ("left" in pv or "right" in pv) else None
            h = z1 - z0
            if fa and h > 1.15 * fa * (np.median(edges["x1"]) - np.median(edges["x0"])) if edges["x0"] and edges["x1"] else False:
                z0 = z1 - fa * (np.median(edges["x1"]) - np.median(edges["x0"]))
                top_from = "kept the top: more hangs below than the part's proportions"
                h = z1 - z0
            def span_of(lo, hi, size):
                if lo and hi:
                    return float(np.median(lo)), float(np.median(hi))
                if lo and size:
                    return float(np.median(lo)), float(np.median(lo)) + size
                if hi and size:
                    return float(np.median(hi)) - size, float(np.median(hi))
                return None
            xs_ = span_of(edges["x0"], edges["x1"], h / fa if fa else None)
            ys_ = span_of(edges["y0"], edges["y1"], h / sa if sa else None)
            if xs_ is None or ys_ is None:
                rep["skipped"][f] = "box not measurable from the visible edges"
                continue
            (x0, x1), (y0, y1) = xs_, ys_
            hidden_note = [k for k in ("x0", "x1", "y0", "y1") if not edges[k]]
            if hidden_note:
                top_from += "; %s from the part's own proportions (hidden against the body)" % ", ".join(hidden_note)
            boxes[f] = (x0, x1, y0, y1, z0, z1, located_top, top_from)
    placed = []
    for f in attached:
        if f not in boxes:
            continue
        x0, x1, y0, y1, z0, z1, located_top, top_from = boxes[f]
        w, d, h = x1 - x0, y1 - y0, z1 - z0
        if min(w, d, h) < 0.01:
            rep["skipped"][f] = "located box too small"
            continue
        views = dict(pviews[f])
        if "top" in views:
            views["top"], _ = orient_top(views["top"], w, d, os.path.join(tmp, "top_%s.png" % f))
        obj = hull_prop(views, h, res=order.get("part_res", 100), name="%s_%s" % (order["name"], f), width_m=w,
                        depth_m=d, features=False, paint=False, rough=order.get("rough", 0.6))
        texturing.project(obj, paint_views(views, tmp, "p_" + f), w, d, h, others=[], name=obj.name,
                          rough=order.get("rough", 0.6))
        obj.location = ((x0 + x1) / 2, (y0 + y1) / 2, z0)
        bpy.context.view_layer.update()
        placed.append(obj)
        obj["box"] = [x0, x1, y0, y1, z0, z1]
        rep["parts"].append({"part": f, "box_m": [[round(x0, 3), round(x1, 3)], [round(y0, 3), round(y1, 3)], [round(z0, 3), round(z1, 3)]],
                             "located_top_m": round(located_top, 3), "top_from": top_from,
                             "revolve": HULL_REPORT.get("revolve")})
    # 3. the body: its own views' shape, hollowed exactly where the parts sit (the assembled drawing
    #    wins where the body's own drawing filled a part's space: a solid arm where the basket hangs)
    bpy.context.view_layer.update()

    bx0, bx1, by0, by1, bz0, bz1 = body_box or (-W / 2, W / 2, -D / 2, D / 2, 0.0, H)
    if body_box:
        rep["body_box_m"] = [[round(bx0, 3), round(bx1, 3)], [round(by0, 3), round(by1, 3)], [round(bz0, 3), round(bz1, 3)]]

    def minus_part_shapes(keep_, carve_, W_, D_, H_):
        k_ = keep_.copy()
        nx_, ny_, nz_ = k_.shape
        xs = bx0 + (np.arange(nx_) + 0.5) / nx_ * (bx1 - bx0)          # world coordinates of the voxels
        ys = by0 + (np.arange(ny_) + 0.5) / ny_ * (by1 - by0)
        zs = bz0 + (np.arange(nz_) + 0.5) / nz_ * (bz1 - bz0)
        for o in placed:
            o.data.update()
            t = BVHTree.FromPolygons([o.matrix_world @ v.co for v in o.data.vertices], [p_.vertices for p_ in o.data.polygons])
            x0_, x1_, y0_, y1_, z0_, z1_ = o["box"]
            inside = np.zeros_like(k_)
            for i in np.nonzero((xs > x0_ - 0.02) & (xs < x1_ + 0.02))[0]:
                for j in np.nonzero((ys > y0_ - 0.02) & (ys < y1_ + 0.02))[0]:
                    zs_hit, origin = [], Vector((xs[i], ys[j], bz0 - 0.01))
                    for _ in range(16):                  # parity along +z: inside between hit pairs
                        h_ = t.ray_cast(origin, Vector((0, 0, 1)), 2 * H)
                        if h_[0] is None:
                            break
                        zs_hit.append(h_[0].z)
                        origin = h_[0] + Vector((0, 0, 1e-5))
                    for a_, b_ in zip(zs_hit[0::2], zs_hit[1::2]):
                        inside[i, j, (zs >= a_) & (zs <= b_)] = True
            inside = ndimage.binary_erosion(inside, iterations=1)   # body keeps a voxel of overlap
            k_ &= ~inside
        return k_
    # A top view carves only if it agrees with the front and side views: its depth/width within
    # TOP_AGREE of the body's measured depth/width, and (if it had to be turned to match the whole-object
    # top view) a clear match. Sheets often draw the "top" with a band of the front face showing,
    # which is not a plan: carving with it sets the front back everywhere but where it is drawn
    # longest (ribs down a phone's face). Such a view still paints.
    body_paint_only = ()
    if "top" in body_views:
        tm_, _ = silhouette(body_views["top"])
        got, want = tm_.shape[0] / tm_.shape[1], (by1 - by0) / (bx1 - bx0)
        weak = rep.get("body_top") and float(rep["body_top"].split("IoU ")[1].split(" ")[0]) < 0.85
        if abs(got / want - 1) > TOP_AGREE or weak:
            body_paint_only = ("top",)
            rep["body_top_paint_only"] = "top view depth/width %.2f vs %.2f from the front and side views%s" % (
                got, want, ", weak match with the whole-object top" if weak else "")
    body = hull_prop(body_views, bz1 - bz0, res=order.get("res", 150), name=order["name"] + "_body",
                     width_m=bx1 - bx0, depth_m=by1 - by0, features=False, paint=False, rough=order.get("rough", 0.6),
                     voxel_hook=minus_part_shapes, paint_only=body_paint_only)
    body.location = ((bx0 + bx1) / 2, (by0 + by1) / 2, bz0)
    bpy.context.view_layer.update()
    body.data.update()
    btree = BVHTree.FromPolygons([body.matrix_world @ v.co for v in body.data.vertices], [p.vertices for p in body.data.polygons])
    # 4. snap each part onto the body and check it is seated, measured from the part's real surface
    #    (its vertices facing each way), never from its box: a rounded hull sits inside its box.
    #    Gravity first: a part with body under it stands on it; else one with body over it hangs
    #    from it; else it is mounted against the body behind it.
    DIRS = {"down": Vector((0, 0, -1)), "up": Vector((0, 0, 1)), "back": Vector((0, 1, 0)),
            "left": Vector((-1, 0, 0)), "right": Vector((1, 0, 0))}

    def in_body(p_):
        h_ = btree.find_nearest(p_)
        return h_[0] is not None and (h_[0] - p_).dot(h_[1]) > 0

    def gaps_toward(obj_, dv, reach=SUPPORT_REACH):
        """Distances from the part's vertices facing dv to the body along dv (0 inside the body,
        None where the body is out of reach)."""
        m3 = obj_.matrix_world.to_3x3()
        out = []
        for v in obj_.data.vertices:
            n_ = (m3 @ v.normal).normalized()
            if n_.dot(dv) < 0.7:
                continue
            p_ = obj_.matrix_world @ v.co
            if in_body(p_):
                out.append(0.0)
                continue
            hit = btree.ray_cast(p_ + dv * 1e-4, dv, reach)
            out.append(None if hit[0] is None else hit[3])
        return out

    def support(obj_):
        """{direction: (share of facing vertices with body in reach, p10 gap m, share touching)}"""
        res = {}
        for name_, dv in DIRS.items():
            g_ = gaps_toward(obj_, dv)
            hit = [x for x in g_ if x is not None]
            if not g_ or not hit:
                res[name_] = (0.0, None, 0.0)
                continue
            # touching share over the near layer (the facing surface within NEAR_LAYER of the closest
            # approach): a C-shaped handset meets the body with its cups and its handle curves away by
            # design; a part floating at an even gap still has its whole near layer clear
            p10 = float(np.percentile(hit, 10))
            near = [x for x in hit if x <= p10 + NEAR_LAYER]
            res[name_] = (len(hit) / len(g_), p10, sum(1 for x in near if x <= MAX_GAP) / max(1, len(near)))
        return res

    for obj, entry in zip(placed, rep["parts"]):
        obj.data.update()
        before = support(obj)
        best = None
        # gravity, then hanging, then against the nearest body beside or behind it
        side_ = sorted(("back", "left", "right"), key=lambda k: before[k][1] if before[k][0] >= SUPPORT_SHARE else 1e9)
        order_ = ("down", "up") + tuple(side_)
        if os.environ.get("HULLASM_NOGRAVITY"):         # test switch: the old nearest-surface snap
            order_ = sorted(order_, key=lambda k: before[k][1] if before[k][0] >= SUPPORT_SHARE else 1e9)
        for name_ in order_:
            share, gap, _ = before[name_]
            if share >= SUPPORT_SHARE:
                best = name_
                break
        if best is not None:
            obj.location += DIRS[best] * (before[best][1] + SNAP_SINK)
            bpy.context.view_layer.update()
        after = support(obj)
        obj["support"] = best or ""
        obj["seated_gap_m"] = -1.0 if best is None else after[best][1]
        # a part that has body right under it must stand on it whatever else it touches
        obj["under_gap_m"] = after["down"][1] if after["down"][0] >= SUPPORT_SHARE and after["down"][1] is not None else -1.0
        obj["touch_share"] = after[best][2] if best else 0.0
        obj["under_touch_share"] = after["down"][2] if obj["under_gap_m"] >= 0 else 1.0
        entry["snapped"] = None if best is None else {
            "towards": best, "moved_mm": round((before[best][1] + SNAP_SINK) * 1000, 1),
            "gap_after_mm": round(after[best][1] * 1000, 1), "touching_share": round(after[best][2], 2),
            "under_gap_mm": round(obj["under_gap_m"] * 1000, 1) if obj["under_gap_m"] >= 0 else None}
    # 5. the body painted from the whole-object views, the parts occluding it
    texturing.project(body, paint_views(asm_views, tmp, "body"), W, D, H, others=placed, name=body.name,
                      rough=order.get("rough", 0.6))
    # 6. every part must be seated where it rests/hangs, and stand on any body right under it
    rep["gaps_mm"] = [{"part": o.name, "support": o["support"] or None,
                       "seated_gap_mm": round(o["seated_gap_m"] * 1000, 1) if o["seated_gap_m"] >= 0 else None,
                       "under_gap_mm": round(o["under_gap_m"] * 1000, 1) if o["under_gap_m"] >= 0 else None,
                       "touching": round(min(o["touch_share"], o["under_touch_share"]), 2)}
                      for o in placed]
    # a few vertices sunk in is not seated: a real share of the facing surface must touch
    bad = [g for g in rep["gaps_mm"] if g["seated_gap_mm"] is None or g["seated_gap_mm"] > MAX_GAP * 1000
           or (g["under_gap_mm"] is not None and g["under_gap_mm"] > MAX_GAP * 1000) or g["touching"] < MIN_TOUCH]
    if bad:
        print("HULLASM report", json.dumps(rep, default=str))           # what was measured, for the person
        raise RuntimeError("parts not seated on the body: " + "; ".join(
            "%s %s (gap %s mm, under %s mm, touching %s)" % (g["part"], g["support"], g["seated_gap_mm"], g["under_gap_mm"], g["touching"]) for g in bad))
    return rep
