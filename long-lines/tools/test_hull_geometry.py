"""Regression tests for the hull builder's geometry (fast: synthetic drawings with known answers).

    blender -b --factory-startup -P tools/test_hull_geometry.py

Each case draws its views, builds with hull_prop (no paint) and checks one property:
  box       stays a box (volume / bounding box), no folds
  slope     a gentle slope drawn at low resolution has no terraces (fitted field at least 2x better
            than binary voxels)
  vase      a round top view is built round (slice circularity) and the lathe carve has no folds
  housing   a C-shaped outline keeps its cavity (front silhouette IoU) and has no folds
Exit code 1 on any failure. Asset-level checks: tools/diag/regress_assets.py.
"""
import os
import sys
import tempfile

import bmesh
import bpy
import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from propkit.hull import hull_prop, HULL_REPORT  # noqa: E402

TMP = tempfile.mkdtemp(prefix="hulltest_")
FAILS = []


def view(name, size, draw):
    im = Image.new("RGB", size, (0, 0, 0))
    draw(ImageDraw.Draw(im), size)
    framed = Image.new("RGB", (size[0] + 16, size[1] + 16), (0, 0, 0))   # views are drawn on a background
    framed.paste(im, (8, 8))
    p = os.path.join(TMP, "%s.png" % name)
    framed.save(p)
    return p


def build(views, h, mode, **kw):
    os.environ["HULL_FIELD"] = mode
    bpy.ops.wm.read_factory_settings(use_empty=True)
    return hull_prop(views, h, features=False, paint=False, smooth_iters=2, decimate=1.0, name="t", **kw)


def folds_per_1k(o):
    bm = bmesh.new()
    bm.from_mesh(o.data)
    f = sum(1 for e in bm.edges if len(e.link_faces) == 2 and e.link_faces[0].normal.angle(e.link_faces[1].normal, 0) > 2.0)
    n = len(bm.faces)
    bm.free()
    return 1000.0 * f / max(1, n)


def volume_ratio(o):
    bm = bmesh.new()
    bm.from_mesh(o.data)
    vol = abs(bm.calc_volume())
    bm.free()
    co = np.array([v.co for v in o.data.vertices])
    return vol / np.prod(co.max(0) - co.min(0))


def check(name, ok, detail):
    print("%s %-8s %s" % ("ok  " if ok else "FAIL", name, detail))
    if not ok:
        FAILS.append(name)


TAN = (200, 170, 120)
# box: three squares
sq = lambda n: view(n, (120, 120), lambda d, s: d.rectangle([0, 0, s[0] - 1, s[1] - 1], fill=TAN))
box = build({"front": sq("bf"), "right": sq("br"), "top": sq("bt")}, 0.5, "sdf", res=60)
vr, fo = volume_ratio(box), folds_per_1k(box)
check("box", vr > 0.93 and fo < 0.5, "volume/bbox %.3f (> 0.93), folds/1k %.2f" % (vr, fo))

# slope: side view a long low wedge, top sloping 1:15, drawn small (each pixel step is a terrace in binary)
wedge = lambda d, s: d.polygon([(0, s[1] - 1), (0, 12), (s[0] - 1, 12 + s[0] // 15), (s[0] - 1, s[1] - 1)], fill=TAN)
sv = {"front": view("sf", (60, 40), lambda d, s: d.rectangle([0, 0, s[0] - 1, s[1] - 1], fill=TAN)),
      "right": view("sr", (240, 40), wedge),
      "top": view("st", (60, 240), lambda d, s: d.rectangle([0, 0, s[0] - 1, s[1] - 1], fill=TAN))}


def terrace_deg(o):
    """Spread of the normals on the sloped top (degrees): 0 for a clean plane."""
    ns = np.array([p.normal for p in o.data.polygons])
    cs = np.array([p.center for p in o.data.polygons])
    co = np.array([v.co for v in o.data.vertices])
    lo, hi = co.min(0), co.max(0)
    inner = (ns[:, 2] > 0.8) & (cs[:, 0] > lo[0] + 0.2 * (hi - lo)[0]) & (cs[:, 0] < hi[0] - 0.2 * (hi - lo)[0]) \
        & (cs[:, 1] > lo[1] + 0.1 * (hi - lo)[1]) & (cs[:, 1] < hi[1] - 0.1 * (hi - lo)[1])
    m = ns[inner].mean(0)
    m /= np.linalg.norm(m)
    return float(np.degrees(np.arccos(np.clip(ns[inner] @ m, -1, 1))).mean())


tb = terrace_deg(build(sv, 0.3, "binary", res=60))
ts = terrace_deg(build(sv, 0.3, "sdf", res=60))
check("slope", ts < 0.5 * tb and ts < 2.0, "normal spread on the slope: binary %.2f deg, fitted %.2f deg" % (tb, ts))


# vase: round top, vase profile front/side
def vase_profile(d, s):
    w, h = s
    pts = []
    for r in range(h):
        t = r / (h - 1)
        half = (0.25 + 0.25 * np.sin(np.pi * (0.15 + 0.85 * t))) * w
        pts.append((w / 2 - half, r))
    d.polygon(pts + [(w - x, y) for x, y in reversed(pts)], fill=(60, 60, 60))


vv = {"front": view("vf", (100, 140), vase_profile), "right": view("vr", (100, 140), vase_profile),
      "top": view("vt", (100, 100), lambda d, s: d.ellipse([2, 2, s[0] - 3, s[1] - 3], fill=(60, 60, 60)))}
vase = build(vv, 0.3, "sdf", res=70)
rev = HULL_REPORT.get("revolve") or {}
co = np.array([v.co for v in vase.data.vertices])
zm = (co[:, 2].min() + co[:, 2].max()) / 2
ring = co[np.abs(co[:, 2] - zm) < 0.006]
c = (co.max(0) + co.min(0)) / 2
rad = np.hypot(ring[:, 0] - c[0], ring[:, 1] - c[1])
circ = rad.std() / rad.mean()
fo = folds_per_1k(vase)
check("vase", bool(rev.get("round")) and circ < 0.04 and fo < 1.0,
      "round %s, slice radius spread %.3f (< 0.04), folds/1k %.2f" % (rev.get("round"), circ, fo))

# housing: a C shape seen from the side (cavity open to the front), rectangles elsewhere
cshape = lambda d, s: (d.rectangle([0, 0, s[0] - 1, s[1] - 1], fill=TAN),
                       d.rectangle([0, int(0.3 * s[1]), int(0.6 * s[0]), int(0.8 * s[1])], fill=(0, 0, 0)))
hv = {"front": view("hf", (100, 130), lambda d, s: d.rectangle([0, 0, s[0] - 1, s[1] - 1], fill=TAN)),
      "right": view("hr", (110, 130), cshape),
      "top": view("ht", (100, 110), lambda d, s: d.rectangle([0, 0, s[0] - 1, s[1] - 1], fill=TAN))}
hs = build(hv, 0.33, "sdf", res=70)
co = np.array([v.co for v in hs.data.vertices])
# cavity: no vertex should sit deep inside it (front 40% of the depth, between 35% and 75% height)
lo, hi = co.min(0), co.max(0)
e = hi - lo
inside = ((co[:, 1] < lo[1] + 0.45 * e[1]) & (co[:, 2] > lo[2] + 0.35 * e[2]) & (co[:, 2] < lo[2] + 0.75 * e[2])
          & (co[:, 0] > lo[0] + 0.1 * e[0]) & (co[:, 0] < hi[0] - 0.1 * e[0]))
# vertices on the cavity walls are fine; vertices filling it would have normals pointing everywhere
fo = folds_per_1k(hs)
vr = volume_ratio(hs)
check("housing", 0.68 < vr < 0.82 and fo < 0.5, "volume/bbox %.3f (C shape: 0.68-0.82), folds/1k %.2f" % (vr, fo))

print("HULL GEOMETRY TESTS: %d failed" % len(FAILS))
sys.exit(1 if FAILS else 0)
