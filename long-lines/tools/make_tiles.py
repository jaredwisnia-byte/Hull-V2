"""Turns painted texture images into seamless tiles and registers them as surfaces.

    python3 tools/make_tiles.py SPEC.json

SPEC: {"source_dir": "...", "surfaces": {name: {"src": file, "box": [x0,y0,x1,y1] | null,
       "kind": "floor"|"wall", "repeat_m": metres per tile, "grid": [cols, rows, inset]?}}}
A "grid" entry splits a swatch board into name_00, name_01, ... Each tile is cropped
square, edge-blended so it repeats without seams, saved to assets/surfaces/<name>.png
and recorded in data/surfaces.json, where recipes look them up by name (mats.painted, facade).
"""
import json
import os
import sys

import numpy as np
from PIL import Image

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
OUT = os.path.join(ROOT, "assets", "surfaces")
CATALOG = os.path.join(ROOT, "data", "surfaces.json")

WEAR = {
    "floor": {"grime": 0.45},
    "wall": {"grime": 0.45, "floor_grime": 0.4, "cracks": 0.35, "peel": 0.45, "stains": 0.45},
    "carpet": {"grime": 0.55},
}


def seamless(im, blend=0.22):
    """Cross-fades the tile with a half-offset copy of itself near the edges, so
    opposite edges match. Works well on painted, non-photographic surfaces."""
    a = np.asarray(im).astype(np.float32)
    h, w = a.shape[:2]
    shifted = np.roll(np.roll(a, h // 2, 0), w // 2, 1)  # roll is the point here: wrap-around
    y = np.abs(np.linspace(-1, 1, h))[:, None]
    x = np.abs(np.linspace(-1, 1, w))[None, :]
    edge = np.clip((np.maximum(x, y) - (1 - 2 * blend)) / (2 * blend), 0, 1)
    edge = edge * edge * (3 - 2 * edge)
    out = a * (1 - edge[..., None]) + shifted * edge[..., None]
    return Image.fromarray(out.clip(0, 255).astype(np.uint8))


def period(rows, lo=24):
    """Strongest repeat length along axis 1 of a 2-D array, from autocorrelations
    of individual rows averaged together (averaging rows first would cancel a
    checkerboard out)."""
    n = rows.shape[1]
    x = rows - rows.mean(1, keepdims=True)
    f = np.fft.rfft(x, 2 * n, axis=1)
    ac = np.fft.irfft(f * np.conj(f), axis=1)[:, :n].mean(0)
    ac[:lo] = -1e18
    return int(np.argmax(ac[: n // 2 + 1]))


def periodic_crop(im):
    """For regular grids (checkerboards, tiles): crop a whole number of repeats,
    measured by autocorrelation, so the tile wraps exactly without blending.
    Returns None if no clean repeat is found."""
    g = np.asarray(im.convert("L")).astype(np.float32)
    px = period(g[::4])
    py = period(g.T[::4])
    if px < 24 or py < 24:
        return None
    w = (im.width - 4) // px * px
    h = (im.height - 4) // py * py
    k = min(w // px, h // py)
    w, h = k * px, k * py
    if w < 64 or h < 64:
        return None
    return im.crop((2, 2, 2 + w, 2 + h))


def square(im, box=None):
    if box:
        im = im.crop(tuple(box))
    s = min(im.size)
    l = (im.width - s) // 2
    t = (im.height - s) // 2
    return im.crop((l, t, l + s, t + s))


def make(name, im, kind, repeat_m, catalog, size=1024, periodic=False):
    crop = periodic_crop(im) if periodic else None
    if crop is not None:
        tile = crop.resize((size, size), Image.LANCZOS)
    else:
        tile = seamless(square(im)).resize((size, size), Image.LANCZOS)
    os.makedirs(OUT, exist_ok=True)
    # JPEG: painted tiles show no visible loss and are a fifth the size of PNG.
    tile.save(os.path.join(OUT, name + ".jpg"), quality=90)
    catalog[name] = {"file": "assets/surfaces/%s.jpg" % name, "kind": kind, "repeat_m": repeat_m,
                     "wear": WEAR.get(kind, WEAR["floor"])}


def main():
    spec = json.load(open(sys.argv[1]))
    src = spec["source_dir"]
    catalog = json.load(open(CATALOG)) if os.path.exists(CATALOG) else {}
    for name, s in spec["surfaces"].items():
        im = Image.open(os.path.join(src, s["src"])).convert("RGB")
        if s.get("box"):
            im = im.crop(tuple(s["box"]))
        if "grid" in s:
            cols, rows, inset = s["grid"]
            cw, ch = im.width / cols, im.height / rows
            k = 0
            for r in range(rows):
                for c in range(cols):
                    cell = im.crop((int(c * cw + inset * cw), int(r * ch + inset * ch), int((c + 1) * cw - inset * cw), int((r + 1) * ch - inset * ch)))
                    make("%s_%02d" % (name, k), cell, s["kind"], s["repeat_m"], catalog, 512)
                    k += 1
        else:
            make(name, im, s["kind"], s["repeat_m"], catalog, periodic=s.get("periodic", False))
        print("tile", name)
    with open(CATALOG, "w") as f:
        json.dump(dict(sorted(catalog.items())), f, indent=1)


if __name__ == "__main__":
    main()
