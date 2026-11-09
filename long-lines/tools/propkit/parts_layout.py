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
  root        the body's own outline fitted into the photo (hull_assembly.match_into); one real size
              (body_width_m) scales the drawing
  residual    the part sticks out of the body's outline: the region the body leaves over in the photo,
              each box edge from a view where it is visible (hull_assembly.locate_by_subtraction)
  match       the part lies on the body: its painting matched into the photo (propkit.locate)
  concentric  centred on its parent; size from the sheet's drawing scale relative to the parent's own
              drawing (low confidence, reported)
  protrusion  drawn as part of the parent's own view, sticking out of its outline (cradle hooks on a
              shell's top edge): position and size from that protrusion
  attach      on the parent's face ("at": top / bottom / centre), sized to fit that face
  leftover    whatever the photo shows that no part explains (a coiled cord): a hull of those regions,
              painted from the photo
Then every part is seated on its parent along the face it attaches to and gap-checked.
"""
import os

import numpy as np
from PIL import Image
from scipy import ndimage

from . import texturing
from .hull import HULL_REPORT, hull_prop, silhouette
from .hull_assembly import (MAX_GAP, MIN_TOUCH, NEAR_LAYER, SNAP_SINK, SUPPORT_REACH, aspect, locate_by_subtraction,
                            orient_like, paint_views, part_views)
from .locate import find_part

PART_MIN_TRIS = 300   # no part decimated below this
ELONGATED = 3.0     # a leftover whose centreline is this many widths long is swept as a tube
INTO = {"front": (0, 1, 0), "back": (0, -1, 0), "top": (0, 0, -1), "bottom": (0, 0, 1),
        "left": (1, 0, 0), "right": (-1, 0, 0)}          # direction from a part on that face into its parent


def _views(folder):
    return {k: p for k, p in part_views(folder).items() if k in ("front", "back", "left", "right", "top")}


def _holes(path, box):
    hp = os.path.join(os.path.dirname(path), "h_%s.png" % os.path.basename(path)[2:-4])
    if not os.path.exists(hp):
        return None
    h = np.asarray(Image.open(hp).convert("L").crop(box)) > 127
    return h if h.any() else None


def build_part(views, w, d, h, name, tmp, res=110, rough=0.5, cut_holes=True, defer=None):
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
                sil["back"] = (sil["back"][0] & ~holes[:, ::-1], sil["back"][1])
            notes.append("%d px of background seen through its front view cut through" % int(holes.sum()))
    obj = hull_prop(views, h, res=res, name=name, width_m=w, depth_m=d, features=False, paint=False, rough=rough,
                    sil_override=sil)
    rev = HULL_REPORT.get("revolve")
    paint = ({k: v for k, v in views.items() if not v.endswith("_side.png")}, w, d, h)
    if defer is not None:
        defer.append((obj, paint))           # painted once its final topology is known (paint_deferred)
    else:
        texturing.project(obj, paint_views(paint[0], tmp, "p_" + name), w, d, h, others=[], name=obj.name, rough=rough)
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


def sweep_tube(front, side, box, name, side_is_left=False, segments=10):
    """A tube swept along an elongated region's centreline (a coiled cord): the front view's skeleton
    gives x and z, the side view's region gives y at each height, the radius is the region's half width.
    Built in the part's own frame (x, y centred, z from 0) like hull_prop's parts."""
    import bmesh
    import bpy
    from skimage.morphology import skeletonize
    from .core import link
    x0, x1, y0, y1, z0, z1 = box
    w, d, h = x1 - x0, y1 - y0, z1 - z0
    hh, ww = front.shape
    path = _longest_path(skeletonize(front))
    r_px = float(np.median(ndimage.distance_transform_edt(front)[tuple(np.array(path).T)])) if path else 1.0
    r = r_px / ww * w
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
        return None, r
    P = np.array(pts)
    P = np.vstack([ndimage.gaussian_filter1d(P[:, i], 1.5, mode="nearest") for i in range(3)]).T
    bm = bmesh.new()
    rings = []
    for i, p_ in enumerate(P):
        t = P[min(i + 1, len(P) - 1)] - P[max(i - 1, 0)]
        t /= max(np.linalg.norm(t), 1e-9)
        a = np.cross(t, [0, 1, 0]) if abs(t[1]) < 0.9 else np.cross(t, [1, 0, 0])
        a /= np.linalg.norm(a)
        b = np.cross(t, a)
        rings.append([bm.verts.new(tuple(p_ + r * (np.cos(k * 2 * np.pi / segments) * a + np.sin(k * 2 * np.pi / segments) * b)))
                      for k in range(segments)])
    for ra, rb in zip(rings[:-1], rings[1:]):
        for k in range(segments):
            bm.faces.new((ra[k], ra[(k + 1) % segments], rb[(k + 1) % segments], rb[k]))
    for ring, flip in ((rings[0], True), (rings[-1], False)):
        f = bm.faces.new(ring[::-1] if flip else ring)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    obj = link(bpy.data.objects.new(name, me))
    return obj, r


def build_parts(order, src_root):
    import bpy
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    root = os.path.join(src_root, order["views_folder"])
    tmp = os.path.join("/tmp", "_parts_" + order["name"])
    os.makedirs(tmp, exist_ok=True)
    rep = {"layout": "parts", "parts": {}}
    asm = part_views(os.path.join(root, order["assembly"]))
    plan = order["parts"]
    body_spec = next(p for p in plan if p.get("root"))
    body_views = _views(os.path.join(root, body_spec["views"]))
    body_own = part_views(os.path.join(root, body_spec["views"]))

    # 1. the body's place in the photo, and the photo's scale from one real size
    sub = {vw: locate_by_subtraction(asm[vw], body_own[vw]) for vw in ("front", "right", "left") if vw in asm and vw in body_own}
    fm_, _ = silhouette(asm["front"])
    sk = "right" if "right" in sub else "left"
    sm_, _ = silhouette(asm[sk])
    bu0, bu1, bv0, bv1 = sub["front"][0]
    px = order["body_width_m"] / ((bu1 - bu0) * fm_.shape[1])
    W, H = fm_.shape[1] * px, fm_.shape[0] * px
    D = sm_.shape[1] * H / sm_.shape[0]
    rep["size_from"] = "body width %.3f m; photo %.3f x %.3f x %.3f m" % (order["body_width_m"], W, D, H)
    sides = []
    for vw in ("right", "left"):
        if vw in sub:
            u0, u1 = sub[vw][0][:2]
            sides.append((u0, u1) if vw == "right" else (1 - u1, 1 - u0))
    body_box = [bu0 * W - W / 2, bu1 * W - W / 2, float(np.median([s[0] for s in sides])) * D - D / 2,
                float(np.median([s[1] for s in sides])) * D - D / 2, (1 - bv1) * H, (1 - bv0) * H]

    def to_world_front(frac):
        u0, u1, v0, v1 = frac
        return u0 * W - W / 2, u1 * W - W / 2, (1 - v1) * H, (1 - v0) * H

    built, boxes, placed_order = {}, {"body": body_box}, []
    pending = []                                                 # (part, paint views) painted after decimation

    # the body: its own views, a top view only carves if it agrees with them (else paint only)
    if "top" in body_views and "top" in asm:
        q, note = orient_like(body_views["top"], asm["top"], os.path.join(tmp, "body_top.png"))
        if note:
            body_views["top"] = q
            rep["body_top"] = note
    bx0, bx1, by0, by1, bz0, bz1 = body_box
    paint_only = ()
    if "top" in body_views:
        tm_, _ = silhouette(body_views["top"])
        got, want = tm_.shape[0] / tm_.shape[1], (by1 - by0) / (bx1 - bx0)
        weak = rep.get("body_top") and float(rep["body_top"].split("IoU ")[1].split(" ")[0]) < 0.85
        if abs(got / want - 1) > 0.15 or weak:
            paint_only = ("top",)
            rep["body_top_paint_only"] = "top view depth/width %.2f vs %.2f" % (got, want)
    body = hull_prop(body_views, bz1 - bz0, res=order.get("res", 150), name=order["name"] + "_body",
                     width_m=bx1 - bx0, depth_m=by1 - by0, features=False, paint=False, rough=order.get("rough", 0.5),
                     paint_only=paint_only)
    body.location = ((bx0 + bx1) / 2, (by0 + by1) / 2, bz0)
    built["body"] = body
    rep["parts"]["body"] = {"box_m": [round(v, 3) for v in body_box], "located": "body outline fitted into the photo"}

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
            continue                                             # after everything else is placed
        pv = _views(os.path.join(root, spec["views"]))
        fa = aspect(pv["front"])                                 # height / width
        side_key = "right" if "right" in pv else "left" if "left" in pv else None
        da = None
        if side_key:
            sm, _ = silhouette(pv[side_key])
            da = sm.shape[1] / sm.shape[0]                       # depth / height
        P = boxes[parent]
        px0, px1, py0, py1, pz0, pz1 = P
        box = None
        if loc == "residual":
            # the region the body leaves over in the photo; visible edges, hidden ones from proportions
            edges = {"x0": [], "x1": [], "y0": [], "y1": [], "top": [], "bottom": []}
            for vw, (bb, regs, _) in sub.items():
                if residual_n >= len(regs):
                    continue
                u0, u1, v0, v1 = regs[residual_n]["box"]
                hid = set(regs[residual_n]["hidden"])
                lo_k, hi_k, span = ("x0", "x1", W) if vw == "front" else ("y0", "y1", D)
                if vw == "left":
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
            residual_n += 1
            z1, z0 = float(np.median(edges["top"])), float(max(edges["bottom"]))
            h = z1 - z0
            w = h / fa
            x0 = float(np.median(edges["x0"])) if edges["x0"] else float(np.median(edges["x1"])) - w
            x1 = float(np.median(edges["x1"])) if edges["x1"] else x0 + w
            dd = h * da if da else (x1 - x0)
            y0 = float(np.median(edges["y0"])) if edges["y0"] else float(np.median(edges["y1"])) - dd
            y1 = float(np.median(edges["y1"])) if edges["y1"] else y0 + dd
            box = [x0, x1, y0, y1, z0, z1]
            entry["located"] = "region the body leaves over in the photo; hidden edges from its own proportions"
        elif loc == "match":
            r = find_part(asm["front"], pv["front"])
            x0, x1, z0, z1 = to_world_front(r["frac"])
            w, h = x1 - x0, z1 - z0
            dd = h * da if da else 0.06 * max(w, h)
            box = [x0, x1, 0, dd, z0, z1]
            entry["located"] = "painting matched into the photo (score %.2f, scale %.2f)" % (r["score"], r["scale"])
        elif loc == "concentric":
            ppv = _views(os.path.join(root, next(p for p in plan if p["name"] == parent)["views"]))
            pfm, _ = silhouette(ppv["front"])
            ofm, _ = silhouette(pv["front"])
            ratio = ofm.shape[1] / pfm.shape[1]
            w = (px1 - px0) * ratio
            h = w * fa
            cx, cz = (px0 + px1) / 2, (pz0 + pz1) / 2
            dd = h * da if da else 0.06 * max(w, h)
            box = [cx - w / 2, cx + w / 2, 0, dd, cz - h / 2, cz + h / 2]
            entry["located"] = "centred on %s; %.2f of its width from the sheet's drawing scale (low confidence)" % (parent, ratio)
        elif loc == "protrusion":
            ppv = _views(os.path.join(root, next(p for p in plan if p["name"] == parent)["views"]))
            pm, _ = silhouette(ppv["front"])
            widths = pm.sum(1)
            full = np.median(widths[widths > 0])
            rows = np.nonzero((widths > 0) & (widths < 0.7 * full))[0]
            rows = rows[rows < 0.3 * pm.shape[0]] if face == "top" else rows[rows > 0.7 * pm.shape[0]]
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
            entry["located"] = "the protrusion on %s's own %s outline" % (parent, face)
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
                dpar = py1 - py0
                w = dpar
                h = w * fa
                dd = h * da if da else 0.3 * w
                zc = pz1 - h / 2 - 0.02 * (pz1 - pz0) if att.get("at") == "top" else pz0 + h / 2 + 0.02 * (pz1 - pz0)
                box = ["side", face, (py0 + py1) / 2, zc, w, dd, h]
            entry["located"] = "on %s's %s face%s" % (parent, face, (" at the " + att["at"]) if att.get("at") else "")
        if box is None:
            rep["parts"][name] = dict(entry, skipped="could not be located")
            continue
        if box[0] == "side":
            # built facing front, then turned so its front faces out of the parent's side face
            _, face_, yc, zc, w, dd, h = box
            obj, notes, rev = build_part(pv, w, dd, h, "%s_%s" % (order["name"], name), tmp, rough=order.get("rough", 0.5), defer=pending)
            obj.rotation_euler = (0, 0, np.pi / 2 if face_ == "right" else -np.pi / 2)
            bpy.context.view_layer.update()
            xside = px1 + dd / 2 if face_ == "right" else px0 - dd / 2
            obj.location = (xside, yc, zc - h / 2)
            boxes[name] = [xside - dd / 2, xside + dd / 2, yc - w / 2, yc + w / 2, zc - h / 2, zc + h / 2]
        else:
            x0, x1, y0, y1, z0, z1 = box
            w, dd, h = x1 - x0, y1 - y0, z1 - z0
            # depth placement by face: in front of / behind the parent; others keep their measured depth
            if face == "front":
                y0, y1 = py0 - dd, py0
            elif face == "back":
                y0, y1 = py1 - dd, py1                         # flush with the parent's back (wall side)
            elif loc in ("protrusion", "match", "concentric") and face == "top":
                y0, y1 = py0, py0 + dd                         # at the parent's front edge
            obj, notes, rev = build_part(pv, w, dd, h, "%s_%s" % (order["name"], name), tmp, rough=order.get("rough", 0.5), defer=pending)
            obj.location = ((x0 + x1) / 2, (y0 + y1) / 2, z0)
            boxes[name] = [x0, x1, y0, y1, z0, z1]
        bpy.context.view_layer.update()
        built[name] = obj
        placed_order.append((name, parent, face))
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
                us = (co[:, 0] + W / 2) / W if vw == "front" else ((co[:, 1] + D / 2) / D if vw == "right" else 1 - (co[:, 1] + D / 2) / D)
                vs = 1 - co[:, 2] / H
                xi = np.clip((us * ww).astype(int), 0, ww - 1)
                yi = np.clip((vs * hh).astype(int), 0, hh - 1)
                hit = np.zeros_like(m)
                hit[yi, xi] = True
                explained |= ndimage.binary_closing(ndimage.binary_dilation(hit, iterations=2), iterations=3)
            rest = ndimage.binary_opening(m & ~ndimage.binary_dilation(explained, iterations=2), iterations=1)
            lab, k = ndimage.label(rest)
            if not k:
                continue
            sizes = ndimage.sum(rest, lab, range(1, k + 1))
            big = lab == (1 + int(np.argmax(sizes)))
            if big.sum() < 0.004 * m.sum():
                continue
            regions[vw] = (big, img)
        if "front" not in regions or sk not in regions:
            rep["parts"][name] = {"locate": "leftover", "skipped": "nothing left over in the front and side views"}
            continue
        boxes_ = {}
        for vw, (mk, img) in regions.items():
            ys_, xs_ = np.nonzero(mk)
            hh, ww = mk.shape
            boxes_[vw] = (xs_.min() / ww, (xs_.max() + 1) / ww, ys_.min() / hh, (ys_.max() + 1) / hh)
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
            sl = (slice(ys_.min(), ys_.max() + 1), slice(xs_.min(), xs_.max() + 1))
            q = os.path.join(tmp, "leftover_%s_%s.png" % (name, vw))
            a = np.asarray(img.convert("RGB")).copy()[sl]
            a[~mk[sl]] = 0
            Image.fromarray(a).save(q)
            crops[vw] = q
        fmk = regions["front"][0]
        fsl = tuple(slice(a_.min(), a_.max() + 1) for a_ in np.nonzero(fmk))
        smk = regions[sk][0]
        ssl = tuple(slice(a_.min(), a_.max() + 1) for a_ in np.nonzero(smk))
        fcrop, scrop = np.ascontiguousarray(fmk[fsl]), np.ascontiguousarray(smk[ssl])
        from skimage.morphology import skeletonize
        sk_len = int(skeletonize(fcrop).sum())
        width = 2 * float(np.median(ndimage.distance_transform_edt(fcrop)[skeletonize(fcrop)])) if sk_len else 1
        notes = []
        obj = None
        notes.append("leftover region %.1f widths long" % (sk_len / max(width, 1e-6)))
        if sk_len > ELONGATED * width:
            # elongated (a cord): a tube swept along its centreline
            obj, rad = sweep_tube(fcrop, scrop, [x0, x1, y0, y1, z0, z1], "%s_%s" % (order["name"], name),
                                  side_is_left=(sk == "left"))
            if obj is not None:
                notes.append("swept along its centreline (length %.1f widths), radius %.1f mm" % (sk_len / width, rad * 1000))
                pending.append((obj, (crops, x1 - x0, y1 - y0, z1 - z0)))
        if obj is None:
            obj, notes, rev = build_part(crops, x1 - x0, y1 - y0, z1 - z0, "%s_%s" % (order["name"], name), tmp,
                                         rough=order.get("rough", 0.5), defer=pending)
        obj.location = ((x0 + x1) / 2, (y0 + y1) / 2, z0)
        bpy.context.view_layer.update()
        built[name] = obj
        boxes[name] = [x0, x1, y0, y1, z0, z1]
        placed_order.append((name, parent, spec.get("attach", {}).get("face", "bottom")))
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
    budget = next(v["tri_budget"] for k, v in STANDARDS["size_classes"].items() if dims <= v["max_dim_m"]) * 0.92
    # shared by each part's dense triangle count (its detail: a finger wheel's holes, a handset's
    # curves), as one uniform decimation of the whole would, never below PART_MIN_TRIS; by area alone a
    # small detailed part got too few and shattered into slivers that shade as dark streaks
    dense = {n: sum(len(p_.vertices) - 2 for p_ in o.data.polygons) for n, o in built.items()}
    total = sum(dense.values())
    rep["triangles"] = {}
    for n, o in built.items():
        tris = dense[n]
        target = max(PART_MIN_TRIS, int(budget * tris / total))
        if tris > target:
            m_ = o.modifiers.new("share", "DECIMATE")
            m_.ratio = target / tris
            apply_mods(o)
        rep["triangles"][n] = sum(len(p_.vertices) - 2 for p_ in o.data.polygons)
    for o, (views_, w_, d_, h_) in pending:
        loc, rot = o.location.copy(), o.rotation_euler.copy()
        o.location, o.rotation_euler = (0, 0, 0), (0, 0, 0)
        bpy.context.view_layer.update()
        texturing.project(o, paint_views(views_, tmp, "p_" + o.name), w_, d_, h_, others=[], name=o.name,
                          rough=order.get("rough", 0.5))
        o.location, o.rotation_euler = loc, rot
    bpy.context.view_layer.update()

    # the body is painted last, from the photo, with every part in front of it occluding: what shows
    # of it in the assembled object (a dial's centre card through the finger wheel) is what the photo
    # shows there; its own drawings show the bare shell
    bpy.context.view_layer.update()
    texturing.project(body, paint_views({k: v for k, v in asm.items() if k in ("front", "back", "left", "right", "top")},
                                        tmp, "p_body_photo"), W, D, H,
                      others=[o for n, o in built.items() if n != "body"], name=body.name, rough=order.get("rough", 0.5))
    children = {}
    for name, parent, face in placed_order:
        children.setdefault(parent, []).append(name)

    def descendants(n):
        out = []
        for c in children.get(n, []):
            out += [c] + descendants(c)
        return out

    rep["gaps_mm"] = []
    for name, parent, face in placed_order:
        o, t = built[name], tree(built[parent])
        dv = Vector(INTO[face])
        g, _ = gaps(o, t, dv)
        if g is not None:
            delta = dv * (g + SNAP_SINK)
            for n in [name] + descendants(name):            # what is attached to it moves with it
                built[n].location += delta
            bpy.context.view_layer.update()
        g2, touch = gaps(o, t, dv)
        rep["gaps_mm"].append({"part": name, "on": parent, "towards": face, "gap_mm": None if g2 is None else round(g2 * 1000, 1),
                               "touching": round(touch, 2), "moved_mm": None if g is None else round((g + SNAP_SINK) * 1000, 1)})
    bad = [g for g in rep["gaps_mm"] if g["gap_mm"] is None or g["gap_mm"] > MAX_GAP * 1000 or g["touching"] < MIN_TOUCH]
    if bad:
        import json
        print("PARTS report", json.dumps(rep, default=str))
        raise RuntimeError("parts not seated: " + "; ".join("%s on %s (%s): gap %s mm, touching %s" % (
            g["part"], g["on"], g["towards"], g["gap_mm"], g["touching"]) for g in bad))
    return rep
