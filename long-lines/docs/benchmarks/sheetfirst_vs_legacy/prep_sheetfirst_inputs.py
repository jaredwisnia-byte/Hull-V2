"""Version B preparation: writes a sheet-first manifest + signed-depth atlas for each benchmark
object from the SAME reference art used by version A. Everything here is preparation work the
sheet-first line needs and the legacy lines do not; it is counted in the report.

    blender -b --factory-startup --python prep_sheetfirst_inputs.py

Depth atlases use the sheet-first colour convention: white = 0, red = recessed, blue = protruding.
Depth content is authored by simple rules written for each object (circles found by Hough,
dark regions, gradients) - i.e. per-object human/AI authoring, not a general automatic step.
"""
import json
import math
import os
import shutil
import sys

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "tools"))
from propkit.atlas import panels  # noqa: E402
from propkit.hull import detect_circles  # noqa: E402

LOG = {}


def signed(t):
    """t in -1..1 -> RGB (red = -1 recessed, white = 0, blue = +1 protruding)."""
    t = float(np.clip(t, -1, 1))
    if t >= 0:
        return (int(255 * (1 - t)), int(255 * (1 - t)), 255)
    return (255, int(255 * (1 + t)), int(255 * (1 + t)))


def depth_image(size, field):
    """field: float array (h, w) in -1..1 -> RGB depth atlas."""
    h, w = field.shape
    f = np.clip(field, -1, 1)
    r = np.where(f < 0, 255, 255 * (1 - f))
    g = 255 * (1 - np.abs(f))
    b = np.where(f > 0, 255, 255 * (1 + f))
    return Image.fromarray(np.dstack([r, g, b]).clip(0, 255).astype(np.uint8))


def panel(name, rect, size, origin, u, v, grid, stretch=False, note=None):
    p = {"name": name, "size_m": [round(size[0], 4), round(size[1], 4)], "rect_px": [int(x) for x in rect],
         "origin_m": [round(x, 4) for x in origin], "u_axis": list(u), "v_axis": list(v), "grid": list(grid)}
    ra = (rect[2] - rect[0]) / (rect[3] - rect[1])
    sa = size[0] / size[1]
    if abs(ra / sa - 1) > 0.05:
        p["allow_stretch"] = True
        LOG.setdefault("stretch", []).append("%s: painted %.2f vs real %.2f (%+.0f%%)" % (name, ra, sa, (ra / sa - 1) * 100))
    return p


def write(obj, atlas_src, depth_field, panels_, extra=None):
    d = os.path.join(HERE, "inputs", obj, "B")
    os.makedirs(d, exist_ok=True)
    im = Image.open(atlas_src).convert("RGB")
    im.save(os.path.join(d, "atlas.png"))
    depth_image(im.size, depth_field).save(os.path.join(d, "depth.png"))
    m = {"schema": 1, "asset_id": "bench_b_" + obj, "description": "benchmark version B: " + obj,
         "atlas": {"albedo": "atlas.png", "depth": "depth.png", "size_px": list(im.size), "roughness": 0.6, "metallic": 0.05},
         "depth_range_m": extra.get("depth", {"inward": 0.02, "outward": 0.03}) if extra else {"inward": 0.02, "outward": 0.03},
         "panels": panels_}
    json.dump(m, open(os.path.join(d, "manifest.json"), "w"), indent=1)
    tris = sum(2 * p["grid"][0] * p["grid"][1] for p in panels_)
    LOG.setdefault("objects", {})[obj] = {"panels": len(panels_), "planned_tris": tris,
                                          "stretched_panels": sum(1 for p in panels_ if p.get("allow_stretch"))}


def circles_in(img, rect):
    x0, y0, x1, y1 = rect
    return [(x0 + cx, y0 + cy, r) for cx, cy, r in detect_circles(img.crop(rect))]


# ---------------------------------------------------------------- oven (appliance atlas 3)
def oven():
    src = os.path.join(HERE, "inputs", "oven", "reference.png")
    img = Image.open(src).convert("RGB")
    P = panels(src, 2500)
    W, D, H = 0.76, 0.66, 0.91
    door, drawer, cook, guard, sideR, sideL = P[15], P[32], P[0], P[1], P[24], P[25]
    hd = W * (door[3] - door[1]) / (door[2] - door[0])
    hw = W * (drawer[3] - drawer[1]) / (drawer[2] - drawer[0])
    s = H / (hd + hw)                       # the painted front panels don't add up to the body height
    hd, hw = hd * s, hw * s
    hg = W * (guard[3] - guard[1]) / (guard[2] - guard[0])
    field = np.zeros(img.size[::-1])
    yy, xx = np.mgrid[0:img.size[1], 0:img.size[0]]
    for cx, cy, r in circles_in(img, guard):          # knobs stand out
        field[(xx - cx) ** 2 + (yy - cy) ** 2 <= r * r] = 0.8
    for cx, cy, r in circles_in(img, cook):           # burner wells sink
        field[(xx - cx) ** 2 + (yy - cy) ** 2 <= r * r] = -0.6
    g = np.asarray(img.convert("L")).astype(float)
    x0, y0, x1, y1 = door                             # oven window: the dark area of the door
    sub = g[y0:y1, x0:x1]
    win = ndimage.binary_opening(sub < np.percentile(sub, 30), iterations=3)
    lab, n = ndimage.label(win)
    if n:
        k = np.argmax(np.bincount(lab.ravel())[1:]) + 1
        field[y0:y1, x0:x1][lab == k] = -0.5
    ps = [panel("front_door", door, (W, hd), (-W / 2, -D / 2, hw), (1, 0, 0), (0, 0, 1), (24, 22)),
          panel("front_drawer", drawer, (W, hw), (-W / 2, -D / 2, 0), (1, 0, 0), (0, 0, 1), (24, 8)),
          panel("right", sideR, (D, H), (W / 2, -D / 2, 0), (0, 1, 0), (0, 0, 1), (8, 12)),
          panel("left", sideL, (D, H), (-W / 2, D / 2, 0), (0, -1, 0), (0, 0, 1), (8, 12)),
          panel("cooktop", cook, (W, D), (-W / 2, -D / 2, H), (1, 0, 0), (0, 1, 0), (28, 24)),
          panel("backguard", guard, (W, hg), (-W / 2, D / 2 - 0.05, H), (1, 0, 0), (0, 0, 1), (32, 10))]
    LOG.setdefault("notes", []).append("oven: front panels scaled x%.2f to fill the 0.91 m body; no back panel exists on the sheet (left open); sides use panels 24/25 (A's order used 26)" % s)
    write("oven", src, field, ps, {"depth": {"inward": 0.02, "outward": 0.025}})


# ---------------------------------------------------------------- fridge (sheet set)
def fridge():
    d = os.path.join(HERE, "inputs", "fridge")
    m = json.load(open(os.path.join(d, "fridge_1_manifest.json")))
    paint = os.path.join(d, "fridge_1_painted.png")
    depth = np.asarray(Image.open(os.path.join(d, "fridge_1_depth.png")).convert("L")).astype(float) / 255
    parts = np.asarray(Image.open(os.path.join(d, "fridge_1_parts.png")).convert("RGB")).max(-1) > 30
    W, D, H = 0.775, 0.75, 1.65
    field = np.zeros(depth.shape)
    rect = {}
    for k, b in m["painted_sheet"]["view_bboxes_px"].items():
        x0, y0, x1, y1 = b
        sub = parts[y0:y1 - 3, x0:x1]
        ys, xs = np.nonzero(sub)
        r = (x0 + xs.min(), y0 + ys.min(), x0 + xs.max() + 1, y0 + ys.max() + 1)   # tight to the drawing
        rect[k] = r
        dz = depth[r[1]:r[3], r[0]:r[2]]
        msk = parts[r[1]:r[3], r[0]:r[2]]
        med = np.median(dz[msk])
        field[r[1]:r[3], r[0]:r[2]] = np.where(msk, (dz - med) / 0.25, 0)
    ps = [panel("front", rect["front"], (W, H), (-W / 2, -D / 2, 0), (1, 0, 0), (0, 0, 1), (30, 64)),
          panel("right", rect["right"], (D, H), (W / 2, -D / 2, 0), (0, 1, 0), (0, 0, 1), (12, 24)),
          panel("back", rect["back"], (W, H), (W / 2, D / 2, 0), (-1, 0, 0), (0, 0, 1), (24, 48)),
          panel("left", rect["left"], (D, H), (-W / 2, D / 2, 0), (0, -1, 0), (0, 0, 1), (12, 24)),
          panel("top", rect["top"], (W, D), (-W / 2, -D / 2, H), (1, 0, 0), (0, 1, 0), (12, 12))]
    LOG.setdefault("notes", []).append("fridge: depth converted from the supplied grayscale map, relative to each view's median; no corner panels exist, so the rounded cabinet edges cannot be represented")
    write("fridge", paint, field, ps, {"depth": {"inward": 0.02, "outward": 0.035}})


# ---------------------------------------------------------------- crown moulding (trim sheet 6)
def crown():
    src = os.path.join(HERE, "inputs", "crown", "reference.png")
    img = Image.open(src).convert("RGB")
    P = panels(src, 900)
    strip, prof = P[0], P[1]
    x0, y0, x1, y1 = strip
    strip = (x0, y0, x0 + int(0.88 * (x1 - x0)), y1)         # same crop as version A's order
    L, Hh, Dd = 1.2, 0.28, 0.165
    # Profile depth per height from the drawn section (fraction of the deepest point).
    pm = np.asarray(img.crop(prof).convert("RGB")).max(-1) > 48
    lab, n = ndimage.label(pm)
    big = ndimage.binary_fill_holes(lab == (np.argmax(np.bincount(lab.ravel())[1:]) + 1))
    ys, xs = np.nonzero(big)
    big = big[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    wall_left = big[:, :3].mean() >= big[:, -3:].mean()
    prof_d = np.array([(np.nonzero(r)[0].max() + 1 if wall_left else big.shape[1] - np.nonzero(r)[0].min()) if r.any() else 0
                       for r in big], float) / big.shape[1]
    field = np.zeros(img.size[::-1])
    hs = strip[3] - strip[1]
    for r in range(hs):
        field[strip[1] + r, strip[0]:strip[2]] = prof_d[min(len(prof_d) - 1, int(r / hs * len(prof_d)))]
    ps = [panel("face", strip, (L, Hh), (0, 0, 0), (1, 0, 0), (0, 0, 1), (32, 120))]
    LOG.setdefault("notes", []).append("crown: profile authored as a row-by-row relief (a heightfield cannot undercut, so the cove is approximated); the painted strip is one rectangle: it is stretched over 1.2 m rather than repeated; no ends, top or underside")
    write("crown", src, field, ps, {"depth": {"inward": 0.001, "outward": Dd}})


# ---------------------------------------------------------------- television (5-view painting)
def tv():
    src_dir = os.path.join(REPO, "assets", "source_textures", "tv_painted")
    views = ["front", "right", "back", "left", "top"]
    ims = {k: Image.open(os.path.join(src_dir, "v_%s.png" % k)).convert("RGB") for k in views}
    pad = 8
    Wa = sum(im.size[0] for im in ims.values()) + pad * 6
    Ha = max(im.size[1] for im in ims.values()) + pad * 2
    atlas = Image.new("RGB", (Wa, Ha), (20, 20, 20))
    rect, x = {}, pad
    for k in views:                                       # pure layout: paint unchanged
        atlas.paste(ims[k], (x, pad))
        rect[k] = (x, pad, x + ims[k].size[0], pad + ims[k].size[1])
        x += ims[k].size[0] + pad
    d = os.path.join(HERE, "inputs", "tv")
    os.makedirs(d, exist_ok=True)
    ap = os.path.join(d, "tv_views_atlas.png")
    atlas.save(ap)
    W, D, H = 0.662, 0.308, 0.48
    field = np.zeros((Ha, Wa))
    g = np.asarray(atlas.convert("L")).astype(float)
    x0, y0, x1, y1 = rect["front"]
    sub = g[y0:y1, x0:x1]
    scr = ndimage.binary_opening(sub < np.percentile(sub, 35), iterations=3)
    lab, n = ndimage.label(scr)
    if n:
        k = np.argmax(np.bincount(lab.ravel())[1:]) + 1
        field[y0:y1, x0:x1][ndimage.binary_erosion(lab == k, iterations=2)] = -0.6   # screen sits back
    yy, xx = np.mgrid[0:Ha, 0:Wa]
    for cx, cy, r in circles_in(atlas, rect["front"]):
        field[(xx - cx) ** 2 + (yy - cy) ** 2 <= r * r] = 0.8                      # knobs stand out
    ps = [panel("front", rect["front"], (W, H), (-W / 2, -D / 2, 0), (1, 0, 0), (0, 0, 1), (60, 48)),
          panel("right", rect["right"], (D, H), (W / 2, -D / 2, 0), (0, 1, 0), (0, 0, 1), (24, 36)),
          panel("back", rect["back"], (W, H), (W / 2, D / 2, 0), (-1, 0, 0), (0, 0, 1), (40, 30)),
          panel("left", rect["left"], (D, H), (-W / 2, D / 2, 0), (0, -1, 0), (0, 0, 1), (24, 36)),
          panel("top", rect["top"], (W, D), (-W / 2, -D / 2, H), (1, 0, 0), (0, 1, 0), (40, 20))]
    LOG.setdefault("notes", []).append("tv: the five split views laid out side by side as one atlas (paint unchanged); screen recess and knobs authored by rules; the curved screen bulge is not represented")
    write("tv", ap, field, ps, {"depth": {"inward": 0.03, "outward": 0.025}})


# ---------------------------------------------------------------- armchair (furniture sheet 2)
def armchair():
    src = os.path.join(HERE, "inputs", "armchair", "reference.png")
    img = Image.open(src).convert("RGB")
    P = panels(src, 2500)
    field = np.zeros(img.size[::-1])

    def bulge(rect, amount):
        x0, y0, x1, y1 = rect
        yy, xx = np.mgrid[0:y1 - y0, 0:x1 - x0]
        u = (xx / max(1, x1 - x0 - 1)) * 2 - 1
        v = (yy / max(1, y1 - y0 - 1)) * 2 - 1
        field[y0:y1, x0:x1] = np.maximum(field[y0:y1, x0:x1], amount * np.clip(1 - np.maximum(np.abs(u), np.abs(v)) ** 4, 0, 1))
    for i, a in ((0, 0.9), (11, 0.9), (12, 0.7), (6, 0.5), (7, 0.5)):
        bulge(P[i], a)
    ps = [panel("back_front", P[0], (0.62, 0.43), (-0.31, 0.25, 0.42), (1, 0, 0), (0, 0, 1), (24, 18)),
          panel("back_rear", P[1], (0.80, 0.64), (0.40, 0.42, 0.0), (-1, 0, 0), (0, 0, 1), (8, 8)),
          panel("seat_front", P[11], (0.62, 0.25), (-0.31, -0.30, 0.20), (1, 0, 0), (0, 0, 1), (20, 10)),
          panel("seat_top", P[12], (0.62, 0.55), (-0.31, -0.30, 0.45), (1, 0, 0), (0, 1, 0), (20, 16)),
          panel("side_right", P[2], (0.85, 0.65), (0.40, -0.42, 0.0), (0, 1, 0), (0, 0, 1), (16, 12)),
          panel("side_left", P[3], (0.85, 0.65), (-0.40, 0.43, 0.0), (0, -1, 0), (0, 0, 1), (16, 12)),
          panel("arm_front_right", P[6], (0.18, 0.35), (0.22, -0.42, 0.30), (1, 0, 0), (0, 0, 1), (6, 10)),
          panel("arm_front_left", P[7], (0.18, 0.35), (-0.40, -0.42, 0.30), (1, 0, 0), (0, 0, 1), (6, 10)),
          panel("skirt_front", P[13], (0.80, 0.13), (-0.40, -0.42, 0.07), (1, 0, 0), (0, 0, 1), (16, 4))]
    LOG.setdefault("notes", []).append("armchair: nine panels positioned by hand from typical armchair proportions; cushion relief authored as soft bulges; no legs, arm tops or inner arm faces (no panels painted for them)")
    write("armchair", src, field, ps, {"depth": {"inward": 0.01, "outward": 0.05}})


if __name__ == "__main__":
    for f in (oven, fridge, crown, tv, armchair):
        f()
    json.dump(LOG, open(os.path.join(HERE, "inputs", "prep_log_B.json"), "w"), indent=1)
    print("PREP", json.dumps(LOG))
