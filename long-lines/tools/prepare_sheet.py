"""Prepares a supplied painted texture sheet for the prop kit (plain Python + PIL).

    python3 tools/prepare_sheet.py IMAGE LAYOUT NAME [--brand STATESMAN] [--tile x0,y0,x1,y1]

LAYOUT is a file in tools/layouts/ (car_v1, range_v1, wallpaper_v1, ...). The sheet is
scaled to the layout's size, every brand region in the layout is scrubbed (generators
like to paint real makes), each crop is written to assets/source_textures/NAME/, and a
review image marking the scrubbed regions is written next to them as _review.png.
Always look at _review.png and the crops for leftover real brand names before building.
"""
import argparse
import json
import os
import random

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def scrub(im, ops, brand):
    d = ImageDraw.Draw(im)
    marks = []
    for op in ops:
        t = op["type"]
        if t == "wash":
            x0, y0, x1, y1 = op["box"]
            dx, dy = op.get("src", [0, 20])
            patch = im.crop((x0 + dx, y0 + dy, x1 + dx, y1 + dy)).filter(ImageFilter.GaussianBlur(1.5))
            im.paste(patch, (x0, y0))
            marks.append(op["box"])
        elif t == "plate":
            x0, y0, x1, y1 = op["box"]
            base = op.get("fill", [32, 30, 28])
            rnd = random.Random(1)
            for y in range(y0, y1):
                for x in range(x0, x1):
                    v = rnd.randint(-4, 4)
                    im.putpixel((x, y), tuple(max(0, c + v) for c in base))
            text = op.get("text", "").replace("{BRAND}", brand)
            if text:
                size = max(6, int((y1 - y0) * 0.6))
                f = ImageFont.truetype(FONT, size)
                w = d.textlength(text, font=f)
                d.text(((x0 + x1) / 2 - w / 2, y0 + (y1 - y0 - size) / 2 - 1), text, font=f, fill=tuple(op.get("ink", [150, 145, 135])))
            marks.append(op["box"])
        elif t == "disc":
            cx, cy = op["center"]
            r = op["r"]
            ring = im.crop((cx + r + 2, cy - 3, cx + r + 8, cy + 3)).resize((1, 1)).getpixel((0, 0))
            d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=ring)
            d.ellipse((cx - r * 0.55, cy - r * 0.55, cx + r * 0.55, cy + r * 0.55), outline=tuple(int(c * 0.55) for c in ring), width=2)
            marks.append([cx - r, cy - r, cx + r, cy + r])
    return marks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("layout")
    ap.add_argument("name")
    ap.add_argument("--brand", default="STATESMAN")
    ap.add_argument("--tile", default=None, help="x0,y0,x1,y1 of one pattern repeat (wallpaper)")
    a = ap.parse_args()
    lay = json.load(open(os.path.join(HERE, "layouts", a.layout + ".json")))
    out = os.path.join(ROOT, "assets", "source_textures", a.name)
    os.makedirs(out, exist_ok=True)
    im = Image.open(a.image).convert("RGB")
    if "size" in lay and list(im.size) != lay["size"]:
        im = im.resize(tuple(lay["size"]), Image.LANCZOS)
    marks = scrub(im, lay.get("scrub", []), a.brand)
    im.save(os.path.join(out, "sheet_clean.png"))
    for k, box in lay.get("crops", {}).items():
        im.crop(tuple(box)).save(os.path.join(out, k + ".png"))
    for k, (box, deg) in lay.get("rotate", {}).items():
        im.crop(tuple(box)).rotate(deg, expand=True).save(os.path.join(out, k + ".png"))
    tile = a.tile or lay.get("tile")
    if tile:
        box = [int(v) for v in (tile.split(",") if isinstance(tile, str) else tile)]
        t = im.crop(tuple(box))
        t.save(os.path.join(out, "tile.png"))
        # Seam check: a 2x2 repeat for eyeballing.
        rep = Image.new("RGB", (t.width * 2, t.height * 2))
        for i in range(2):
            for j in range(2):
                rep.paste(t, (i * t.width, j * t.height))
        rep.thumbnail((800, 800))
        rep.save(os.path.join(out, "_tile_check.png"))
    rv = im.copy()
    d = ImageDraw.Draw(rv)
    for b in marks:
        d.rectangle(b, outline=(255, 0, 255), width=2)
    rv.thumbnail((1200, 1200))
    rv.save(os.path.join(out, "_review.png"))
    with open(os.path.join(out, "SOURCE.md"), "w") as f:
        f.write("# %s\n\nPainted sheet supplied by Jared, prepared with `tools/prepare_sheet.py %s %s --brand %s`.\n"
                "Brand regions scrubbed: %d. The original is not kept in the repo.\n"
                "Confirm the generator's terms allow commercial use before shipping.\n" % (a.name, a.layout, a.name, a.brand, len(marks)))
    print("prepared", a.name, "crops:", len(lay.get("crops", {})), "scrubbed:", len(marks))


if __name__ == "__main__":
    main()
