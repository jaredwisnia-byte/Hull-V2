"""Tests for removable construction guides (propkit/guides.py) on a synthetic painted view.

    blender -b --factory-startup --python-exit-code 1 -P tools/test_guides.py
"""
import os
import sys
import tempfile

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from propkit import guides  # noqa: E402

fails = []


def check(cond, msg):
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


d = tempfile.mkdtemp()
im = Image.new("RGB", (120, 300), (25, 27, 32))                  # dark sheet background
dr = ImageDraw.Draw(im)
dr.rectangle([30, 20, 90, 280], fill=(150, 90, 55))             # a warm painted post
for y in (120, 200):                                            # two cross-section rings
    dr.ellipse([30, y - 5, 90, y + 5], outline=(140, 215, 235), width=2)
for y in range(5, 295, 12):                                     # dashed centre line, on and off the object
    dr.line([(60, y), (60, y + 6)], fill=(140, 215, 235), width=1)
im.save(os.path.join(d, "v_front.png"))
found = guides.clean(d)
a = np.asarray(Image.open(os.path.join(d, "v_front.png")).convert("RGB")).astype(int)
inside = a[25:275, 35:85]
check(found["front"] > 200, "guide strokes found (%d px)" % found["front"])
check(int(((inside[..., 2] - inside[..., 0]) > 0).sum()) == 0, "no blue-leaning pixel left on the object")
bg = a[:, :20]
check(int((bg[..., 2] > 60).sum()) == 0, "the centre line's dashes off the object are gone too")
band = guides.ring_band(os.path.join(d, "v_front.png"), os.path.join(d, "g_front.png"))
check(band is not None and band["rings"] == 2, "two rings read (%s)" % (band and band["rings"]))
check(band is not None and abs(band["v_top"] - (115 - 20) / 261) < 0.03 and abs(band["v_bottom"] - (206 - 20) / 261) < 0.03,
      "round band from the upper ring to the lower one (%s)" % band)
# the hook rounds only the band
keep = np.ones((40, 40, 100), bool)
rep = {}
k2 = guides.round_hook(0.4, 0.6, rep)(keep.copy(), {}, 1, 1, 1)
check(k2[0, 0, 50] == False and k2[20, 20, 50] and k2[0, 0, 10] and k2[0, 0, 90], "only slices in the band become round")
print("\n%d failed" % len(fails) if fails else "\nall passed")
sys.exit(1 if fails else 0)
