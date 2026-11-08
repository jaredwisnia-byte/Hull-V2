"""Atlas line: an appliance (or any boxy object) from a painted parts atlas.

Jared's atlas sheets lay an object out flat: front panels, sides, top, back, kick
plate, plus loose parts, on a dark background. The machine finds every panel
(`panels`); a work order says which numbered panel is which face, in one line:

    {"front": [[15], [32]], "side": 26, "top": 0, "back": null, "backguard": 1,
     "kick": 24, "burners": 2, "controls": [1]}

front is a list of rows, top to bottom, each a list of panels left to right (a
side-by-side fridge is [[0, 1]]). Panel proportions give the real proportions: the
category gives the height, the front rows give the width, the side panel the depth.
Each front panel is its own slab, standing a little proud with a bevelled edge, so
doors and drawers read as separate parts. Knobs on control panels are found with the
hull line's circle detector and given depth by part_rules (same logic as the TV).
"""
import math
import os

import numpy as np
from PIL import Image

BG_MAX = 48


def panels(sheet, min_area=2500):
    """Every drawn panel on the sheet: [(x0, y0, x1, y1)] in reading order. The
    numbering is stable for a given sheet, so work orders can refer to it."""
    from scipy import ndimage
    a = np.asarray(Image.open(sheet).convert("RGB"))
    fg = ndimage.binary_fill_holes(ndimage.binary_opening(a.max(-1) > BG_MAX, iterations=2))
    lab, n = ndimage.label(fg)
    boxes = []
    for sl in ndimage.find_objects(lab):
        h, w = sl[0].stop - sl[0].start, sl[1].stop - sl[1].start
        if h * w > min_area:
            boxes.append((sl[1].start, sl[0].start, sl[1].stop, sl[0].stop))
    return sorted(boxes, key=lambda b: (b[1] // 60, b[0]))


def _crop(sheet_img, box, out_dir, key, inset=2):
    x0, y0, x1, y1 = box
    p = os.path.join(out_dir, "p_%s.png" % key)
    sheet_img.crop((x0 + inset, y0 + inset, x1 - inset, y1 - inset)).save(p)
    return p


def _slab(size, loc, png, rough, name, bevel=0.006):
    """A panel slab facing -y with the painting on its front (and smeared on its edges)."""
    from . import core, mats
    s = core.box(size, loc, mats.image(png, rough=rough, grime=0.3, name="atl_" + os.path.basename(png) + name),
                 bevel=bevel, name=name)
    core.planar_uv(s, 0, 2, size[0], size[2])
    return s


def _face(png, size, loc, rot, rough, name):
    """A thin skin on a body face (side, top, back) carrying that face's painting."""
    from . import core, mats
    s = core.box(size, loc, mats.image(png, rough=rough, grime=0.35, name="atl_" + os.path.basename(png) + name),
                 bevel=0.002, rot=rot, name=name)
    core.planar_uv(s, 0, 2, size[0], size[2])
    return s


def appliance(sheet, order, src_dir, height_m, rough=0.45):
    """Builds the object (front faces -y, standing on z = 0). Returns measurements."""
    from . import core, mats, part_rules
    from .hull import detect_circles
    boxes = panels(sheet)
    img = Image.open(sheet).convert("RGB")
    os.makedirs(src_dir, exist_ok=True)

    def pw(i):
        b = boxes[i]
        return b[2] - b[0], b[3] - b[1]

    # Real proportions from the panels: rows share one width, heights follow.
    rows = order["front"]
    row_h_over_w = []
    for row in rows:
        ws = sum(pw(i)[0] for i in row)
        row_h_over_w.append(max(pw(i)[1] for i in row) / ws)
    kick_h = 0.0
    if order.get("kick") is not None:
        kw, kh = pw(order["kick"])
        kick_h_over_w = kh / kw
    else:
        kick_h_over_w = 0.0
    body_h = height_m
    Wv = body_h / (sum(row_h_over_w) + kick_h_over_w)   # width implied by the painting
    W = order.get("width_m") or Wv                      # a real-world width wins if given
    kick_h = kick_h_over_w * Wv
    # Depth is a real-world fact of the category (painted side panels are not drawn
    # to scale on these sheets): order > category > a fraction of the width.
    D = order.get("depth_m") or order.get("cat_depth_m") or 0.65 * W
    plain = mats.paint(tuple(c / 255 for c in np.asarray(img.crop(boxes[rows[0][0]])).reshape(-1, 3).mean(0)), name="atl_body")
    core.box((W - 0.004, D - 0.004, body_h - 0.004), (0, D / 2, body_h / 2), plain, bevel=0.01, name="body")

    made, knobs = [], []
    z = body_h
    for r, row in enumerate(rows):
        h = row_h_over_w[r] * Wv
        x = -W / 2
        total = sum(pw(i)[0] for i in row)
        for i in row:
            w = pw(i)[0] / total * W
            png = _crop(img, boxes[i], src_dir, "f%d" % i)
            gap = 0.004
            _slab((w - gap, 0.022, h - gap), (x + w / 2, -0.011, z - h / 2), png, rough, "panel%d" % i)
            made.append(i)
            if i in order.get("controls", []):
                knobs += _knobs(png, w, h, x + w / 2, -0.022, z - h / 2)
            x += w
        z -= h
    if order.get("kick") is not None:
        png = _crop(img, boxes[order["kick"]], src_dir, "kick")
        _slab((W - 0.01, 0.012, kick_h), (0, 0.01, kick_h / 2), png, rough, "kick", bevel=0.003)
    if order.get("side") is not None:
        png = _crop(img, boxes[order["side"]], src_dir, "side")
        for sx, nm in ((1, "side_r"), (-1, "side_l")):
            _face(png, (D - 0.01, 0.006, body_h - kick_h - 0.004), (sx * (W / 2), D / 2, (body_h + kick_h) / 2),
                  (0, 0, math.radians(90 * sx)), 0.5, nm)
    if order.get("top") is not None:
        png = _crop(img, boxes[order["top"]], src_dir, "top")
        _face(png, (W - 0.004, 0.006, D - 0.004), (0, D / 2, body_h), (math.radians(-90), 0, 0), rough, "top")
    if order.get("back") is not None:
        png = _crop(img, boxes[order["back"]], src_dir, "back")
        _face(png, (W - 0.01, 0.006, body_h - 0.01), (0, D, body_h / 2), (0, 0, math.radians(180)), 0.6, "back")
    if order.get("backguard") is not None:     # range control panel standing at the rear of the top
        bw, bh = pw(order["backguard"])
        gh = bh / bw * W
        png = _crop(img, boxes[order["backguard"]], src_dir, "guard")
        _slab((W, 0.05, gh), (0, D - 0.025, body_h + gh / 2), png, rough, "backguard", bevel=0.008)
        if order["backguard"] in order.get("controls", []):
            knobs += _knobs(png, W, gh, 0, D - 0.05, body_h + gh / 2)
    if order.get("burners") is not None:       # four burners at the quarter points of the cooktop
        png = _crop(img, boxes[order["burners"]], src_dir, "burner")
        r = min(W, D) * 0.16
        for bx in (-0.25, 0.25):
            for by in (0.3, 0.62):
                b = core.cyl(r, 0.012, (bx * W, by * D, body_h + 0.009), mats.image(png, rough=0.6, name="atl_burner"),
                             32, bevel=0.002, name="burner")
                core.planar_uv(b, 0, 1, 2 * r, 2 * r)
    for o in core.PARTS:          # library convention: origin at the bottom centre
        o.location.y -= D / 2
    return {"width_m": round(W, 3), "depth_m": round(D, 3), "height_m": round(body_h, 3),
            "panels": made, "knobs": knobs}


def _knobs(png, w, h, cx, y_front, cz):
    """Knobs painted on a control panel become fluted cylinders standing proud by
    what a real knob of that size would (part_rules), capped with the painting."""
    from . import core, mats, part_rules
    from .hull import detect_circles
    im = Image.open(png)
    fw, fh = im.size
    out = []
    mat = mats.image(png, rough=0.4, grime=0.2, name="atl_knob_" + os.path.basename(png))
    for px, py, pr in detect_circles(im):
        d = 2 * pr / fw * w
        part = part_rules.classify_circle(d)
        if part is None:
            continue
        d = min(d, part_rules.RULES[part]["max_real"])
        pr = d / 2 / w * fw
        depth = part_rules.depth_for(part, d)
        x = cx + (px / fw - 0.5) * w
        z = cz + (0.5 - py / fh) * h
        k = core.cyl(d / 2 * 0.95, depth, (x, y_front - depth / 2 + 0.001, z), mat, 32,
                     (math.radians(90), 0, 0), bevel=d * 0.08, flutes=part_rules.RULES[part]["flutes"])
        attr = k.data.color_attributes.new("label_uv", "FLOAT_COLOR", "CORNER")
        for li, loop in enumerate(k.data.loops):
            v = k.data.vertices[loop.vertex_index].co
            attr.data[li].color = ((px + v.x / (d / 2) * pr) / fw, 1 - (py - v.y / (d / 2) * pr) / fh, 0, 1)
        out.append({"part": part, "diameter_mm": round(d * 1000, 1), "depth_mm": round(depth * 1000, 1)})
    return out
