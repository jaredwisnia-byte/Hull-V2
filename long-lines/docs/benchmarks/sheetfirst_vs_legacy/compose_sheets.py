"""Comparison sheets: reference | version A (legacy) | version B (sheet-first), one row per view,
plus a UV-layout row. python3 compose_sheets.py"""
import json
import os

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
F = lambda s: ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", s)
CELL = 420
REF = {  # what to show in the reference column per view (file, box or None)
    "oven": {"front": ("inputs/oven/front_composite.png", None), "threequarter": ("inputs/oven/reference.png", None)},
    "fridge": {"front": ("inputs/fridge/fridge_1_painted.png", "front"), "side": ("inputs/fridge/fridge_1_painted.png", "right"),
               "rear": ("inputs/fridge/fridge_1_painted.png", "back"), "top": ("inputs/fridge/fridge_1_painted.png", "top")},
    "crown": {"front": ("inputs/crown/reference.png", "strip"), "side": ("inputs/crown/reference.png", "profile"),
              "threequarter": ("inputs/crown/reference.png", None)},
    "tv": {"front": ("inputs/tv/v_front.png", None), "side": ("inputs/tv/v_right.png", None), "rear": ("inputs/tv/v_back.png", None),
           "top": ("inputs/tv/v_top.png", None)},
    "armchair": {"threequarter": ("inputs/armchair/reference.png", None)},
}
VIEWS = ["front", "side", "rear", "threequarter", "top"]


def fit(im, w, h):
    im = im.copy()
    im.thumbnail((w, h))
    out = Image.new("RGB", (w, h), (30, 30, 34))
    out.paste(im, ((w - im.size[0]) // 2, (h - im.size[1]) // 2))
    return out


def ref_cell(obj, view):
    spec = REF.get(obj, {}).get(view)
    if not spec:
        c = Image.new("RGB", (CELL, CELL), (30, 30, 34))
        ImageDraw.Draw(c).text((20, CELL // 2 - 10), "no reference for this view", font=F(18), fill=(150, 150, 150))
        return c
    fn, box = spec
    im = Image.open(os.path.join(HERE, fn)).convert("RGB")
    if isinstance(box, str):
        if obj == "fridge":
            b = json.load(open(os.path.join(HERE, "inputs/fridge/fridge_1_manifest.json")))["painted_sheet"]["view_bboxes_px"][box]
            im = im.crop(tuple(b))
        elif obj == "crown":
            rv = json.load(open(os.path.join(HERE, "reference_views.json")))["crown"]
            im = im.crop(tuple(rv["front_texture"]["box"] if box == "strip" else rv["silhouettes"]["profile"]["box"]))
    return fit(im, CELL, CELL)


def model_cell(obj, ver, view):
    p = os.path.join(HERE, "renders", "%s_%s_%s.png" % (obj, ver, view))
    return fit(Image.open(p).convert("RGB"), CELL, CELL) if os.path.exists(p) else Image.new("RGB", (CELL, CELL), (60, 0, 0))


for obj in REF:
    rows = VIEWS + ["uv"]
    head = 60
    sheet = Image.new("RGB", (CELL * 3 + 160, head + len(rows) * (CELL + 8)), (18, 18, 22))
    d = ImageDraw.Draw(sheet)
    for i, t in enumerate(["REFERENCE", "A  legacy factory", "B  sheet-first"]):
        d.text((160 + i * CELL + 12, 16), t, font=F(24), fill=(240, 220, 170))
    for r, view in enumerate(rows):
        y = head + r * (CELL + 8)
        d.text((10, y + CELL // 2 - 12), view, font=F(22), fill=(220, 220, 220))
        if view == "uv":
            c0 = Image.new("RGB", (CELL, CELL), (30, 30, 34))
            ImageDraw.Draw(c0).text((20, CELL // 2 - 10), "UV layout on each model's atlas", font=F(16), fill=(150, 150, 150))
            cells = [c0] + [fit(Image.open(os.path.join(HERE, "uv", "%s_%s_uv.png" % (obj, v))).convert("RGB"), CELL, CELL) for v in "AB"]
        else:
            cells = [ref_cell(obj, view), model_cell(obj, "A", view), model_cell(obj, "B", view)]
        for i, c in enumerate(cells):
            sheet.paste(c, (160 + i * CELL, y))
    sheet.save(os.path.join(HERE, "compare_%s.png" % obj))
    print("sheet", obj)
