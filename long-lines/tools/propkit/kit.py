"""Kit line: an object assembled from components found on a painted parts sheet, without
depth or part maps. Every component carries its support (protocol, factory/VALIDATION.md):
evidence (painted on the sheet), function (sizing manual), convention (sizing manual profiles).

Components in the order:
  {"type": "body",   "front": n, "back": n, "profile": "telephone"}      carved shell
  {"type": "keys",   "view": n, "region": [u0,v0,u1,v1], "kind": "key"}  raised on the body
  {"type": "rest",   "panel": n, "width_mm": 50, "on": "top", "y_frac": 0.4}   a separate part resting on the body
  {"type": "cord",   "colour_panel": n, "from": "rest_left", "to": [x,y,z]}
"""
import json
import math
import os

import numpy as np
from PIL import Image

from .atlas import _crop, panels
from . import sizing


def _mask(png):
    from scipy import ndimage
    a = np.asarray(Image.open(png).convert("RGB")).astype(np.int32)
    m = a.max(-1) > 48
    m = ndimage.binary_fill_holes(ndimage.binary_closing(m, iterations=2))
    lab, n = ndimage.label(m)
    return lab == (np.argmax(np.bincount(lab.ravel())[1:]) + 1)


def _pad_paint(png, mask):
    from scipy import ndimage
    a = np.asarray(Image.open(png).convert("RGB"))
    idx = ndimage.distance_transform_edt(~ndimage.binary_erosion(mask, iterations=1), return_distances=False, return_indices=True)
    Image.fromarray(a[idx[0], idx[1]]).save(png)
    return png


def build(sheet, order, src_dir):
    import bpy
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    from . import core, mats
    from .hull import hull_prop
    os.makedirs(src_dir, exist_ok=True)
    boxes = panels(sheet, min_area=order.get("min_area", 150))
    img = Image.open(sheet).convert("RGB")
    env = sizing.manual()["envelopes"].get(order["category"], {})
    W = order.get("width_m") or sum(env.get("width", [200, 200])) / 2000
    D = order.get("depth_m") or sum(env.get("depth", [200, 200])) / 2000
    H = order.get("height_m") or sum(env.get("height", [120, 120])) / 2000
    report = []
    body = None
    for c in order["components"]:
        if c["type"] == "body":
            sil = {}
            for k in ("front", "back"):
                if k in c:
                    p = _crop(img, boxes[c[k]], src_dir, k, inset=0)
                    m = _mask(p)
                    ys, xs = np.nonzero(m)
                    p2 = os.path.join(src_dir, "v_%s.png" % k)
                    Image.open(p).crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1)).save(p2)
                    m = m[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
                    _pad_paint(p2, m)
                    sil[k] = (m, Image.open(p2))
                    report.append({"part": "body " + k, "support": "evidence", "confidence": "high"})
            prof = sizing.manual()["profiles"][c["profile"]]
            n = 200
            sm = np.zeros((int(n * H / D), n), bool)
            from PIL import ImageDraw
            im = Image.new("L", (n, sm.shape[0]), 0)
            ImageDraw.Draw(im).polygon([(u * (n - 1), v * (sm.shape[0] - 1)) for u, v in prof["points"]], fill=255)
            sm = np.asarray(im) > 127
            sil["right"] = (sm, Image.fromarray(np.full(sm.shape + (3,), np.asarray(sil["front"][1]).reshape(-1, 3).mean(0), np.uint8)))
            sil["left"] = (sm[:, ::-1], sil["right"][1])
            report.append({"part": "side profile", "support": "convention", "confidence": "low",
                           "why": prof["why"]})
            # Conventional (not painted) views get another name, so the gate only checks real views.
            paths = {k: os.path.join(src_dir, ("v_%s.png" if k in ("front", "back") else "conv_%s.png") % k) for k in sil}
            for k in ("right", "left"):
                sil[k][1].save(paths[k])
            body = hull_prop(paths, H, res=120, name=order["name"], features=False, sil_override=sil, depth_m=D,
                             decimate=0.5, grime=0.0)
            W = H * sil["front"][0].shape[1] / sil["front"][0].shape[0]
        elif c["type"] == "keys":
            # Painted keys -> raised keys on the body surface, along the surface normal.
            from scipy import ndimage
            fp = os.path.join(src_dir, "v_front.png")
            g = np.asarray(Image.open(fp).convert("L")).astype(np.float32)
            Hp, Wp = g.shape
            u0, v0, u1, v1 = c["region"]
            sub = g[int(v0 * Hp):int(v1 * Hp), int(u0 * Wp):int(u1 * Wp)]
            bright = sub > ndimage.uniform_filter(sub, size=max(5, sub.shape[1] // 3)) + 4
            lab, nk = ndimage.label(ndimage.binary_opening(bright, iterations=1))
            sizes = np.bincount(lab.ravel())[1:]
            keep = [i + 1 for i, s_ in enumerate(sizes) if s_ >= 0.3 * np.median(sorted(sizes)[-9:])]
            me = body.data
            tree = BVHTree.FromPolygons([body.matrix_world @ v.co for v in me.vertices], [p.vertices for p in me.polygons])
            rule = sizing.catalogue()["out"][c.get("kind", "key")]
            depth = rule["default"] / 1000
            made = 0
            for i in keep:
                ys, xs = np.nonzero(lab == i)
                cu = (u0 * Wp + xs.mean()) / Wp
                cv = (v0 * Hp + ys.mean()) / Hp
                side = max(np.ptp(xs) + 1, np.ptp(ys) + 1) / Wp * W * 0.9
                x, z = (cu - 0.5) * W, (1 - cv) * H
                loc, nor, _, _ = tree.ray_cast(Vector((x, -1.0, z)), Vector((0, 1, 0)), 3)
                if loc is None:
                    continue
                k = core.box((side, side, depth * 2), (0, 0, 0), mats.image(fp, rough=0.4, grime=0.0, name="kit_key"),
                             bevel=side * 0.12, name="key")
                k.rotation_euler = nor.to_track_quat("Z", "Y").to_euler()
                k.location = loc
                bpy.context.view_layer.update()
                attr = k.data.color_attributes.new("label_uv", "FLOAT_COLOR", "CORNER")
                for li, loop in enumerate(k.data.loops):
                    wv = k.matrix_world @ k.data.vertices[loop.vertex_index].co
                    attr.data[li].color = (wv.x / W + 0.5, wv.z / H, 0, 1)
                made += 1
            report.append({"part": "keys x%d" % made, "support": "evidence (painted keypad) + sizing manual depth",
                           "depth_mm": rule["default"], "why": rule["why"], "confidence": "medium"})
        elif c["type"] == "rest":
            # A separate part (handset) from its painted side outline, extruded to a functional width.
            p = _crop(img, boxes[c["panel"]], src_dir, "rest", inset=0)
            m = _mask(p)
            ys, xs = np.nonzero(m)
            m = m[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
            p2 = os.path.join(src_dir, "v_rest.png")
            Image.open(p).crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1)).save(p2)
            _pad_paint(p2, m)
            L = c.get("length_m", W * 1.02)
            h = L * m.shape[0] / m.shape[1]
            wd = c.get("width_mm", 50) / 1000
            from skimage.measure import approximate_polygon, find_contours
            import bmesh
            cc = max(find_contours(np.pad(m, 1).astype(float), 0.5), key=len)
            cc = approximate_polygon(cc, tolerance=0.6)[:-1]
            pts = [((x_ - 1) / m.shape[1] * L - L / 2, h - (y_ - 1) / m.shape[0] * h) for y_, x_ in cc]
            bm = bmesh.new()
            a = [bm.verts.new((x_, -wd / 2, z_)) for x_, z_ in pts]
            b = [bm.verts.new((x_, wd / 2, z_)) for x_, z_ in pts]
            for j in range(len(a)):
                bm.faces.new((a[j], a[(j + 1) % len(a)], b[(j + 1) % len(a)], b[j]))
            bm.faces.new(list(reversed(a)))
            bm.faces.new(b)
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
            o = core.mesh_obj("rest", bm)
            o.data.materials.append(mats.image(p2, rough=0.4, grime=0.0, name="kit_rest"))
            bv = o.modifiers.new("bevel", "BEVEL")
            bv.width = wd * 0.3
            bv.segments = 4
            bv.limit_method = "ANGLE"
            core.apply_mods(o)
            attr = o.data.color_attributes.new("label_uv", "FLOAT_COLOR", "CORNER")
            for li, loop in enumerate(o.data.loops):
                v = o.data.vertices[loop.vertex_index].co
                attr.data[li].color = ((v.x + L / 2) / L, v.z / h, 0, 1)
            vs = [body.matrix_world @ v.co for v in body.data.vertices]
            top = max(v.z for v in vs)
            o.location = (0, -D / 2 + c.get("y_frac", 0.4) * D, top - h * c.get("sink", 0.35))
            report.append({"part": "handset", "support": "evidence (painted side view) + function (grip width) + assembly (rests in the cradle)",
                           "width_mm": c.get("width_mm", 50), "confidence": "medium"})
            order["_rest"] = (o.location.x - L / 2 + 0.01, o.location.y, o.location.z + h * 0.2)
        elif c["type"] == "cord":
            col = np.asarray(img.crop(boxes[c["colour_panel"]])).reshape(-1, 3).mean(0) / 255
            start = Vector(order.get("_rest", (-W / 2, 0, H)))
            end = Vector(c.get("to", (-W / 2 - 0.01, 0.0, 0.03)))
            r, turns = 0.007, int((end - start).length / 0.009)
            axis = (end - start)
            ref = Vector((0, 1, 0)) if abs(axis.normalized().y) < 0.9 else Vector((1, 0, 0))
            e1 = axis.cross(ref).normalized()
            e2 = axis.cross(e1).normalized()
            pts = [start + axis * (t / (turns * 8)) + (e1 * math.cos(t / 8 * 2 * math.pi) + e2 * math.sin(t / 8 * 2 * math.pi)) * r
                   for t in range(turns * 8 + 1)]
            core.tube(pts, 0.0022, mats.plain(tuple(col), rough=0.5, name="kit_cord"), sides=6, name="cord")
            report.append({"part": "coiled cord", "support": "evidence (painted cord) + convention (handset to base side)",
                           "confidence": "medium"})
    for o in core.PARTS:
        pass
    print("KIT", order["name"], json.dumps(report))
    return {"width_m": round(W, 3), "depth_m": D, "height_m": H, "components": report,
            "size_warnings": sizing.envelope(order["category"], W, D, H)}
