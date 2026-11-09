"""Construction guides drawn on a painted sheet: read them, then take them out of the painting.

An artist (or ChatGPT) may draw removable guides over the views in one guide colour (cyan on the
updated leg sheet, with a legend): centre lines, outline curves, dashed side profiles, and cross-section
rings (ellipses drawn across a part) meaning "this is round here". The guides carry shape information but
must never reach the model or its paint:

  clean(folder)   every v_<view>.png: guide pixels found by colour (much bluer than anything painted, and
                  bright), saved as g_<view>.png, and painted out of v_<view>.png from the surrounding
                  paint (nearest unguided pixel, then a light blur inside the filled strip)
  ring_band(...)  rows of a view where cross-section rings are drawn: horizontal guide strokes inside the
                  object, away from the centre line. The band from the highest ring to the lowest is round
  round_band(...) the widest band at least two views' rings agree on, with the bottom view's roundness as a check
  round_hook(...) a hull voxel_hook: every slice in that band becomes the ellipse inscribed in the slice's
                  own extent (width from the front, depth from the side), as a lathe would turn it

Intake: crop the views (tools/sheet_blobs.py crop), then
    blender -b --factory-startup -P tools/propkit/guides.py -- clean assets/source_textures/<name>/<part>
and give the order "hull": {"guides": true}.
"""
import os

import numpy as np
from PIL import Image
from scipy import ndimage

BLUE_OVER_RED = 45      # a guide pixel is this much bluer than red ...
BRIGHT = 110            # ... and at least this bright in blue (the dark background is slightly blue too)
FAINT_LEAN = 5          # faint stroke: blue above red ...
FAINT_BRIGHT = 70       # ... and brighter than the dark background
FRINGE_PX = 3           # px around a stroke searched for its anti-aliased fringe
FRINGE_LEAN = -25       # fringe: blue within this of red (painted wood has red far above blue)
RING_SPAN = 0.3         # a ring runs across at least this share of the object's width at its row
RING_PAIR = 0.045       # arcs closer than this share of the height belong to one ring
EDGE = 0.03             # rings this close to the object's top or bottom edge are ignored
RING_RUN = 9            # px: a ring stroke stays this long horizontally (centre lines and outlines do not)


def guide_mask(rgb):
    """Guide strokes plus their anti-aliased fringe: the strict colour test finds the strokes; pixels just
    beside them that lean blue at all (paint here is warm: red well above blue) are fringe."""
    a = rgb.astype(int)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    strong = (b - r > BLUE_OVER_RED) & (b > BRIGHT) & (g - r > BLUE_OVER_RED * 0.6)
    # faint strokes (thin rings, dashes) fail the strict test but still lean blue, which warm paint never
    # does; the dark background leans slightly blue too, so they must be brighter than it
    faint = (b - r > FAINT_LEAN) & (b > FAINT_BRIGHT)
    core = strong | faint
    near = ndimage.binary_dilation(core, iterations=FRINGE_PX)
    return core | (near & (b - r > FRINGE_LEAN))


def paint_out(rgb, mask):
    """Fill guide pixels from the nearest unguided paint, then soften the filled strip."""
    m = ndimage.binary_dilation(mask, iterations=1)
    if not m.any():
        return rgb
    idx = ndimage.distance_transform_edt(m, return_distances=False, return_indices=True)
    out = rgb[tuple(idx)].astype(float)
    soft = np.stack([ndimage.gaussian_filter(out[..., c], 1.2) for c in range(3)], -1)
    out[m] = soft[m]
    return np.clip(out, 0, 255).astype(np.uint8)


def clean(folder):
    """g_<view>.png from every v_<view>.png's guides; v_<view>.png painted clean. Returns {view: guide px}."""
    found = {}
    for fn in sorted(os.listdir(folder)):
        if not (fn.startswith("v_") and fn.endswith(".png")):
            continue
        p = os.path.join(folder, fn)
        rgb = np.asarray(Image.open(p).convert("RGB"))
        g = guide_mask(rgb)
        Image.fromarray((g * 255).astype(np.uint8)).save(os.path.join(folder, "g_" + fn[2:]))
        Image.fromarray(paint_out(rgb, g)).save(p)
        found[fn[2:-4]] = int(g.sum())
    return found


def ring_band(view_png, guide_png):
    """(v_top, v_bottom) of the drawn cross-section rings as fractions of the view's object box (v from the
    top), and the ring rows; or None when the view has no rings."""
    from .hull import silhouette
    m, _, (x0, y0, x1, y1) = silhouette(view_png, with_box=True)
    g = np.asarray(Image.open(guide_png).convert("L")) > 127
    g = g[y0:y0 + m.shape[0], x0:x0 + m.shape[1]]
    inside = ndimage.binary_dilation(m, iterations=2)
    horiz = ndimage.binary_opening(g & inside, structure=np.ones((1, RING_RUN), bool))
    width = np.maximum(m.sum(1), 1)
    rows = np.nonzero(horiz.sum(1) >= np.maximum(RING_RUN, RING_SPAN * width))[0]
    if len(rows) < 2:
        return None
    # rings: groups of nearby rows
    hh = m.shape[0]
    rows = rows[(rows > EDGE * hh) & (rows < (1 - EDGE) * hh)]     # the outline's own top and bottom are not rings
    if len(rows) < 2:
        return None
    # one drawn ellipse shows as two horizontal arcs (its near and far side): arcs this close are one ring
    groups = np.split(rows, np.nonzero(np.diff(rows) > max(3, RING_PAIR * hh))[0] + 1)
    centres = [float(gr.mean()) for gr in groups]
    hh = m.shape[0]
    return {"v_top": float(groups[0][0]) / hh, "v_bottom": float(groups[-1][-1] + 1) / hh,
            "rings": len(groups), "ring_v": [round(c / hh, 3) for c in centres]}


def round_hook(v_top, v_bottom, report):
    """voxel_hook: slices with v in [v_top, v_bottom] (v from the top of the object) become ellipses."""
    def hook(keep, views, W, D, H):
        nx, ny, nz = keep.shape
        zs = (np.arange(nz) + 0.5) / nz
        band = np.nonzero(((1 - zs) >= v_top) & ((1 - zs) <= v_bottom))[0]
        xs = np.arange(nx)[:, None]
        ys = np.arange(ny)[None, :]
        changed = 0
        for iz in band:
            s = keep[:, :, iz]
            if not s.any():
                continue
            ix, iy = np.nonzero(s)
            cx, cy = (ix.min() + ix.max()) / 2, (iy.min() + iy.max()) / 2
            ax, ay = (ix.max() - ix.min() + 1) / 2, (iy.max() - iy.min() + 1) / 2
            ell = ((xs - cx) / ax) ** 2 + ((ys - cy) / ay) ** 2 <= 1.0
            changed += int((s & ~ell).sum())
            keep[:, :, iz] = s & ell
        report["round_band"] = {"v_top": round(v_top, 3), "v_bottom": round(v_bottom, 3), "slices": int(len(band)),
                                "voxels_removed": changed}
        return keep
    return hook


def round_band(folder, views=("front", "back", "left", "right")):
    """The round band the views' rings agree on (the widest band two views share); plus whether the
    bottom view (if any) is round, as a check. Returns (v_top, v_bottom, report) or None."""
    from .hull import silhouette
    from .revolve import round_body
    bands = {}
    for k in views:
        vp, gp = os.path.join(folder, "v_%s.png" % k), os.path.join(folder, "g_%s.png" % k)
        if os.path.exists(vp) and os.path.exists(gp):
            b = ring_band(vp, gp)
            if b:
                bands[k] = b
    if not bands:
        return None
    # the widest band at least two views agree on (one view's stray stroke cannot widen it; a view that
    # draws no ring that low cannot shorten it)
    tops = sorted(b["v_top"] for b in bands.values())
    bots = sorted((b["v_bottom"] for b in bands.values()), reverse=True)
    vt = float(tops[1] if len(tops) > 1 else tops[0])
    vb = float(bots[1] if len(bots) > 1 else bots[0])
    rep = {"views": {k: [round(b["v_top"], 3), round(b["v_bottom"], 3), b["rings"]] for k, b in bands.items()}}
    bp = os.path.join(folder, "v_bottom.png")
    if os.path.exists(bp):
        rb = round_body(silhouette(bp)[0])
        rep["bottom_view_round"] = bool(rb and rb.get("round"))
        rep["bottom_view_iou"] = round(float(rb["iou"]), 3) if rb else None
    return vt, vb, rep


if __name__ == "__main__":
    import json
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    argv = sys.argv[sys.argv.index("--") + 1:]
    if argv[0] == "clean":
        print("GUIDES", json.dumps(clean(argv[1])))
