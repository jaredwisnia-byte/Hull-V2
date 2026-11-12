"""Layout "parts": every part manufactured from its own views, then assembled like the photo shows.

A parts sheet gives the whole object (the "photo": front, sides, back, top) and each part with its own
views. Each part is built separately (a hull from its views; round parts as lathes; thin parts with their
drawn holes cut through) and painted from its own views, then placed and seated on what it attaches to.
The order is a declarative plan, one entry per part; nothing here knows what the object is:

    "layout": "parts", "assembly": "<folder>", "body_width_m": 0.14, "parts": [
      {"name": "body", "views": "body", "root": true},
      {"name": "plate", "views": "plate", "attach": {"to": "body", "face": "back", "fit": "inside"}},
      {"name": "dial_face", "views": "dial_face", "locate": "match", "attach": {"to": "body", "face": "front"}},
      {"name": "dial_wheel", "views": "dial_wheel", "locate": "concentric", "attach": {"to": "dial_face", "face": "front"}},
      {"name": "hooks", "views": "hooks", "locate": "protrusion", "attach": {"to": "body", "face": "top"}},
      {"name": "handset", "views": "handset", "locate": "residual", "attach": {"to": "body", "face": "left"}},
      {"name": "earpiece", "views": "cap", "attach": {"to": "handset", "face": "right", "at": "top"}},
      {"name": "mouthpiece", "views": "cap", "attach": {"to": "handset", "face": "right", "at": "bottom"}},
      {"name": "cord", "locate": "leftover", "attach": {"to": "handset", "face": "bottom"}}]

How a part is located (where in the object, and how big):
  root        the body's own outline fitted into the photo (hull_assembly.match_into). Every part is
              located in drawing units first; then the scale comes from human scale (the handbook's
              contacts measured in the drawing, propkit/human_scale.py) or from a given body_width_m
  residual    the part sticks out of the body's outline: the region the body leaves over in the photo,
              each box edge from a view where it is visible (hull_assembly.locate_by_subtraction)
  match       the part lies on the body: its painting matched into the photo (propkit.locate)
  concentric  centred on its parent; size from the sheet's drawing scale relative to the parent's own
              drawing
  protrusion  drawn as part of the parent's own view, sticking out of its outline (cradle hooks on a
              shell's top edge): position and size from that protrusion
  attach      on the parent's face ("at": top / bottom / centre), sized to fit that face
  inset       set into an opening of its parent's front (a CRT in its cabinet): found like match, its face
              just behind the front surface; the body spec's "recess" recesses the openings its own front
              drawing shows
  leftover    whatever the photo shows that no part explains (a coiled cord): a hull of those regions,
              painted from the photo
Then every part is seated on its parent along the face it attaches to and gap-checked.
"""
from .simplification import screen_tolerance, decimate_to_error
import os
import tempfile

import numpy as np
from PIL import Image
from scipy import ndimage

from . import texturing
from .hull import HULL_REPORT, hull_prop, silhouette
from .hull_assembly import (MAX_GAP, MIN_TOUCH, NEAR_LAYER, SNAP_SINK, SUPPORT_REACH, aspect, locate_by_subtraction,
                            orient_like, paint_views, part_views)
from .locate import find_part
from . import handbook as HB

PART_MIN_TRIS = 300   # no part decimated below this
# openings drawn in a body's front are recessed this share of its depth (order may set depth_m)
RECESS_SHARE = 0.12
# an inset part's face sits this share of its parent's depth behind the parent's front
INSET_BEHIND = 0.03
# an opening must cover this share of the front to be recessed (knob holes stay painted)
OPENING_MIN = 0.02
# an inset part is this much larger than its opening, its rim hidden behind the edge
INSET_OVERSIZE = 1.04
# an opening filling this share of its convex outline is given that outline
CONVEX_OPENING = 0.9
# a body filling this share of the front (both ways) is the object's envelope
ENVELOPE = 0.9
ELONGATED = 3.0     # a leftover whose centreline is this many widths long is swept as a tube
INTO = {"front": (0, 1, 0), "back": (0, -1, 0), "top": (0, 0, -1), "bottom": (0, 0, 1),
        # direction from a part on that face into its parent
        "left": (1, 0, 0), "right": (-1, 0, 0)}


def _views(folder):
    return {k: p for k, p in part_views(folder).items() if k in ("front", "back", "left", "right", "top")}


def _holes(path, box):
    hp = os.path.join(os.path.dirname(path), "h_%s.png" %
                      os.path.basename(path)[2:-4])
    if not os.path.exists(hp):
        return None
    h = np.asarray(Image.open(hp).convert("L").crop(box)) > 127
    return h if h.any() else None


def repeated_holes(front_path):
    """The repeated openings drawn in a part's front view (a dial's finger holes): their median
    diameter as a share of the part's drawn width, and how many. One big opening (a centre window) is
    not a repeat. Returns (share, count) or None."""
    m, _, box = silhouette(front_path, with_box=True)
    h = _holes(front_path, box)
    if h is None:
        return None
    lab, k = ndimage.label(h)
    if k < 3:
        return None
    areas = ndimage.sum(h, lab, range(1, k + 1))
    med = float(np.median(areas))
    rep_ = areas[(areas > 0.6 * med) & (areas < 1.6 * med)]
    if len(rep_) < 3:
        return None
    return float(np.median(2 * np.sqrt(rep_ / np.pi))) / m.shape[1], len(rep_)


def contact_measure(c, boxes, photo, plan, root, todo=()):
    """A handbook contact measured in the drawing (drawing units), or None. The part is found by its
    name or by the views it is drawn from (both caps of a handset are drawn as one "cap"). Measures:
    width / height / depth (the part as drawn, before it is turned onto a side face), top_height (above
    the floor), and hole_diameter (the repeated openings drawn in its front view)."""
    W, D, H = photo
    part, m = c["part"], c["measure"]
    if part == "whole":
        return {"width": W, "depth": D, "height": H}.get(m)
    spec = next((p for p in plan if p["name"] == part), None) or next(
        (p for p in plan if p.get("views") == part), None)
    if spec is None or spec["name"] not in boxes:
        return None
    b = boxes[spec["name"]]
    side = any(t[0] == spec["name"] and t[3][0] == "side" for t in todo)
    w, d, h = (b[3] - b[2], b[1] - b[0], b[5] - b[4]
               ) if side else (b[1] - b[0], b[3] - b[2], b[5] - b[4])
    if m in ("width", "depth", "height"):
        return {"width": w, "depth": d, "height": h}[m]
    if m == "top_height":
        return b[5]
    if m == "hole_diameter" and spec.get("views"):
        got = repeated_holes(os.path.join(root, spec["views"], "v_front.png"))
        return got[0] * w if got else None
    return None


def openings(front_path, min_share=None):
    """Openings drawn in a part's front view (background seen through), largest first, as (u0, u1, v0, v1)
    fractions of its object box."""
    m, _, box = silhouette(front_path, with_box=True)
    holes = _holes(front_path, box)
    if holes is None or holes.shape != m.shape:
        return []
    lab, k = ndimage.label(ndimage.binary_opening(holes, iterations=1))
    out = []
    for i, sl in enumerate(ndimage.find_objects(lab), 1):
        a = int((lab[sl] == i).sum())
        if a >= (OPENING_MIN if min_share is None else min_share) * m.sum():
            out.append((a, (sl[1].start / m.shape[1], sl[1].stop / m.shape[1],
                       sl[0].start / m.shape[0], sl[0].stop / m.shape[0])))
    return [b for _, b in sorted(out, reverse=True)]


def recess_hook(front_path, depth_m, report, min_share=None):
    """A hull voxel_hook: the openings drawn in a body's own front view (background seen through it: a
    screen opening in a "no screen" drawing, knob holes) recessed depth_m into the body from its front
    surface, instead of being painted on a flat front."""
    m, _, box = silhouette(front_path, with_box=True)
    holes = _holes(front_path, box)
    if holes is None or holes.shape != m.shape:
        return None
    lab, k = ndimage.label(holes)
    sizes = ndimage.sum(holes, lab, range(1, k + 1))
    keepl = [i + 1 for i, s_ in enumerate(sizes) if s_ >= (
        OPENING_MIN if min_share is None else min_share) * m.sum()]
    op = np.zeros_like(holes)
    from skimage.morphology import convex_hull_image
    for i in keepl:
        one = lab == i
        hull_ = convex_hull_image(one)
        # a nearly convex opening (a screen, a dial window) is drawn with a ragged painted edge: its
        # convex outline is the opening; a shaped one (an L, a slot pattern) keeps its own outline
        op |= hull_ if one.sum() >= CONVEX_OPENING * \
            hull_.sum() else ndimage.binary_opening(one, iterations=1)
    report["openings"] = int(len(keepl))
    report["recess_mm"] = round(depth_m * 1000, 1)

    def hook(keep, views, W, D, H):
        nx, ny, nz = keep.shape
        hh, ww = op.shape
        xi = np.clip(((np.arange(nx) + 0.5) / nx * ww).astype(int), 0, ww - 1)
        zi = np.clip(((1 - (np.arange(nz) + 0.5) / nz)
                     * hh).astype(int), 0, hh - 1)
        mask = op[np.ix_(zi, xi)].T                                   # (x, z)
        dv = max(1, int(round(depth_m / (D / ny))))
        # first solid voxel from the front, per (x, z)
        front = np.where(keep.any(1), keep.argmax(1), ny)
        removed = 0
        lab_, k_ = ndimage.label(mask & (front < ny))
        for j in range(1, k_ + 1):
            cells = lab_ == j
            # one plane per opening (its front surface's median): a recess is a clean prism, not a
            # copy of every bump of the front surface
            f = int(np.median(front[cells]))
            ix, iz = np.nonzero(cells)
            removed += int(keep[ix, f:f + dv, iz].sum())
            for a, b in zip(ix, iz):
                keep[a, :f + dv, b] = False
        report["recess_voxels"] = removed
        return keep
    return hook


def build_part(views, w, d, h, name, tmp, res=110, rough=0.5, cut_holes=True, defer=None, automatic_depth=False, cad_export=False):
    """A part from its own views at size w x d x h (m), painted from its own views. Background seen
    through its front view (split's h_ mask: a hook frame's opening, a dial's finger holes) is an opening
    along that view and is cut through; a part with only a front view is a plate of depth d."""
    import bpy  # noqa: F401
    views = dict(views)
    if not ({"right", "left"} & set(views)):
        fm, _ = silhouette(views["front"])
        sh = fm.shape[0]
        sw = max(3, int(round(sh * d / max(h, 1e-6))))
        q = os.path.join(tmp, "%s_side.png" % name)
        im = Image.new("RGB", (sw + 16, sh + 16), (0, 0, 0))
        im.paste(Image.new("RGB", (sw, sh), (128, 128, 128)), (8, 8))
        im.save(q)
        views["right"] = q
    sil = {k: silhouette(p) for k, p in views.items()}
    notes = []
    if cut_holes:
        m, img, box = silhouette(views["front"], with_box=True)
        holes = _holes(views["front"], box)
        if holes is not None and holes.shape == m.shape:
            sil["front"] = (m & ~holes, img)
            if "back" in sil and sil["back"][0].shape == m.shape:
                sil["back"] = (sil["back"][0] & ~
                               holes[:, ::-1], sil["back"][1])
            notes.append(
                "%d px of background seen through its front view cut through" % int(holes.sum()))
    options = {}
    detail = {}
    if automatic_depth:
        from . import surface_detail
        observed = {k: v for k, v in views.items(
        ) if not v.endswith('_side.png')}
        plan = surface_detail.analyse(observed, (w, d, h), detail)
        plan['cad_export'] = cad_export
        plan['diagnostic_folder'] = os.path.join(tmp, name + '_surface')
        options = {'field_hook': lambda field: surface_detail.apply_field(field, plan),
                   'mesh_hook': lambda obj: surface_detail.capture_high(obj, plan),
                   'smooth_iters': 0, 'decimate': 1.}
    obj = hull_prop(views, h, res=res, name=name, width_m=w, depth_m=d, features=False, paint=False, rough=rough,
                    sil_override=sil, **options)
    if detail:
        import json
        obj['surface_detail_report'] = json.dumps(detail)
    rev = HULL_REPORT.get("revolve")
    paint = ({k: v for k, v in views.items()
             if not v.endswith("_side.png")}, w, d, h)
    if defer is not None:
        # painted once its final topology is known (paint_deferred)
        defer.append((obj, paint))
    else:
        texturing.project(obj, paint_views(
            paint[0], tmp, "p_" + name), w, d, h, others=[], name=obj.name, rough=rough)
    return obj, notes, rev


def _longest_path(sk):
    """Pixels of a skeleton's longest path (two breadth-first sweeps), in order."""
    from collections import deque
    pts = set(zip(*np.nonzero(sk)))
    if not pts:
        return []

    def bfs(start):
        prev, dist, q = {start: None}, {start: 0}, deque([start])
        while q:
            p_ = q.popleft()
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    n_ = (p_[0] + dy, p_[1] + dx)
                    if n_ in pts and n_ not in prev:
                        prev[n_] = p_
                        dist[n_] = dist[p_] + 1
                        q.append(n_)
        far = max(dist, key=dist.get)
        return far, prev

    a, _ = bfs(next(iter(pts)))
    b, prev = bfs(a)
    path = [b]
    while prev[path[-1]] is not None:
        path.append(prev[path[-1]])
    return path


def centreline(front, side, box, side_is_left=False):
    """The 3D centreline of an elongated region seen in the front and side views, in the part's own
    frame (x, y centred, z from 0): the front view's skeleton gives x and z, the side view's region y."""
    from skimage.morphology import skeletonize
    x0, x1, y0, y1, z0, z1 = box
    w, d, h = x1 - x0, y1 - y0, z1 - z0
    hh, ww = front.shape
    path = _longest_path(skeletonize(front))
    r_px = float(np.median(ndimage.distance_transform_edt(
        front)[tuple(np.array(path).T)])) if path else 1.0
    sh, sw = side.shape
    pts = []
    for (py, px_) in path[::max(1, int(r_px / 2))]:
        x = (px_ + 0.5) / ww * w - w / 2
        z = h - (py + 0.5) / hh * h
        row = min(sh - 1, int((1 - z / h) * sh))
        cols = np.nonzero(side[row])[0]
        u = (cols.mean() + 0.5) / sw if len(cols) else 0.5
        if side_is_left:
            u = 1 - u
        pts.append(np.array([x, u * d - d / 2, z]))
    if len(pts) < 3:
        return None, r_px / ww * w
    P = np.array(pts)
    P = np.vstack([ndimage.gaussian_filter1d(
        P[:, i], 1.5, mode="nearest") for i in range(3)]).T
    return P, r_px / ww * w


def sweep_tube(front, side, box, name, side_is_left=False, segments=10):
    """A tube swept along an elongated region's centreline, radius its half width (no handbook entry)."""
    from .cord import tube
    P, r = centreline(front, side, box, side_is_left)
    if P is None:
        return None, r
    return tube(P, r, name, segments), r


# Compatibility imports preserve existing callers while sharing one implementation.


def build_parts(order, src_root):
    import bpy
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    root = os.path.join(src_root, order["views_folder"])
    tmp = os.path.join(tempfile.gettempdir(), "_parts_" + order["name"])
    os.makedirs(tmp, exist_ok=True)
    rep = {"layout": "parts", "parts": {}}
    asm = part_views(os.path.join(root, order["assembly"]))
    # the reference handbook: the parts list, finishes, and how the object meets the human body
    hb = HB.entry(order["handbook"]) if order.get("handbook") else None
    plan = order.get("parts") or (hb or {}).get("assembly")
    contacts = HB.contacts(hb)
    given = order.get("body_width_m")
    if not given and not contacts:
        raise ValueError(
            "%s: no body_width_m and no human-scale contacts in the handbook" % order["name"])
    if hb:
        rep["handbook"] = hb["name"]
        if hb.get("mount") and not order.get("mount"):
            order["mount"] = hb["mount"]

    def kind_of(spec_):
        return spec_.get("is") or spec_["name"]

    def finish_of(name_, spec_=None):
        return HB.material(hb, name_, kind_of(spec_) if spec_ else None, order.get("rough", 0.5))
    body_spec = next(p for p in plan if p.get("root"))
    body_views = _views(os.path.join(root, body_spec["views"]))
    body_own = part_views(os.path.join(root, body_spec["views"]))

    # 1. the body's place in the photo. Until the scale is known every length is in drawing units
    #    (the body's drawn width = 1), or in metres when the order gives the body's real width
    sub = {vw: locate_by_subtraction(asm[vw], body_own[vw]) for vw in (
        "front", "right", "left") if vw in asm and vw in body_own}
    fm_, _ = silhouette(asm["front"])
    sk = "right" if "right" in sub else "left"
    sm_, _ = silhouette(asm[sk])
    bu0, bu1, bv0, bv1 = sub["front"][0]
    px = (given or 1.0) / ((bu1 - bu0) * fm_.shape[1])
    W, H = fm_.shape[1] * px, fm_.shape[0] * px
    D = sm_.shape[1] * H / sm_.shape[0]
    # [W, H, D] printed on the sheet's own dimension drawing
    dims = order.get("sheet_dims_mm")
    if dims and given:
        # the drawn side views can disagree with the sheet's printed size (drawn too narrow): the print wins
        rep["depth_from"] = "sheet dimensions: depth %.0f mm, height %.0f mm (the views implied %.0f and %.0f mm)" % (
            dims[2], dims[1], D * 1000, H * 1000)
        D, H = dims[2] / 1000.0, dims[1] / 1000.0
    sides = []
    for vw in ("right", "left"):
        if vw in sub:
            u0, u1 = sub[vw][0][:2]
            sides.append((u0, u1) if vw == "right" else (1 - u1, 1 - u0))
    body_box = [bu0 * W - W / 2, bu1 * W - W / 2, float(np.median([s[0] for s in sides])) * D - D / 2,
                float(np.median([s[1] for s in sides])) * D - D / 2, (1 - bv1) * H, (1 - bv0) * H]
    if bu1 - bu0 > ENVELOPE and bv1 - bv0 > ENVELOPE:
        # the body fills the whole front: it is the object's envelope (a cabinet), so it is as deep as the
        # whole object; its own side drawings can be drawn thin
        body_box[2], body_box[3] = -D / 2, D / 2
        rep["body_depth"] = "the whole object's depth (the body fills the front)"

    def to_world_front(frac):
        u0, u1, v0, v1 = frac
        return u0 * W - W / 2, u1 * W - W / 2, (1 - v1) * H, (1 - v0) * H

    built, boxes, placed_order = {}, {"body": body_box}, []
    # (part, paint views) painted after decimation
    pending = []

    # the body: its own views, a top view only carves if it agrees with them (else paint only)
    if "top" in body_views and "top" in asm:
        q, note = orient_like(
            body_views["top"], asm["top"], os.path.join(tmp, "body_top.png"))
        if note:
            body_views["top"] = q
            rep["body_top"] = note
    bx0, bx1, by0, by1, bz0, bz1 = body_box
    paint_only = ()
    if "top" in body_views:
        tm_, _ = silhouette(body_views["top"])
        got, want = tm_.shape[0] / tm_.shape[1], (by1 - by0) / (bx1 - bx0)
        weak = rep.get("body_top") and float(
            rep["body_top"].split("IoU ")[1].split(" ")[0]) < 0.85
        if abs(got / want - 1) > 0.15 or weak:
            paint_only = ("top",)
            rep["body_top_paint_only"] = "top view depth/width %.2f vs %.2f" % (
                got, want)
    # (name, spec, views, placement, entry): built once scaled
    todo = []

    residual_n = 0
    for spec in plan:
        if spec.get("root"):
            continue
        name = spec["name"]
        att = spec.get("attach", {})
        parent = att.get("to", "body")
        face = att.get("face", "front")
        loc = spec.get("locate", "attach")
        entry = {"locate": loc, "attach": "%s of %s" % (face, parent)}
        if loc == "leftover":
            # after everything else is placed
            continue
        pv = _views(os.path.join(root, spec["views"]))
        # height / width
        fa = aspect(pv["front"])
        side_key = "right" if "right" in pv else "left" if "left" in pv else None
        da = None
        if side_key:
            sm, _ = silhouette(pv[side_key])
            # depth / height
            da = sm.shape[1] / sm.shape[0]
        P = boxes[parent]
        px0, px1, py0, py1, pz0, pz1 = P
        box = None
        if loc == "residual":
            # the region the body leaves over in the photo; visible edges, hidden ones from proportions
            edges = {"x0": [], "x1": [], "y0": [],
                     "y1": [], "top": [], "bottom": []}
            for vw, (bb, regs, _) in sub.items():
                if residual_n >= len(regs):
                    continue
                u0, u1, v0, v1 = regs[residual_n]["box"]
                hid = set(regs[residual_n]["hidden"])
                lo_k, hi_k, span = (
                    "x0", "x1", W) if vw == "front" else ("y0", "y1", D)
                if vw == "left":
                    u0, u1 = 1 - u1, 1 - u0
                    hid = {{"left": "right", "right": "left"}.get(
                        e, e) for e in hid}
                if "left" not in hid:
                    edges[lo_k].append(u0 * span - span / 2)
                if "right" not in hid:
                    edges[hi_k].append(u1 * span - span / 2)
                if "top" not in hid:
                    edges["top"].append((1 - v0) * H)
                if "bottom" not in hid:
                    edges["bottom"].append((1 - v1) * H)
            residual_n += 1
            z1, z0 = float(np.median(edges["top"])), float(
                max(edges["bottom"]))
            h = z1 - z0
            w = h / fa
            x0 = float(np.median(edges["x0"])) if edges["x0"] else float(
                np.median(edges["x1"])) - w
            x1 = float(np.median(edges["x1"])) if edges["x1"] else x0 + w
            dd = h * da if da else (x1 - x0)
            y0 = float(np.median(edges["y0"])) if edges["y0"] else float(
                np.median(edges["y1"])) - dd
            y1 = float(np.median(edges["y1"])) if edges["y1"] else y0 + dd
            box = [x0, x1, y0, y1, z0, z1]
            entry["located"] = "region the body leaves over in the photo; hidden edges from its own proportions"
        elif loc == "inset":
            # set into the parent's largest opening (drawn in its own front view): sized to the opening, a
            # little larger so its rim hides behind the edge; its face just behind the parent's front
            ppv = _views(os.path.join(root, next(
                p for p in plan if p["name"] == parent)["views"]))
            op = openings(ppv["front"])
            if op:
                u0, u1, v0, v1 = op[0]
                x0, x1 = px0 + u0 * (px1 - px0), px0 + u1 * (px1 - px0)
                z1, z0 = pz1 - v0 * (pz1 - pz0), pz1 - v1 * (pz1 - pz0)
                cx_, cz_, w, h = (x0 + x1) / 2, (z0 + z1) / 2, (x1 - x0) * \
                    INSET_OVERSIZE, (z1 - z0) * INSET_OVERSIZE
                x0, x1, z0, z1 = cx_ - w / 2, cx_ + w / 2, cz_ - h / 2, cz_ + h / 2
                entry["located"] = "set into %s's largest opening (its own front drawing), %.0f x %.0f mm" % (
                    parent, (u1 - u0) * (px1 - px0) * 1000, (v1 - v0) * (pz1 - pz0) * 1000)
            else:
                r = find_part(asm["front"], pv["front"])
                x0, x1, z0, z1 = to_world_front(r["frac"])
                w, h = x1 - x0, z1 - z0
                entry["located"] = "no opening drawn: painting matched into the photo (score %.2f)" % r[
                    "score"]
            dd = h * da if da else 0.06 * max(w, h)
            box = [x0, x1, 0, dd, z0, z1]
        elif loc == "vision":
            # Coordinates generated by image correspondence, in the same physical
            # frame as the assembly views. Manufacturing/seating stay unchanged.
            candidate = spec.get('vision_box')
            if not isinstance(candidate, list) or len(candidate) != 6 or not np.isfinite(candidate).all():
                raise ValueError(name + ': invalid visual measurement box')
            x0, x1, y0, y1, z0, z1 = map(float, candidate)
            if min(x1 - x0, y1 - y0, z1 - z0) <= 0:
                raise ValueError(name + ': degenerate visual measurement box')
            box = [x0, x1, y0, y1, z0, z1]
            entry['located'] = 'automatic visual correspondence in the assembly reference'
        elif loc == "match":
            r = find_part(asm["front"], pv["front"])
            x0, x1, z0, z1 = to_world_front(r["frac"])
            w, h = x1 - x0, z1 - z0
            dd = h * da if da else 0.06 * max(w, h)
            box = [x0, x1, 0, dd, z0, z1]
            entry["located"] = "painting matched into the photo (score %.2f, scale %.2f)" % (
                r["score"], r["scale"])
        elif loc == "concentric":
            ppv = _views(os.path.join(root, next(
                p for p in plan if p["name"] == parent)["views"]))
            pfm, _ = silhouette(ppv["front"])
            ofm, _ = silhouette(pv["front"])
            ratio = ofm.shape[1] / pfm.shape[1]
            w = (px1 - px0) * ratio
            h = w * fa
            cx, cz = (px0 + px1) / 2, (pz0 + pz1) / 2
            dd = h * da if da else 0.06 * max(w, h)
            box = [cx - w / 2, cx + w / 2, 0, dd, cz - h / 2, cz + h / 2]
            entry["located"] = "centred on %s; %.2f of its width from the sheet's drawing scale" % (
                parent, ratio)
        elif loc == "protrusion":
            ppv = _views(os.path.join(root, next(
                p for p in plan if p["name"] == parent)["views"]))
            pm, _ = silhouette(ppv["front"])
            widths = pm.sum(1)
            full = np.median(widths[widths > 0])
            rows = np.nonzero((widths > 0) & (widths < 0.7 * full))[0]
            rows = rows[rows < 0.3 * pm.shape[0]
                        ] if face == "top" else rows[rows > 0.7 * pm.shape[0]]
            band = np.zeros_like(pm)
            band[rows] = pm[rows]
            ys_, xs_ = np.nonzero(band)
            pw_ = pm.shape[1]
            x0 = px0 + xs_.min() / pw_ * (px1 - px0)
            x1 = px0 + (xs_.max() + 1) / pw_ * (px1 - px0)
            w = x1 - x0
            h = w * fa
            dd = h * da if da else 0.3 * w
            z1 = pz1 if face == "top" else pz0 + h
            box = [x0, x1, 0, dd, z1 - h, z1]
            entry["located"] = "the protrusion on %s's own %s outline" % (
                parent, face)
        else:                                                    # attach by rule, sized to the face
            if face in ("front", "back"):
                fw_, fh_ = px1 - px0, pz1 - pz0
                if att.get("fit") == "inside":
                    s = min(fw_ / 1.0, fh_ / fa)
                    w, h = s * 0.97, s * fa * 0.97
                else:
                    w, h = fw_, fw_ * fa
                dd = h * da if da else 0.03 * max(w, h)
                cx, cz = (px0 + px1) / 2, (pz0 + pz1) / 2
                box = [cx - w / 2, cx + w / 2, 0, dd, cz - h / 2, cz + h / 2]
            elif face in ("left", "right"):
                # a cap on the parent's side face at one end: diameter = the parent's depth there
                w = py1 - py0
                entry["size_from"] = "the parent's depth"
                h = w * fa
                dd = h * da if da else 0.3 * w
                zc = pz1 - h / 2 - 0.02 * \
                    (pz1 - pz0) if att.get("at") == "top" else pz0 + \
                    h / 2 + 0.02 * (pz1 - pz0)
                box = ["side", face, (py0 + py1) / 2, zc, w, dd, h]
            entry["located"] = "on %s's %s face%s" % (
                parent, face, (" at the " + att["at"]) if att.get("at") else "")
        if box is None:
            rep["parts"][name] = dict(entry, skipped="could not be located")
            continue
        if box[0] == "side":
            # built facing front, then turned so its front faces out of the parent's side face
            _, face_, yc, zc, w, dd, h = box
            xside = px1 + dd / 2 if face_ == "right" else px0 - dd / 2
            boxes[name] = [xside - dd / 2, xside + dd / 2,
                           yc - w / 2, yc + w / 2, zc - h / 2, zc + h / 2]
            todo.append((name, spec, pv, ("side", face_), entry))
        else:
            x0, x1, y0, y1, z0, z1 = box
            dd = y1 - y0
            # depth placement by face: in front of / behind the parent; others keep their measured depth
            if loc == "inset":
                back = INSET_BEHIND * (py1 - py0)
                y0, y1 = py0 + back, py0 + back + dd
            elif face == "front":
                y0, y1 = py0 - dd, py0
            elif face == "back":
                # behind the parent (the body box is the bare shell)
                y0, y1 = py1, py1 + dd
            elif loc in ("protrusion", "match", "concentric") and face == "top":
                y0, y1 = py0, py0 + dd                         # at the parent's front edge
            boxes[name] = [x0, x1, y0, y1, z0, z1]
            todo.append((name, spec, pv, ("box", face), entry))
        placed_order.append((name, parent, face))

    # the scale: from the human body (the handbook's contacts measured in the drawing), cross-checked
    if not given:
        from . import human_scale as HS
        anchors, unmeasured = [], []
        for c in contacts:
            v = contact_measure(c, boxes, (W, D, H), plan, root, todo)
            if v:
                anchors.append(HS.anchor(c, v))
            else:
                unmeasured.append("%s %s" % (c["part"], c["measure"]))
        k, srep = HS.solve(anchors)
        srep["unmeasured"] = unmeasured
        W, D, H, px = W * k, D * k, H * k, px * k
        body_box = [v * k for v in body_box]
        boxes = {n: [v * k for v in b] for n, b in boxes.items()}
        # reported, never written back into the order: a rebuild solves the scale again
        srep["body_width_mm"] = round((body_box[1] - body_box[0]) * 1000, 1)
        rep["scale"] = srep
        rep["size_from"] = "human scale (%d of %d contacts agree); photo %.3f x %.3f x %.3f m" % (
            srep["agreeing"], srep["of"], W, D, H)
    else:
        rep["size_from"] = "body width %.3f m given; photo %.3f x %.3f x %.3f m" % (
            given, W, D, H)
    rep["photo_m"] = [round(W, 4), round(D, 4), round(H, 4)]

    # build: the body, then every part at its place
    bx0, bx1, by0, by1, bz0, bz1 = body_box
    rhook = None
    if body_spec.get("recess") and "front" in body_views:
        # openings in the body's own front drawing are recessed (default: RECESS_SHARE of its depth)
        rrep = rep.setdefault("recess", {})
        rd = body_spec["recess"].get("depth_m") if isinstance(
            body_spec["recess"], dict) else None
        rhook = recess_hook(body_views["front"],
                            rd or RECESS_SHARE * (by1 - by0), rrep)
    field_options = {}
    if order.get('automatic_depth'):
        exclusions = []
        for spec in plan:
            if spec.get('attach', {}).get('to') == 'body' and spec.get('attach', {}).get('face') == 'front' and spec['name'] in boxes:
                a, b, _, _, c, d = boxes[spec['name']]
                exclusions.append(('front', [(a - bx0) / (bx1 - bx0), (bz1 - d) / (bz1 - bz0),
                                             (b - bx0) / (bx1 - bx0), (bz1 - c) / (bz1 - bz0)]))
        from . import surface_detail
        report = rep.setdefault('surface_details', {}).setdefault('body', {})
        body_surface_plan = surface_detail.analyse(
            body_views, (bx1 - bx0, by1 - by0, bz1 - bz0), report, exclusions)
        body_surface_plan['cad_export'] = bool(order.get('cad_export'))
        body_surface_plan['diagnostic_folder'] = os.path.join(tmp, 'body_surface')
        field_options = {'field_hook': lambda field: surface_detail.apply_field(field, body_surface_plan),
                         'mesh_hook': lambda obj: surface_detail.capture_high(obj, body_surface_plan),
                         'smooth_iters': 0, 'decimate': 1.}
    body = hull_prop(body_views, bz1 - bz0, res=order.get("res", 150), name=order["name"] + "_body",
                     width_m=bx1 - bx0, depth_m=by1 - by0, features=False, paint=False, rough=order.get("rough", 0.5),
                     paint_only=paint_only, voxel_hook=rhook, **field_options)
    body.location = ((bx0 + bx1) / 2, (by0 + by1) / 2, bz0)
    built["body"] = body
    rep["parts"]["body"] = {"box_m": [
        round(v, 3) for v in body_box], "located": "body outline fitted into the photo"}
    for name, spec, pv, (how, face_), entry in todo:
        x0, x1, y0, y1, z0, z1 = boxes[name]
        if how == "side":
            w, dd, h = y1 - y0, x1 - x0, z1 - z0
        else:
            w, dd, h = x1 - x0, y1 - y0, z1 - z0
        obj, notes, rev = build_part(pv, w, dd, h, "%s_%s" % (
            order["name"], name), tmp, rough=order.get("rough", 0.5), defer=pending,
            automatic_depth=bool(order.get('automatic_depth')), cad_export=bool(order.get('cad_export')))
        obj["finish"] = list(finish_of(name, spec)[:2])
        if how == "side":
            obj.rotation_euler = (
                0, 0, np.pi / 2 if face_ == "right" else -np.pi / 2)
            obj.location = ((x0 + x1) / 2, (y0 + y1) / 2, z0)
        else:
            if face_ == "back":
                # its drawn front faces out, away from the parent
                obj.rotation_euler = (0, 0, np.pi)
            obj.location = ((x0 + x1) / 2, (y0 + y1) / 2, z0)
        bpy.context.view_layer.update()
        built[name] = obj
        entry.update(box_m=[round(v, 3) for v in boxes[name]], notes=notes,
                     lathe=(rev or {}).get("axis") if (rev or {}).get("round") else None)
        rep["parts"][name] = entry

    # 2. leftovers: what the photo shows that no part explains, built from those regions
    for spec in plan:
        if spec.get("locate") != "leftover":
            continue
        name = spec["name"]
        parent = spec.get("attach", {}).get("to", "body")
        regions = {}
        for vw in ("front", sk):
            m, img = silhouette(asm[vw])
            hh, ww = m.shape
            span = W if vw == "front" else D
            explained = np.zeros_like(m)
            for o in built.values():
                co = np.array([o.matrix_world @ v.co for v in o.data.vertices])
                us = (co[:, 0] + W / 2) / W if vw == "front" else ((co[:, 1] +
                                                                    D / 2) / D if vw == "right" else 1 - (co[:, 1] + D / 2) / D)
                vs = 1 - co[:, 2] / H
                xi = np.clip((us * ww).astype(int), 0, ww - 1)
                yi = np.clip((vs * hh).astype(int), 0, hh - 1)
                hit = np.zeros_like(m)
                hit[yi, xi] = True
                explained |= ndimage.binary_closing(
                    ndimage.binary_dilation(hit, iterations=2), iterations=3)
            rest = ndimage.binary_opening(m & ~ndimage.binary_dilation(
                explained, iterations=2), iterations=1)
            lab, k = ndimage.label(rest)
            if not k:
                continue
            sizes = ndimage.sum(rest, lab, range(1, k + 1))
            big = lab == (1 + int(np.argmax(sizes)))
            if big.sum() < 0.004 * m.sum():
                continue
            regions[vw] = (big, img)
        if "front" not in regions or sk not in regions:
            rep["parts"][name] = {
                "locate": "leftover", "skipped": "nothing left over in the front and side views"}
            continue
        boxes_ = {}
        for vw, (mk, img) in regions.items():
            ys_, xs_ = np.nonzero(mk)
            hh, ww = mk.shape
            boxes_[vw] = (xs_.min() / ww, (xs_.max() + 1) / ww,
                          ys_.min() / hh, (ys_.max() + 1) / hh)
        fu0, fu1, fv0, fv1 = boxes_["front"]
        su0, su1, sv0, sv1 = boxes_[sk]
        if sk == "left":
            su0, su1 = 1 - su1, 1 - su0
        x0, x1 = fu0 * W - W / 2, fu1 * W - W / 2
        y0, y1 = su0 * D - D / 2, su1 * D - D / 2
        z0, z1 = (1 - max(fv1, sv1)) * H, (1 - min(fv0, sv0)) * H
        crops = {}
        for vw, (mk, img) in regions.items():
            ys_, xs_ = np.nonzero(mk)
            sl = (slice(ys_.min(), ys_.max() + 1),
                  slice(xs_.min(), xs_.max() + 1))
            q = os.path.join(tmp, "leftover_%s_%s.png" % (name, vw))
            a = np.asarray(img.convert("RGB")).copy()[sl]
            a[~mk[sl]] = 0
            Image.fromarray(a).save(q)
            crops[vw] = q
        fmk = regions["front"][0]
        fsl = tuple(slice(a_.min(), a_.max() + 1) for a_ in np.nonzero(fmk))
        smk = regions[sk][0]
        ssl = tuple(slice(a_.min(), a_.max() + 1) for a_ in np.nonzero(smk))
        fcrop, scrop = np.ascontiguousarray(
            fmk[fsl]), np.ascontiguousarray(smk[ssl])
        from skimage.morphology import skeletonize
        sk_len = int(skeletonize(fcrop).sum())
        width = 2 * float(np.median(ndimage.distance_transform_edt(fcrop)
                          [skeletonize(fcrop)])) if sk_len else 1
        notes = []
        obj = None
        notes.append("leftover region %.1f widths long" %
                     (sk_len / max(width, 1e-6)))
        hpart = HB.part(hb, name, kind_of(spec))
        if hpart.get("make") == "cord":
            # a cord: straight first, then curled along the path the photo shows (propkit/cord.py)
            from .cord import make_cord
            from . import mats
            P, _ = centreline(
                fcrop, scrop, [x0, x1, y0, y1, z0, z1], side_is_left=(sk == "left"))
            # coil thickness: the drawn cord's width at the photo's scale, kept within what the body says
            # a cord like this is (a finger's thickness); wire and pitch as shares of it
            coil = width * (x1 - x0) / max(fcrop.shape[1], 1)
            coil_from = "drawn %.1f mm" % (coil * 1000)
            if hpart.get("coil_outer"):
                from . import human_scale as HS
                ok, (lo_, hi_) = HS.check(hpart["coil_outer"], coil)
                if not ok:
                    # the drawn width is not a cord's (loops of the coil merge in the drawing): the body's
                    # typical size, not the edge of its range
                    coil = HS.size_range(hpart["coil_outer"])[1]
                    coil_from += ", outside the human range %s-%s mm: typical %.1f mm" % (
                        lo_, hi_, coil * 1000)
                else:
                    coil_from += " (human range %s-%s mm)" % (lo_, hi_)
            wire = coil * hpart.get("wire_share_of_coil", 0.33)
            pitch = wire * hpart.get("pitch_share_of_wire", 1.0)
            if P is not None:
                obj, crep = make_cord(
                    P, wire, coil, pitch, "%s_%s" % (order["name"], name))
                fimg = np.asarray(regions["front"][1].convert("RGB"))[
                    fmk].astype(float)
                if len(fimg):
                    # the coils, not the dark gaps between them
                    lum = fimg.sum(1)
                    fimg = fimg[lum >= np.percentile(lum, 50)]
                col = tuple(float(c) / 255 for c in np.median(fimg,
                            axis=0)) if len(fimg) else (0.6, 0.5, 0.3)
                # sRGB painting -> linear material
                col = tuple(c ** 2.2 for c in col)
                rough_, metal_, _ = finish_of(name, spec)
                obj.data.materials.append(mats.plain(col, rough=rough_, metal_v=metal_, grime=0.1, dust=0.03,
                                                     name="cord_%s" % order["name"]))
                obj["procedural"] = True
                notes.append("cord: built straight, curled along the photo's path; %s; coil %s" % (
                    crep, coil_from))
                obj.location = ((x0 + x1) / 2, (y0 + y1) / 2, z0)
                bpy.context.view_layer.update()
                built[name] = obj
                boxes[name] = [x0, x1, y0, y1, z0, z1]
                placed_order.append((name, parent, spec.get(
                    "attach", {}).get("face", "bottom")))
                rep["parts"][name] = {"locate": "leftover", "make": "cord", "box_m": [round(v, 3) for v in boxes[name]],
                                      "located": "what the photo shows that no part explains", "notes": notes}
                continue
        if sk_len > ELONGATED * width:
            # elongated (a cord): a tube swept along its centreline
            obj, rad = sweep_tube(fcrop, scrop, [x0, x1, y0, y1, z0, z1], "%s_%s" % (order["name"], name),
                                  side_is_left=(sk == "left"))
            if obj is not None:
                notes.append("swept along its centreline (length %.1f widths), radius %.1f mm" % (
                    sk_len / width, rad * 1000))
                pending.append((obj, (crops, x1 - x0, y1 - y0, z1 - z0)))
        if obj is None:
            obj, notes, rev = build_part(crops, x1 - x0, y1 - y0, z1 - z0, "%s_%s" % (order["name"], name), tmp,
                                         rough=order.get("rough", 0.5), defer=pending,
                                         automatic_depth=bool(order.get('automatic_depth')))
        obj.location = ((x0 + x1) / 2, (y0 + y1) / 2, z0)
        bpy.context.view_layer.update()
        built[name] = obj
        boxes[name] = [x0, x1, y0, y1, z0, z1]
        placed_order.append((name, parent, spec.get(
            "attach", {}).get("face", "bottom")))
        rep["parts"][name] = {"locate": "leftover", "box_m": [round(v, 3) for v in boxes[name]],
                              "located": "what the photo shows that no part explains", "notes": notes}

    # 3. seat every part on its parent along the face it attaches to, and check it
    def tree(o):
        o.data.update()
        return BVHTree.FromPolygons([o.matrix_world @ v.co for v in o.data.vertices], [p.vertices for p in o.data.polygons])

    def gaps(o, t, dv):
        m3 = o.matrix_world.to_3x3()
        out = []
        for v in o.data.vertices:
            n_ = (m3 @ v.normal).normalized()
            if n_.dot(dv) < 0.5:
                continue
            p_ = o.matrix_world @ v.co
            hn = t.find_nearest(p_)
            if hn[0] is not None and (hn[0] - p_).dot(hn[1]) > 0:
                out.append(0.0)
                continue
            hit = t.ray_cast(p_ + dv * 1e-4, dv, SUPPORT_REACH)
            out.append(None if hit[0] is None else hit[3])
        hits = [x for x in out if x is not None]
        if not out or len(hits) < 0.15 * len(out) or not hits:
            return None, 0.0
        p10 = float(np.percentile(hits, 10))
        near = [x for x in hits if x <= p10 + NEAR_LAYER]
        return p10, sum(1 for x in near if x <= max(MAX_GAP, p10 + 1e-6)) / max(1, len(near))

    # the triangle budget is shared out and each part decimated to its share BEFORE it is painted:
    # decimating the painted assembly afterwards (1-2% of the dense meshes) collapses faces across the
    # projected texture and stretches it into streaks
    from .bake import STANDARDS
    from .core import apply_mods
    dims = max(W, D, H)
    budget = next(v["tri_budget"] for k, v in STANDARDS["size_classes"].items(
    ) if dims <= v["max_dim_m"]) * 0.92
    # shared by each part's dense triangle count (its detail: a finger wheel's holes, a handset's
    # curves), as one uniform decimation of the whole would, never below PART_MIN_TRIS; by area alone a
    # small detailed part got too few and shattered into slivers that shade as dark streaks
    fixed = {n: sum(len(p_.vertices) - 2 for p_ in o.data.polygons)
             for n, o in built.items() if o.get("procedural")}
    budget -= sum(fixed.values())
    mode = order.get("budget", "screen")
    if mode not in ("screen", "share"):
        raise ValueError("Unknown reduction policy: " + str(mode))
    tol = screen_tolerance(STANDARDS, order.get("kind", "fixture" if order.get(
        "mount") == "wall" else "static")) if mode == "screen" else None
    if mode == 'screen' and (tol is None or not np.isfinite(tol) or tol <= 0):
        raise ValueError('Screen reduction requires a positive finite error budget')
    dense = {n: sum(len(p_.vertices) - 2 for p_ in o.data.polygons)
             for n, o in built.items() if not o.get("procedural")}
    total = sum(dense.values())
    rep["triangles"] = dict(fixed)
    if tol:
        from . import surface_detail
        import json
        protected = {}
        for name, obj in built.items():
            report = rep.setdefault('surface_details', {}).get(name)
            if report is None and obj.get('surface_detail_report'):
                report = json.loads(obj['surface_detail_report'])
                rep['surface_details'][name] = report
            protected[name] = surface_detail.protected_samples(
                obj, report, geometry_tolerance=tol) if report else None
            obj['protected_surface_features'] = protected[name] is not None
        # The ceiling must never silently increase the allowed surface error.
        rep["budget"] = {"mode": "screen error", "tolerance_mm": round(
            tol * 1000, 2), "ceiling": int(budget + sum(fixed.values()))}
        got = {}
        for n, o in built.items():
            if o.get("procedural"):
                continue
            got[n] = decimate_to_error(o, tol, PART_MIN_TRIS, protected=protected.get(n))
            o['bounded_surface_error'] = True
        rep["budget"]["tolerance_used_mm"] = round(tol * 1000, 2)
        rep["budget"]["ceiling_conflict"] = sum(t for t, _ in got.values()) > budget
        rep["budget"]["error_mm"] = {
            n: round(e * 1000, 2) for n, (t, e) in got.items()}
        rep["triangles"].update({n: t for n, (t, e) in got.items()})
    for n, o in built.items():
        if o.get("procedural") or tol:
            continue
        tris = dense[n]
        target = max(PART_MIN_TRIS, int(budget * tris / total))
        if tris > target:
            m_ = o.modifiers.new("share", "DECIMATE")
            m_.ratio = target / tris
            apply_mods(o)
        rep["triangles"][n] = sum(
            len(p_.vertices) - 2 for p_ in o.data.polygons)
    if order.get('vision_generated') or order.get('automatic_depth'):
        from .simplification import refresh_normals
        for obj in built.values():
            refresh_normals(obj, planar=True)
    for o, (views_, w_, d_, h_) in pending:
        loc, rot = o.location.copy(), o.rotation_euler.copy()
        o.location, o.rotation_euler = (0, 0, 0), (0, 0, 0)
        bpy.context.view_layer.update()
        rough_, metal_ = o.get("finish", [order.get("rough", 0.5), 0.0])
        texturing.project(o, paint_views(views_, tmp, "p_" + o.name), w_, d_, h_, others=[], name=o.name,
                          rough=float(rough_), metal=float(metal_))
        o.location, o.rotation_euler = loc, rot
    bpy.context.view_layer.update()

    # the body is painted last, from the photo, with every part in front of it occluding: what shows
    # of it in the assembled object (a dial's centre card through the finger wheel) is what the photo
    # shows there; its own drawings show the bare shell
    bpy.context.view_layer.update()
    b_rough, b_metal, _ = finish_of("body")
    texturing.project(body, paint_views({k: v for k, v in asm.items() if k in ("front", "back", "left", "right", "top")},
                                        tmp, "p_body_photo"), W, D, H,
                      others=[o for n, o in built.items() if n != "body"], name=body.name, rough=b_rough, metal=b_metal)
    children = {}
    for name, parent, face in placed_order:
        children.setdefault(parent, []).append(name)

    def descendants(n):
        out = []
        for c in children.get(n, []):
            out += [c] + descendants(c)
        return out

    rep["gaps_mm"] = []
    insets = {sp["name"] for sp in plan if sp.get("locate") == "inset"}
    for name, parent, face in placed_order:
        if name in insets:
            rep["gaps_mm"].append(
                {"part": name, "on": parent, "towards": face, "held": "set into the opening"})
            continue
        o, t = built[name], tree(built[parent])
        dv = Vector(INTO[face])
        g, _ = gaps(o, t, dv)
        if g is not None:
            delta = dv * (g + SNAP_SINK)
            # what is attached to it moves with it
            for n in [name] + descendants(name):
                built[n].location += delta
            bpy.context.view_layer.update()
        g2, touch = gaps(o, t, dv)
        rep["gaps_mm"].append({"part": name, "on": parent, "towards": face, "gap_mm": None if g2 is None else round(g2 * 1000, 1),
                               "touching": round(touch, 2), "moved_mm": None if g is None else round((g + SNAP_SINK) * 1000, 1)})
    bad = [g for g in rep["gaps_mm"] if "held" not in g and g["gap_mm"]
           is None or "held" not in g and (g["gap_mm"] > MAX_GAP * 1000 or g["touching"] < MIN_TOUCH)]
    if bad:
        import json
        print("PARTS report", json.dumps(rep, default=str))
        raise RuntimeError("parts not seated: " + "; ".join("%s on %s (%s): gap %s mm, touching %s" % (
            g["part"], g["on"], g["towards"], g["gap_mm"], g["touching"]) for g in bad))
    for name, report in rep.get('surface_details', {}).items():
        report['physical_owner'] = built[name].get(
            'physical_region_id', built[name].name)
        report['matrix_world'] = [list(row)
                                  for row in built[name].matrix_world]
    for obj in built.values():
        high = bpy.data.objects.get(obj.get('dense_source_name', ''))
        if high:
            high.matrix_world = obj.matrix_world.copy()
    return rep
