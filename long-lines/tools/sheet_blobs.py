"""Find every drawn object on a parts sheet, then crop the ones a spec names into part views.

    blender -b --factory-startup -P tools/sheet_blobs.py -- list SHEET.png OUT_overlay.png
    blender -b --factory-startup -P tools/sheet_blobs.py -- crop SHEET.png SPEC.json NAME

list: objects are the sheet's coloured drawings; section labels (grey tags with text), titles and divider
lines are left out (low colour saturation, or thin). Prints "id x0 y0 x1 y1" per object, numbered left to
right, top to bottom, and writes an overlay with the numbers, so a person (or Claude) only has to say
which number is which part's view.

crop: SPEC is {"part": {"view": id, ...}, ...} with ids from list (or [x0, y0, x1, y1] boxes). Writes
assets/source_textures/NAME/<part>/v_<view>.png on black, plus h_<view>.png for background-coloured holes
(carved solid, never painted; cut through in a part of the "parts" layout), as split_parts_sheet does.
"""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def load(sheet):
    a = np.asarray(Image.open(sheet).convert("RGB")).astype(int)
    border = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])
    vals, counts = np.unique((border // 8) * 8, axis=0, return_counts=True)
    bg = np.median(a.reshape(-1, 3)[np.abs(a.reshape(-1, 3) - vals[np.argmax(counts)]).sum(1) < 24], axis=0)
    return a, bg


def objects(a, bg):
    diff = np.abs(a - bg).sum(2)
    mx, mn = a.max(2), a.min(2)
    sat = (mx - mn) / np.maximum(mx, 1)
    drawn = diff > 36
    lab, n = ndimage.label(ndimage.binary_closing(drawn, iterations=2))
    out = []
    for i, sl in enumerate(ndimage.find_objects(lab), 1):
        m = lab[sl] == i
        h, w = m.shape
        if m.sum() < 150 or min(h, w) < 6:
            continue                                         # specks, divider lines
        s_ = float(np.median(sat[sl][m]))
        if s_ < 0.18:
            continue                                         # grey label tags, titles, rules
        out.append([sl[1].start, sl[0].start, sl[1].stop, sl[0].stop])
    # merge pieces of one drawing (a view drawn in a few parts with gaps under 3 px; neighbouring
    # views on a sheet can sit 5 px apart)
    merged = True
    while merged:
        merged = False
        for i in range(len(out)):
            for j in range(i + 1, len(out)):
                A, B = out[i], out[j]
                if A[0] - 3 <= B[2] and B[0] - 3 <= A[2] and A[1] - 3 <= B[3] and B[1] - 3 <= A[3]:
                    out[i] = [min(A[0], B[0]), min(A[1], B[1]), max(A[2], B[2]), max(A[3], B[3])]
                    out.pop(j)
                    merged = True
                    break
            if merged:
                break
    rows = sorted(out, key=lambda b: b[1])
    lines, cur = [], []
    for b in rows:                                           # reading order: rows by overlap, then x
        if cur and b[1] > max(c[3] for c in cur) - 0.3 * (b[3] - b[1]):
            lines.append(cur)
            cur = []
        cur.append(b)
    if cur:
        lines.append(cur)
    return [b for line in lines for b in sorted(line, key=lambda b: b[0])]


def crop(a, bg, box, pad=6):
    x0, y0, x1, y1 = box
    c = a[y0:y1, x0:x1].copy()
    drawn = np.abs(c - bg).sum(2) > 36
    lab, n = ndimage.label(ndimage.binary_closing(drawn, iterations=2))
    sizes = ndimage.sum(drawn, lab, range(1, n + 1))
    keep = np.isin(lab, [i + 1 for i, s_ in enumerate(sizes) if s_ >= 0.05 * sizes.max()]) & drawn
    filled = ndimage.binary_fill_holes(ndimage.binary_closing(keep, iterations=2))
    holes = ndimage.binary_opening(filled & ~ndimage.binary_dilation(keep, iterations=1)
                                   & (np.abs(c - bg).sum(2) <= 36), iterations=1)
    c[~filled] = 0
    out = np.zeros((c.shape[0] + 2 * pad, c.shape[1] + 2 * pad, 3), np.uint8)
    out[pad:-pad, pad:-pad] = c
    hm = np.zeros(out.shape[:2], bool)
    hm[pad:-pad, pad:-pad] = holes
    return out, hm


def main(argv):
    cmd, sheet = argv[0], argv[1]
    a, bg = load(sheet)
    if cmd == "list":
        obs = objects(a, bg)
        im = Image.open(sheet).convert("RGB")
        d = ImageDraw.Draw(im)
        for i, b in enumerate(obs):
            d.rectangle(b, outline=(255, 0, 255), width=2)
            d.text((b[0] + 3, b[1] + 2), str(i), fill=(0, 255, 255))
            print("%d %d %d %d %d" % (i, *b))
        im.save(argv[2])
        return
    spec, name = json.load(open(argv[2])), argv[3]
    obs = objects(a, bg)
    for part, views in spec.items():
        if part.startswith("_"):
            continue
        d_ = os.path.join(ROOT, "assets", "source_textures", name, part)
        os.makedirs(d_, exist_ok=True)
        for v, ref in views.items():
            box = obs[ref] if isinstance(ref, int) else ref
            img, holes = crop(a, bg, box)
            Image.fromarray(img).save(os.path.join(d_, "v_%s.png" % v))
            hp = os.path.join(d_, "h_%s.png" % v)
            if holes.sum() > 20:
                Image.fromarray(holes.astype(np.uint8) * 255).save(hp)
            elif os.path.exists(hp):
                os.remove(hp)
            print("CROP", part, v, img.shape[:2], "holes", int(holes.sum()))


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:])
