"""Stress test on the oven: five variants, prepared for both pipelines without touching either
pipeline's modelling code. Run under Blender's Python (scipy/skimage):

    blender -b --factory-startup --python stress_test.py

Writes version-A work orders into factory/orders/ (+ sheets into source_textures/_sheets/) and
version-B manifests + depth atlases into stress/<variant>/B/. Building is done afterwards with
each pipeline's normal build command.
"""
import colorsys
import json
import os
import sys

import numpy as np
from PIL import Image
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(REPO, "tools"))
sys.path.insert(0, HERE)
from propkit.atlas import panels  # noqa: E402
from prep_sheetfirst_inputs import circles_in, depth_image, panel, LOG  # noqa: E402

SHEETS = os.path.join(REPO, "assets", "source_textures", "_sheets")


def recolour(src, dst, hue=0.25):
    a = np.asarray(Image.open(src).convert("RGB")).astype(float) / 255
    hsv = np.array(Image.fromarray((a * 255).astype(np.uint8)).convert("HSV")).astype(float)
    cream = (hsv[..., 1] < 110) & (hsv[..., 2] > 120)            # the painted enamel, not metal or black
    hsv[..., 0] = np.where(cream, 0.22 * 255, hsv[..., 0])
    hsv[..., 1] = np.where(cream, np.clip(hsv[..., 1] * 2.2 + 40, 0, 255), hsv[..., 1])
    Image.fromarray(hsv.astype(np.uint8), "HSV").convert("RGB").save(dst)


# variant: (sheet, A panel labels, B panel ids, W, D, H, drawer?)
APPL3 = {"door": 15, "drawer": 32, "cook": 0, "guard": 1, "sideR": 24, "sideL": 25}
APPL4 = {"door": 10, "drawer": 20, "cook": 1, "guard": 3, "sideR": 0, "sideL": 9}
VARIANTS = {
    "v1_avocado": ("appl_3_avocado.png", APPL3, 0.76, 0.66, 0.91, True),
    "v2_wide36": ("appl_3.png", APPL3, 0.91, 0.66, 0.91, True),
    "v3_deep_tall": ("appl_3.png", APPL3, 0.76, 0.70, 0.95, True),
    "v4_harvest_gold": ("appl_4.png", APPL4, 0.76, 0.66, 0.91, True),
    "v5_no_drawer": ("appl_3.png", APPL3, 0.76, 0.66, 0.91, False),
}


def order_a(name, sheet, ids, W, D, H, drawer):
    o = {"name": name, "category": "range_atlas", "line": "atlas", "sheet": sheet, "views_folder": name,
         "height_m": H, "cat_depth_m": D, "width_m": W,
         "front": [[ids["door"]], [ids["drawer"]]] if drawer else [[ids["door"]]],
         "side": 26 if sheet.startswith("appl_3") else ids["sideR"], "top": ids["cook"],
         "backguard": ids["guard"], "burners": 2 if sheet.startswith("appl_3") else 4, "controls": [ids["guard"]],
         "status": "pending", "class": None, "assumptions": ["stress test variant"], "notes": "stress " + name}
    os.makedirs(os.path.join(REPO, "assets", "source_textures", name), exist_ok=True)
    json.dump(o, open(os.path.join(REPO, "factory", "orders", name + ".json"), "w"), indent=1)


def manifest_b(name, sheet, ids, W, D, H, drawer):
    src = os.path.join(SHEETS, sheet)
    img = Image.open(src).convert("RGB")
    P = panels(src, 2500)
    door, cook, guard, sR, sL = (P[ids[k]] for k in ("door", "cook", "guard", "sideR", "sideL"))
    hd = W * (door[3] - door[1]) / (door[2] - door[0])
    hw = 0.0
    if drawer:
        dr = P[ids["drawer"]]
        hw = W * (dr[3] - dr[1]) / (dr[2] - dr[0])
    s = H / (hd + hw)
    hd, hw = hd * s, hw * s
    hg = W * (guard[3] - guard[1]) / (guard[2] - guard[0])
    field = np.zeros(img.size[::-1])
    yy, xx = np.mgrid[0:img.size[1], 0:img.size[0]]
    for cx, cy, r in circles_in(img, guard):
        field[(xx - cx) ** 2 + (yy - cy) ** 2 <= r * r] = 0.8
    for cx, cy, r in circles_in(img, cook):
        field[(xx - cx) ** 2 + (yy - cy) ** 2 <= r * r] = -0.6
    ps = [panel("front_door", door, (W, hd), (-W / 2, -D / 2, hw), (1, 0, 0), (0, 0, 1), (24, 22))]
    if drawer:
        ps.append(panel("front_drawer", P[ids["drawer"]], (W, hw), (-W / 2, -D / 2, 0), (1, 0, 0), (0, 0, 1), (24, 8)))
    ps += [panel("right", sR, (D, H), (W / 2, -D / 2, 0), (0, 1, 0), (0, 0, 1), (8, 12)),
           panel("left", sL, (D, H), (-W / 2, D / 2, 0), (0, -1, 0), (0, 0, 1), (8, 12)),
           panel("cooktop", cook, (W, D), (-W / 2, -D / 2, H), (1, 0, 0), (0, 1, 0), (28, 24)),
           panel("backguard", guard, (W, hg), (-W / 2, D / 2 - 0.05, H), (1, 0, 0), (0, 0, 1), (32, 10))]
    d = os.path.join(HERE, "stress", name, "B")
    os.makedirs(d, exist_ok=True)
    img.save(os.path.join(d, "atlas.png"))
    depth_image(img.size, field).save(os.path.join(d, "depth.png"))
    m = {"schema": 1, "asset_id": name, "description": "stress variant " + name,
         "atlas": {"albedo": "atlas.png", "depth": "depth.png", "size_px": list(img.size), "roughness": 0.6, "metallic": 0.05},
         "depth_range_m": {"inward": 0.02, "outward": 0.025}, "panels": ps}
    json.dump(m, open(os.path.join(d, "manifest.json"), "w"), indent=1)


if __name__ == "__main__":
    recolour(os.path.join(SHEETS, "appl_3.png"), os.path.join(SHEETS, "appl_3_avocado.png"))
    for v, (sheet, ids, W, D, H, drawer) in VARIANTS.items():
        order_a("stress_a_" + v, sheet, ids, W, D, H, drawer)
        manifest_b("stress_b_" + v, sheet, ids, W, D, H, drawer)
    print("STRESS prepared", list(VARIANTS), "stretch notes:", LOG.get("stretch", []))
