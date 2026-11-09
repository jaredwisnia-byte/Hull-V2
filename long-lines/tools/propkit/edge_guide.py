"""Edge guides for the hull line: annotated copies of the painted views that steer cutting and topology.

An edge guide is the painted orthographic view with coloured lines drawn on it, same view, same
framing (the guide is registered to the painting by its outline here, and the fit is reported):

    red     physical separation between components   -> a full cut / part boundary
    cyan    exterior silhouette                      -> the outline (replaces the painted-mask guess)
    yellow  convex, rounded transition               -> extra local rounding, never a cut
    purple  recessed upholstery crease               -> a shallow pressed groove, never a cut

The guide never becomes texture. From it this module makes a machine-readable mask per view
(one-pixel skeleton lines labelled by class, plus the lines as point lists in JSON) in the
painted view's own crop coordinates, and a mesh hook that applies creases, cuts and rounding to the
dense hull mesh before smoothing and decimation, following the lines' exact curves.
"""
import json
import os

import numpy as np
from PIL import Image
from scipy import ndimage

CLASSES = {"cut": 1, "exterior": 2, "rounded": 3, "crease": 4}
NAMES = {v: k for k, v in CLASSES.items()}
# hue ranges (degrees) of the guide colours; lines are saturated and bright, the painting is not
HUES = {"cut": [(345, 360), (0, 15)], "rounded": [(40, 70)], "exterior": [(165, 200)], "crease": [(265, 310)]}
CREASE_DEPTH, CREASE_RADIUS = 0.014, 0.012      # metres; the hull's smoothing leaves about a third
CUT_DEPTH, CUT_RADIUS = 0.03, 0.006
ROUND_RADIUS, ROUND_ITERS = 0.02, 12


def classify(path):
    """Label image of the guide's coloured lines (0 = none)."""
    a = np.asarray(Image.open(path).convert("RGB")).astype(float) / 255
    mx, mn = a.max(2), a.min(2)
    sat = np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-6), 0)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    d = np.maximum(mx - mn, 1e-6)
    hue = np.where(mx == r, (60 * ((g - b) / d)) % 360, np.where(mx == g, 60 * ((b - r) / d) + 120, 60 * ((r - g) / d) + 240))
    line = (sat > 0.55) & (mx > 0.62)
    lab = np.zeros(a.shape[:2], np.uint8)
    for name, ranges in HUES.items():
        m = np.zeros_like(line)
        for lo, hi in ranges:
            m |= (hue >= lo) & (hue <= hi)
        lab[line & m] = CLASSES[name]
    return lab


def body_rows_only(mask):
    """Rows of the object's body (drops painted feet hanging below): last row >= 85% of full width."""
    rows = mask.sum(1)
    if not rows.any():
        return mask
    body = np.nonzero(rows > 0.85 * rows.max())[0]
    out = mask.copy()
    out[body[-1] + 1:] = False
    return out


def register(guide_path, view_path, strip_feet=False):
    """The guide's labels in the painted view's silhouette-crop coordinates, and how well they fit.

    The guide's object is what its cyan outline encloses; it is mapped onto the painted view's object
    box (independent x/y scale + offset). fit = IoU of the two object masks after mapping."""
    from .hull import silhouette
    lab = classify(guide_path)
    vm, _ = silhouette(view_path)
    cyan = ndimage.binary_dilation(lab == CLASSES["exterior"], iterations=2)
    inside = ndimage.binary_fill_holes(ndimage.binary_closing(cyan, iterations=5))   # bridge small gaps
    if inside.sum() < 1.5 * cyan.sum():                # still open: the drawn area (painting + lines)
        g = np.asarray(Image.open(guide_path).convert("L")) > 40
        inside = ndimage.binary_fill_holes(ndimage.binary_closing(g, iterations=3))
    # the line sits on the outline: shrink by half its thickness
    thick = max(1, int(round(np.median(ndimage.distance_transform_edt(cyan)[cyan]) if cyan.any() else 1)))
    core = ndimage.binary_erosion(inside, iterations=thick) if inside.sum() > 200 else inside
    if strip_feet:
        core = body_rows_only(core)
    ys, xs = np.nonzero(core)
    if not len(xs):
        return None
    box = (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1)
    h, w = vm.shape
    reg = np.asarray(Image.fromarray(lab[box[1]:box[3], box[0]:box[2]]).resize((w, h), Image.Resampling.NEAREST))
    gm = np.asarray(Image.fromarray(core[box[1]:box[3], box[0]:box[2]].astype(np.uint8) * 255).resize((w, h))) > 127
    fit = float((gm & vm).sum() / max(1, (gm | vm).sum()))
    return {"labels": reg, "object": gm, "fit": round(fit, 3)}


def skeletons(labels):
    """One-pixel lines per class (precise curves for Blender), and their point lists."""
    from skimage.morphology import skeletonize
    sk = np.zeros_like(labels)
    lines = {}
    for name, c in CLASSES.items():
        m = labels == c
        if not m.any():
            continue
        s = skeletonize(ndimage.binary_closing(m, iterations=1))
        sk[s] = c
        lab, n = ndimage.label(s, structure=np.ones((3, 3)))
        lines[name] = []
        for i in range(1, n + 1):
            ys, xs = np.nonzero(lab == i)
            if len(xs) < 4:
                continue
            order = np.argsort(xs if np.ptp(xs) >= np.ptp(ys) else ys)
            lines[name].append([[int(xs[j]), int(ys[j])] for j in order])
    return sk, lines


def prepare(guide_path, view_path, out_dir, tag, strip_feet=False, mirror=False):
    """Register a guide to its painted view and write the machine-readable mask (PNG + JSON)."""
    r = register(guide_path, view_path, strip_feet)
    if r is not None and mirror:
        r["labels"], r["object"] = r["labels"][:, ::-1].copy(), r["object"][:, ::-1].copy()
    if r is None:
        return None
    sk, lines = skeletons(r["labels"])
    os.makedirs(out_dir, exist_ok=True)
    png = os.path.join(out_dir, "edges_%s.png" % tag)
    Image.fromarray(sk).save(png)                       # values: 0 none, 1 cut, 2 exterior, 3 rounded, 4 crease
    js = os.path.join(out_dir, "edges_%s.json" % tag)
    json.dump({"classes": CLASSES, "size_px": list(sk.shape[::-1]), "fit": r["fit"], "lines": lines},
              open(js, "w"))
    r.update(skeleton=sk, mask_png=png, mask_json=js)
    return r


# view -> how a point (x in [-W/2, W/2], y in [-D/2, D/2], z in [0, H]) lands on the view's crop, and
# the direction the viewer looks from (the surface must face it)
def _uv(view, x, y, z, W, D, H):
    X, Y, Z = (x + W / 2) / W, (y + D / 2) / D, z / H
    return {"front": (X, 1 - Z), "back": (1 - X, 1 - Z), "right": (Y, 1 - Z), "left": (1 - Y, 1 - Z),
            "top": (X, 1 - Y)}[view]


TOWARD = {"front": (0, -1, 0), "back": (0, 1, 0), "right": (1, 0, 0), "left": (-1, 0, 0), "top": (0, 0, 1)}
SPAN = {"front": "W", "back": "W", "right": "D", "left": "D", "top": "W"}


def mesh_hook(guides, W, D, H, report=None, cuts="groove"):
    """A hull_prop mesh_hook applying the guides to the dense mesh: creases (and cuts) pressed in along
    the exact lines on surfaces that face (and are visible from) that view; rounding near yellow lines.
    cuts="groove": a red line is a narrow deep cut in this one surface (a single hull). cuts="structural":
    red lines are where separately built parts meet (hull_parts used them to split the parts), so they
    are not carved again."""
    def hook(obj):
        from mathutils import Vector
        from mathutils.bvhtree import BVHTree
        me = obj.data
        me.update()
        tree = BVHTree.FromPolygons([v.co for v in me.vertices], [p.vertices for p in me.polygons])
        n = len(me.vertices)
        disp = np.zeros((n, 3))
        rounded = np.zeros(n)
        counts = {"crease": 0, "cut": 0, "rounded": 0}
        for view, g in guides.items():
            if view not in TOWARD:
                continue
            sk = g["skeleton"]
            h, w = sk.shape
            ppm = w / {"W": W, "D": D}[SPAN[view]]
            kinds = ("crease", "cut", "rounded") if cuts == "groove" else ("crease", "rounded")
            dist = {c: ndimage.distance_transform_edt(sk != CLASSES[c]) / ppm for c in kinds
                    if (sk == CLASSES[c]).any()}
            if not dist:
                continue
            tow = Vector(TOWARD[view])
            for i, v in enumerate(me.vertices):
                nrm = v.normal
                if nrm.dot(tow) < 0.35:
                    continue
                u, vv = _uv(view, v.co.x, v.co.y, v.co.z, W, D, H)
                px, py = int(u * (w - 1)), int(vv * (h - 1))
                if not (0 <= px < w and 0 <= py < h):
                    continue
                if tree.ray_cast(v.co + nrm * 0.002, tow, 10.0)[0] is not None:
                    continue                                   # hidden from this view
                if "crease" in dist and dist["crease"][py, px] < CREASE_RADIUS:
                    f = (1 - dist["crease"][py, px] / CREASE_RADIUS) ** 2
                    disp[i] -= np.array(nrm) * CREASE_DEPTH * f
                    counts["crease"] += 1
                if "cut" in dist and dist["cut"][py, px] < CUT_RADIUS:
                    f = 1 - dist["cut"][py, px] / CUT_RADIUS
                    disp[i] -= np.array(nrm) * CUT_DEPTH * f
                    counts["cut"] += 1
                if "rounded" in dist and dist["rounded"][py, px] < ROUND_RADIUS:
                    rounded[i] = max(rounded[i], 1 - dist["rounded"][py, px] / ROUND_RADIUS)
        for i, v in enumerate(me.vertices):
            if disp[i].any():
                v.co += Vector(disp[i])
        if rounded.any():
            vg = obj.vertex_groups.new(name="guide_rounded")
            for i in np.nonzero(rounded)[0]:
                vg.add([int(i)], float(rounded[i]), "REPLACE")
            counts["rounded"] = int((rounded > 0).sum())
            m = obj.modifiers.new("guide_round", "SMOOTH")
            m.vertex_group = vg.name
            m.iterations = ROUND_ITERS
            m.factor = 0.8
        if report is not None:
            report[obj.name] = counts
    return hook
