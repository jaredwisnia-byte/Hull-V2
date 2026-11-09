"""Reconcile: make a painted sheet's views agree with each other before anything is built from them.

Image generators draw pretty sheets that contradict themselves: a top view twice as deep as the side views,
a side view drawn mirrored, printed dimensions that no view matches. Averaging contradictions gives an
object that matches no drawing, so this station measures everything, keeps what agrees and rejects the
rest, and says what it did:

1. Measure every proportion each view shows on the object's core (feet, knobs and cables left out):
   front and back give width/height, the sides depth/height, top and bottom width/depth.
2. Decide each axis. Printed dimensions (the sheet's own numbers) are trusted first; otherwise the largest
   group of views that agree within TOL decides, and the others are outliers.
3. Every view whose proportion is off is not trusted for that axis: the build stretches it to the decided
   size (the hull does this when it is given width, depth and height), and the report says by how much.
4. Orientation: a side view must put the object's front where the top view does (protrusions such as
   knobs stick out at the same end). A side view that matches the top view only when flipped was drawn
   mirrored and is flipped.
5. Opposite views must agree in outline (front vs mirrored back, left vs mirrored right). A view that
   disagrees with its opposite where the opposite agrees with the rest only paints; it does not carve.

Returns the views to build from (flipped copies where needed), the decided size, the views that only
paint, and a report.
"""
import os

import numpy as np
from PIL import Image

from .hull import silhouette

TOL = 0.08              # proportions within 8% agree
MIRROR_MARGIN = 0.15    # a flip must match the top view this much better (correlation) to be applied
OUTLINE_IOU = 0.85      # opposite views agreeing less than this in outline disagree
N = 64
PROTRUDE = 0.03         # a band this wide (share of the view) past the core counts as sticking out
CORE = 0.5              # a row or column at least this full (vs the fullest) is part of the object's core


def _box(path):
    """Silhouette and its core extent (w, h): rows and columns at least CORE as full as the fullest, so feet,
    knobs and a dangling cable do not count towards the object's proportions."""
    m, _ = silhouette(path)
    rows, cols = m.sum(1), m.sum(0)
    h = int((rows >= CORE * rows.max()).sum())
    w = int((cols >= CORE * cols.max()).sum())
    return m, w, h


def _resample(m, w=N, h=N):
    return np.asarray(Image.fromarray(m.astype(np.uint8) * 255).resize((w, h), Image.BILINEAR)) > 127


def _profile(m, axis):
    """Occupancy along one axis (share of the other axis filled), resampled to N."""
    p = m.mean(axis=axis)
    return np.interp(np.linspace(0, len(p) - 1, N), np.arange(len(p)), p)


def _corr(a, b):
    a, b = a - a.mean(), b - b.mean()
    d = np.sqrt((a * a).sum() * (b * b).sum())
    return float((a * b).sum() / d) if d > 1e-9 else 0.0


def _group(values, tol=TOL):
    """The largest group of values agreeing within tol of their median; its median."""
    best = []
    for v in values.values():
        g = [k for k, x in values.items() if abs(x / v - 1) <= tol]
        if len(g) > len(best):
            best = g
    return float(np.median([values[k] for k in best])), best


def run(views, printed_mm=None, tmp="/tmp/_reconcile"):
    os.makedirs(tmp, exist_ok=True)
    rep = {"views": {}, "decisions": []}
    m = {k: _box(p) for k, p in views.items() if k in ("front", "back", "left", "right", "top", "bottom")}
    r_wh = {k: m[k][1] / m[k][2] for k in ("front", "back") if k in m}           # width / height
    r_dh = {k: m[k][1] / m[k][2] for k in ("left", "right") if k in m}           # depth / height
    r_wd = {k: m[k][1] / m[k][2] for k in ("top", "bottom") if k in m}           # width / depth

    # 2. decide the axes (proportions relative to the height)
    if printed_mm:
        W, H, D = (v / 1000.0 for v in printed_mm)
        wh, dh = W / H, D / H
        rep["decided_by"] = "printed dimensions %s mm (trusted first)" % "x".join("%g" % v for v in printed_mm)
    else:
        wh, gw = _group(r_wh) if r_wh else (None, [])
        dh, gd = _group(r_dh) if r_dh else (None, [])
        if dh is None and wh and r_wd:
            dh = wh / _group(r_wd)[0]
        rep["decided_by"] = "largest agreeing group of views"
        W = H = D = None
    wd = wh / dh
    for k, r in list(r_wh.items()) + list(r_dh.items()) + list(r_wd.items()):
        want = wh if k in r_wh else dh if k in r_dh else wd
        off = r / want - 1
        rep["views"][k] = {"proportion": round(r, 3), "decided": round(want, 3), "off_pct": round(off * 100, 1),
                           "agrees": abs(off) <= TOL}
        if abs(off) > TOL:
            rep["decisions"].append("%s view's proportion is %+.0f%% off: not trusted for size, stretched to the decided size" % (k, off * 100))

    # 4. orientation of the side views against the top view (front at the top view's bottom edge)
    out = dict(views)
    if "top" in m:
        top_depth = _profile(m["top"][0], axis=1)[::-1]                     # front -> back
        for k in ("right", "left"):
            if k not in m:
                continue
            side = _profile(m[k][0], axis=0)                                  # image left -> right
            side = side if k == "right" else side[::-1]                       # convention: right view has front at left
            as_drawn, flipped = _corr(side, top_depth), _corr(side[::-1], top_depth)
            rep["views"].setdefault(k, {})["orientation"] = {"as_drawn": round(as_drawn, 2), "flipped": round(flipped, 2)}
            if flipped - as_drawn > MIRROR_MARGIN:
                q = os.path.join(tmp, "v_%s.png" % k)
                Image.open(views[k]).transpose(Image.FLIP_LEFT_RIGHT).save(q)
                out[k] = q
                m[k] = _box(q)
                rep["decisions"].append("%s view drawn mirrored (it matches the top view only when flipped: %.2f vs %.2f): flipped" % (
                    k, flipped, as_drawn))

    # 4b. one-sided protrusions: something sticking out past a side view's core (knobs seen side-on) that
    # the opposite view does not show would be stretched across the whole face by the hull (bars carved
    # across the front). Such columns are cropped from that view; the front view still paints them.
    for a, b in (("right", "left"), ("left", "right"), ("front", "back"), ("back", "front")):
        if a not in m or b not in m:
            continue
        ma = m[a][0]
        ca = ma.mean(0)
        cb = m[b][0].mean(0)[::-1]                      # the opposite view, mirrored: same ends
        w = ma.shape[1]

        def bands(c):
            core = np.nonzero(c >= CORE * c.max())[0]
            lo_, hi_ = int(core.min()), int(core.max()) + 1
            return lo_ / len(c), (len(c) - hi_) / len(c), lo_, hi_
        a_lo, a_hi, lo, hi = bands(ca)
        b_lo, b_hi, _, _ = bands(cb)
        # each view's own band past its core, compared by share: one view sticks out where the other does not
        extra_lo = a_lo > PROTRUDE and b_lo < a_lo / 3
        extra_hi = a_hi > PROTRUDE and b_hi < a_hi / 3
        if not (extra_lo or extra_hi):
            continue
        im = Image.open(out[a]).convert("RGB")
        _, _, (x0, y0, x1, y1) = silhouette(out[a], with_box=True)
        c0 = x0 + (lo if extra_lo else 0)
        c1 = x0 + (hi if extra_hi else w)
        a_img = np.asarray(im).copy()
        bg = np.median(np.concatenate([a_img[0], a_img[-1]]), axis=0).astype(np.uint8)
        a_img[:, :c0] = bg
        a_img[:, c1:] = bg
        q = os.path.join(tmp, "v_%s.png" % a)
        Image.fromarray(a_img).save(q)
        out[a] = q
        m[a] = _box(q)
        rep["decisions"].append("%s view: %s sticks out past its core where the %s view shows nothing: left out of the shape (painted only)" % (
            a, "its front" if (extra_lo and a == "right") or (extra_hi and a == "left") else "an edge", b))

    # 5. opposite views must agree in outline
    paint_only = []
    for a, b in (("front", "back"), ("right", "left")):
        if a in m and b in m:
            ma, mb = _resample(m[a][0]), _resample(m[b][0])[:, ::-1]
            iou = float((ma & mb).sum() / max((ma | mb).sum(), 1))
            rep["views"].setdefault(a, {})["outline_vs_%s" % b] = round(iou, 3)
            if iou < OUTLINE_IOU:
                # keep the one that agrees with the decided proportion better; the other only paints
                da = abs(rep["views"].get(a, {}).get("off_pct", 0))
                db = abs(rep["views"].get(b, {}).get("off_pct", 0))
                worse = a if da > db else b
                paint_only.append(worse)
                rep["decisions"].append("%s and %s disagree in outline (IoU %.2f): %s only paints" % (a, b, iou, worse))
    for k in ("top", "bottom"):
        if k in rep["views"] and not rep["views"][k]["agrees"]:
            # a top or bottom view in the wrong proportion would carve the wrong plan: paint only
            paint_only.append(k)
            rep["decisions"].append("%s view only paints (its proportion disagrees)" % k)
    rep["paint_only"] = sorted(set(paint_only))
    size = {"width_m": W, "height_m": H, "depth_m": D} if printed_mm else None
    return out, size, rep["paint_only"], rep
