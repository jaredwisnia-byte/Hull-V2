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

import numpy as np
from PIL import Image
from scipy import ndimage

from . import blades, edge_guide, texturing
from .hull import HULL_REPORT, hull_prop, silhouette

FOOT_SINK = 0.015


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


def paint_views(views, out_dir, tag):
    """Views cropped to the object (the frame texturing.project maps to), paint padded past the outline
    with the object's own colours so rounded edges never pick up the sheet background."""
    os.makedirs(out_dir, exist_ok=True)
    out = {}
    for k, p in views.items():
        m, img = silhouette(p)
        a = np.asarray(img).copy()
        idx = ndimage.distance_transform_edt(~ndimage.binary_erosion(m, iterations=2), return_distances=False,
                                             return_indices=True)
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


def part_views(folder):
    return {f[2:-4]: os.path.join(folder, f) for f in sorted(os.listdir(folder)) if f.startswith("v_") and f.endswith(".png")}


def aspect(path):
    m, _ = silhouette(path)
    return m.shape[0] / m.shape[1]          # height / width


def build(order, src_root):
    """Builds the assembly into the scene; returns a report dict."""
    root = os.path.join(src_root, order["views_folder"])
    W, D, H = order["width_m"], order["depth_m"], order["height_m"]
    parts = order["parts"]                  # {"side": folder, "seat": folder, "back": folder, "foot": folder}
    tmp = os.path.join("/tmp", "_hullasm_" + order["name"])
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
    # 4. the frame: whole-object hull minus the parts' spaces
    def minus_parts(keep_, carve, W_, D_, H_):
        k = keep_.copy()
        xs = (np.arange(nx) + 0.5) / nx * W - W / 2
        ys = (np.arange(ny) + 0.5) / ny * D - D / 2
        zs = (np.arange(nz) + 0.5) / nz * H
        for b in boxes:
            if b["kind"] == "foot":
                continue
            mx = (xs >= b["x"][0] - 0.005) & (xs <= b["x"][1] + 0.005)
            my = (ys >= b["y"][0] - 0.005) & (ys <= b["y"][1] + 0.005)
            mz = (zs >= b["z"][0] - 0.005) & (zs <= b["z"][1] + 0.005)
            k[np.ix_(mx, my, mz)] = False
        k[:, :, zs < foot_top] = False           # feet are their own parts
        # The frame is what lies under the parts and behind them; strips between part spaces that
        # no part claims (between an arm and the cushions) would show as lumps.
        under = [b["z"][0] for b in boxes if b["kind"] in ("seat", "back")]
        behind = [b["y"][1] for b in boxes if b["kind"] == "back"]
        if under:
            zcut = min(under)
            yb = max(behind) if behind else D / 2
            kill = (zs[None, None, :] >= zcut) & (ys[None, :, None] < yb - 0.005)
            k &= ~kill
        for b in boxes:
            if b["kind"] == "side":
                mx = (xs >= b["x"][0] - 0.03) & (xs <= b["x"][1] + 0.03)
                k[mx] = False
        return k
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
                    if f.startswith("g_"):
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
        w, d, h = b["x"][1] - b["x"][0], b["y"][1] - b["y"][0], b["z"][1] - b["z"][0]
        if min(w, d, h) <= 0.01:
            continue
        obj = hull_prop(views, h, res=order.get("part_res", 90), name="%s_%s_%d" % (order["name"], b["kind"], n),
                        width_m=w, depth_m=d, features=False, rough=order.get("rough", 0.6), paint=False,
                        sil_override=guided_sil(views, g), mesh_hook=guide_hook(g, w, d, h))
        # blended projection (facing^4 x visibility): no stretched streaks where a face is seen at a slant
        texturing.project(obj, paint_views(views, tmp, "p%d" % n), w, d, h, others=[], name=obj.name,
                          rough=order.get("rough", 0.6))
        obj.location = ((b["x"][0] + b["x"][1]) / 2, (b["y"][0] + b["y"][1]) / 2, b["z"][0])
        placed.append(obj)
        rep["parts"].append({"kind": b["kind"], "box_m": [[round(v, 3) for v in b[a]] for a in ("x", "y", "z")]})
    # 6. the frame last, painted with the placed parts occluding it
    frame = hull_prop(asm_views, H, res=order.get("res", 140), name=order["name"] + "_frame", width_m=W, depth_m=D,
                      blades=True, features=False, rough=order.get("rough", 0.6), voxel_hook=minus_parts, paint=False,
                      sil_override=asm_sil,
                      mesh_hook=guide_hook(guides.get("assembly"), W, D, H))
    texturing.project(frame, paint_views(asm_views, tmp, "frame"), W, D, H, others=placed, name=frame.name,
                      rough=order.get("rough", 0.6))
    rep["guide_edits"] = guide_counts

    return rep
