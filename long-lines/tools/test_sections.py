"""Tests for inferred cross-sections (propkit/sections.py) on synthetic painted views.

    blender -b --factory-startup --python-exit-code 1 -P tools/test_sections.py
"""
import os
import sys
import tempfile

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from propkit import sections as SC  # noqa: E402

fails = []


def check(cond, msg):
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


def painted(kind, w=60, h=300, seed=0):
    """A post painted under a light from the front and a little left: a cylinder shades across its width,
    a flat face evenly (with brush noise in both)."""
    rng = np.random.default_rng(seed)
    a = np.full((h + 40, w + 40, 3), (25, 27, 32), np.uint8)
    t = np.linspace(-1, 1, w)
    if kind == "round":
        nx, nf = t, np.sqrt(1 - np.clip(t, -1, 1) ** 2)
        lum = 0.25 + 0.55 * np.clip(-0.4 * nx + 0.9 * nf, 0, None)
    else:
        lum = np.full(w, 0.62)
    col = np.array([0.62, 0.38, 0.22])
    img = (lum[None, :, None] * col[None, None, :] / 0.62 * 255 + rng.normal(0, 4, (h, w, 3)))
    a[20:20 + h, 20:20 + w] = np.clip(img, 0, 255).astype(np.uint8)
    return Image.fromarray(a)


for kind in ("round", "square"):
    d = tempfile.mkdtemp()
    for k in ("front", "right", "back", "left"):
        painted(kind, seed=hash(k) % 100).save(os.path.join(d, "v_%s.png" % k))
    # the end view: a straight post is as wide everywhere, so only its top view can name its section
    top = Image.new("RGB", (100, 100), (25, 27, 32))
    from PIL import ImageDraw
    (ImageDraw.Draw(top).ellipse if kind == "round" else ImageDraw.Draw(top).rectangle)([20, 20, 80, 80], fill=(160, 100, 60))
    top.save(os.path.join(d, "v_top.png"))
    views = {k: os.path.join(d, "v_%s.png" % k) for k in ("front", "right", "back", "left", "top")}
    half = SC.infer(views)
    if kind == "round":
        lower = [b for b in half if b["v"][0] >= 0.5]
        check(not any(b["curved"] for b in lower), "without a bottom view the lower half makes no claim")
    top.save(os.path.join(d, "v_bottom.png"))
    views["bottom"] = os.path.join(d, "v_bottom.png")
    bands = SC.infer(views)
    share = np.mean([b["curved"] for b in bands])
    if kind == "round":
        check(share > 0.8, "a painted cylinder reads as round (%.0f%% of bands)" % (share * 100))
        check(all(b["best_n"] <= 3 for b in bands if b["curved"]), "its exponent is near an ellipse")
    else:
        check(share < 0.1, "a flat-shaded post stays as the hull (%.0f%% of bands curved)" % (share * 100))
# the hook: curved bands become superellipses, others untouched
keep = np.ones((40, 30, 50), bool)
bands = [{"v": [i * SC.BAND, (i + 1) * SC.BAND], "curved": i >= 25, "best_n": 2.0, "evidence": {}} for i in range(int(1 / SC.BAND))]
rep = {}
SC.hook.__globals__["infer"] = lambda v: bands                  # feed known bands
k2 = SC.hook({}, rep)(keep.copy(), {}, 1, 1, 1)
check(k2[0, 0, 40] and not k2[0, 0, 10] and k2[20, 15, 10], "lower bands rounded, upper bands kept (v from the top)")
print("\n%d failed" % len(fails) if fails else "\nall passed")
sys.exit(1 if fails else 0)
