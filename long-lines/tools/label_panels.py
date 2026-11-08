"""Draws every panel the atlas line sees on a sheet, numbered, for writing a sheet spec.

    blender -b --factory-startup -P tools/label_panels.py -- SHEET.png OUT.png [MIN_AREA]
(min area 2500 px for appliance atlases, 900 for trim sheets; Blender's Python has scipy.)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from propkit.atlas import panels  # noqa: E402

a = sys.argv[sys.argv.index("--") + 1:]
sheet, out = a[0], a[1]
min_area = int(a[2]) if len(a) > 2 else 2500
try:
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 30)
except OSError:
    font = None
im = Image.open(sheet).convert("RGB")
d = ImageDraw.Draw(im)
for n, b in enumerate(panels(sheet, min_area)):
    d.rectangle(b, outline=(0, 255, 0), width=3)
    d.text((b[0] + 4, b[1] + 2), str(n), fill=(255, 0, 255), font=font)
im.save(out)
print("PANELS", out)
