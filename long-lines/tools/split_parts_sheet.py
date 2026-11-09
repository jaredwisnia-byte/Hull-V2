"""Split a parts sheet into per-part views and write a hull_parts work order.

    blender -b --factory-startup -P tools/split_parts_sheet.py -- SHEET.png NAME \
        --rows "assembly:front,right,back,left,top" "seat:front,right,back,left,top" \
               "back:front,right,back,left,top" "side:front,outer,back,top,bottom" "foot:front,right,top" \
        --size 1.98 0.86 0.81 [--category sofa]

A parts sheet: the whole object in five views on the first row, then one row per part, each
row's views left to right. Rows are found by the thin separator lines (or, if there are none,
by empty bands); views within a row by empty columns. Each view is saved on black, with any drawn
ground line removed BEFORE holes are filled (otherwise the gap between legs becomes "solid").

--guide EDGE_GUIDE.png [--guide-rows ...] also splits an edge guide sheet into g_<view>.png beside
each view (propkit/edge_guide.py; a view a guide row names "side" is the part's right side).

Writes assets/source_textures/NAME/<row>/v_<view>.png and factory/orders/NAME.json (line
hull_parts, class large, tex 2048). Row names are the part kinds the line understands:
assembly (required), side (arms: outer side view, feet trimmed if a foot row exists), seat, back,
foot. Then: blender -b --factory-startup -P tools/factory.py -- build NAME
"""
import argparse
import json
import os
import sys

import numpy as np
from PIL import Image
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def bands(a, bg):
    """Row bands between separator lines, or between empty horizontal bands."""
    H = a.shape[0]
    diff = np.abs(a - bg).sum(2)
    grey = (diff > 40) & (np.abs(a[..., 0] - a[..., 2]) < 12)
    seps = [y for y in range(H) if grey[y].mean() > 0.5]
    cuts = []
    if seps:
        groups = []
        for y in seps:
            if groups and y - groups[-1][-1] <= 3:
                groups[-1].append(y)
            else:
                groups.append([y])
        edges = [0] + [v for g in groups for v in (g[0] - 2, g[-1] + 3)] + [H]
        cuts = [(edges[i], edges[i + 1]) for i in range(0, len(edges), 2)]
    else:
        occ = (diff > 36).mean(1) > 0.002
        y = 0
        while y < H:
            if occ[y]:
                s = y
                while y < H and occ[y]:
                    y += 1
                cuts.append((s, y))
            y += 1
    return [(a0, a1) for a0, a1 in cuts if a1 - a0 > 20]


def items(m, gap=12, min_w=8):
    xs = np.nonzero(m.any(0))[0]
    if not len(xs):
        return []
    out, s, p = [], xs[0], xs[0]
    for x in xs[1:]:
        if x - p > gap:
            out.append((s, p))
            s = x
        p = x
    out.append((s, p))
    return [(a, b) for a, b in out if b - a > min_w]


def main(a):
    im = Image.open(a.sheet).convert("RGB")
    arr = np.asarray(im).astype(int)
    bg = np.median(np.concatenate([arr[0], arr[-1], arr[:, 0], arr[:, -1]]), axis=0)
    rows = [r.split(":") for r in a.rows]
    found = bands(arr, bg)
    if len(found) < len(rows):
        raise SystemExit("found %d rows on the sheet, expected %d" % (len(found), len(rows)))
    out_root = os.path.join(ROOT, "assets", "source_textures", a.name)
    report = {}
    for (y0, y1), (part, views) in zip(found, rows):
        views = views.split(",")
        m = ndimage.binary_opening(np.abs(arr[y0:y1] - bg).sum(2) > 36, iterations=1)
        its = items(m)
        if len(its) != len(views):
            print("WARNING row %s: %d views found, %d named" % (part, len(its), len(views)))
        os.makedirs(os.path.join(out_root, part), exist_ok=True)
        report[part] = []
        for (x0, x1), v in zip(its, views):
            ys = np.nonzero(m[:, x0:x1 + 1].any(1))[0]
            box = (int(x0) - 14, int(y0 + ys[0]) - 14, int(x1) + 15, int(y0 + ys[-1]) + 15)
            crop = np.asarray(im.crop(box)).astype(int)
            mm = np.abs(crop - bg).sum(2) > 36
            fr = mm.mean(1)                         # ground lines out first, then fill holes
            for yy in range(mm.shape[0]):
                ab, be = fr[max(0, yy - 6):max(0, yy - 2)], fr[yy + 3:yy + 7]
                if fr[yy] > 0.6 and (not len(ab) or ab.max() < 0.3) and (not len(be) or be.max() < 0.3):
                    mm[max(0, yy - 2):yy + 3] = False
            mm = ndimage.binary_fill_holes(ndimage.binary_closing(mm, iterations=2))
            crop[~mm] = 0
            Image.fromarray(crop.astype(np.uint8)).save(os.path.join(out_root, part, "v_%s.png" % v))
            report[part].append([v, list(box)])
        print(part, report[part])
    if a.guide:
        # the edge guide sheet: split the same way; crops keep their coloured lines (g_<view>.png)
        gim = Image.open(a.guide).convert("RGB")
        garr = np.asarray(gim).astype(int)
        gbg = np.median(np.concatenate([garr[0], garr[-1], garr[:, 0], garr[:, -1]]), axis=0)
        grows = [r.split(":") for r in (a.guide_rows or a.rows)]
        for (y0, y1), (part, views) in zip(bands(garr, gbg), grows):
            views = views.split(",")
            m = ndimage.binary_opening(np.abs(garr[y0:y1] - gbg).sum(2) > 36, iterations=1)
            its = items(m)
            if len(its) != len(views):
                print("WARNING guide row %s: %d views found, %d named" % (part, len(its), len(views)))
            for (x0, x1), v in zip(its, views):
                ys = np.nonzero(m[:, x0:x1 + 1].any(1))[0]
                box = (int(x0) - 6, int(y0 + ys[0]) - 6, int(x1) + 7, int(y0 + ys[-1]) + 7)
                gim.crop(box).save(os.path.join(out_root, part, "g_%s.png" % v))
            print("guide", part, len(its), "views")
    W, D, H = a.size
    order = {"name": a.name, "category": a.category, "line": "hull_parts", "source": os.path.basename(a.sheet),
             "class": "large", "tex": 2048, "status": "pending", "views_folder": a.name, "assembly": "assembly",
             "parts": {r[0]: r[0] for r in rows if r[0] != "assembly"},
             "width_m": W, "depth_m": D, "height_m": H, "rough": a.rough, "res": 150, "part_res": 100,
             "edge_guide": bool(a.guide),
             "assumptions": ["size given on the command line"], "notes": "parts sheet split: " + json.dumps(report)}
    path = os.path.join(ROOT, "factory", "orders", a.name + ".json")
    json.dump(order, open(path, "w"), indent=1)
    print("ORDER", path)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sheet")
    ap.add_argument("name")
    ap.add_argument("--rows", nargs="+", required=True, help="row:view,view,... top to bottom")
    ap.add_argument("--size", nargs=3, type=float, required=True, metavar=("W", "D", "H"))
    ap.add_argument("--category", default="furniture")
    ap.add_argument("--rough", type=float, default=0.85, help="0.85 for fabric")
    ap.add_argument("--guide", help="edge guide sheet (same layout, coloured lines: red cut, cyan outline, "
                                     "yellow rounded, purple crease)")
    ap.add_argument("--guide-rows", nargs="+", help="guide rows if they differ, e.g. seat:front,side,top")
    main(ap.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]))
