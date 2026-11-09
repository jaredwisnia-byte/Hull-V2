"""Contact sheet of render_modes.py output: one row per camera, one column per mode.
    python3 tools/diag/sheet.py DIR OUT.jpg [cam,cam] [--scale 0.5]"""
import os
import sys

from PIL import Image, ImageDraw

d, out = sys.argv[1], sys.argv[2]
modes = ["textured", "clay", "wire", "albedo", "normals", "facets", "depth"]
cams = sys.argv[3].split(",") if len(sys.argv) > 3 and not sys.argv[3].startswith("--") else \
    sorted({f.split("_")[0] for f in os.listdir(d) if f.endswith(".png")})
scale = float(sys.argv[sys.argv.index("--scale") + 1]) if "--scale" in sys.argv else 0.4
ims = [[Image.open(os.path.join(d, "%s_%s.png" % (c, m))).convert("RGB") for m in modes] for c in cams]
w, h = int(ims[0][0].width * scale), int(ims[0][0].height * scale)
sheet = Image.new("RGB", (w * len(modes), (h + 22) * len(cams)), (20, 20, 26))
dr = ImageDraw.Draw(sheet)
for r, row in enumerate(ims):
    for c, im in enumerate(row):
        sheet.paste(im.resize((w, h)), (c * w, r * (h + 22) + 22))
        dr.text((c * w + 6, r * (h + 22) + 5), "%s / %s" % (cams[r], modes[c]), fill=(240, 220, 180))
sheet.save(out, quality=88)
