"""Final renders of a shipped library prop: the assembly line's last station.

    blender -b --factory-startup -P tools/render_turnaround.py -- NAME [OUT_DIR]

Writes OUT_DIR/NAME.png (default docs/renders/): front, right, back, left, top and three-quarter views
with its textures, plus a clay three-quarter (shape only), on one sheet with its size, triangles, build time
and quality-gate result. Orthographic cameras framed on the prop's own size, so any prop works.
"""
import json
import math
import os
import tempfile
import sys

import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
argv = sys.argv[sys.argv.index("--") + 1:]
name = argv[0]
out_dir = argv[1] if len(argv) > 1 else os.path.join(ROOT, "docs", "renders")
os.makedirs(out_dir, exist_ok=True)
base = os.path.join(ROOT, "assets", "props", name, name)
CAMS = [("front", 0, 0), ("right", 90, 0), ("back", 180, 0), ("left", -90, 0), ("top", 0, 89.9),
        ("three-quarter", -35, 18)]
PX = 520

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=base + ".glb")
objs = [o for o in bpy.data.objects if o.type == "MESH"]
bpy.context.view_layer.update()
lo, hi = Vector((1e9,) * 3), Vector((-1e9,) * 3)
for o in objs:
    for c in o.bound_box:
        w = o.matrix_world @ Vector(c)
        lo, hi = Vector(map(min, lo, w)), Vector(map(max, hi, w))
centre, size = (lo + hi) / 2, hi - lo
sc = bpy.context.scene
sc.render.engine = "CYCLES"
sc.cycles.use_denoising = False
sc.cycles.samples = 48
sc.render.resolution_x = sc.render.resolution_y = PX
world = bpy.data.worlds.new("w")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.30, 0.32, 0.36, 1)
world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.9
sc.world = world
for nm, d, e in (("key", (-0.6, -0.9, 0.7), 3.2), ("fill", (0.8, -0.2, 0.4), 1.2), ("rim", (0.2, 1, 0.6), 1.6),
                 ("under", (0, -0.3, -1), 0.4)):
    L = bpy.data.lights.new(nm, "SUN")
    L.energy, L.angle = e, 0.15
    lo_ = bpy.data.objects.new(nm, L)
    sc.collection.objects.link(lo_)
    lo_.rotation_euler = (-Vector(d)).to_track_quat("-Z", "Y").to_euler()
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
sc.collection.objects.link(cam)
sc.camera = cam
cam.data.type = "ORTHO"
cam.data.clip_end = 100


def material(kind):
    m = bpy.data.materials.new(kind)
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    if kind == "clay":
        b.inputs["Base Color"].default_value = (0.6, 0.6, 0.6, 1)
        b.inputs["Roughness"].default_value = 0.6
        return m

    def tex(k, cs):
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = bpy.data.images.load(base + "_%s.png" % k)
        n.image.colorspace_settings.name = cs
        return n
    nt.links.new(tex("albedo", "sRGB").outputs["Color"], b.inputs["Base Color"])
    nm = nt.nodes.new("ShaderNodeNormalMap")
    nt.links.new(tex("normal", "Non-Color").outputs["Color"], nm.inputs["Color"])
    nt.links.new(nm.outputs["Normal"], b.inputs["Normal"])
    sep = nt.nodes.new("ShaderNodeSeparateColor")
    nt.links.new(tex("orm", "Non-Color").outputs["Color"], sep.inputs["Color"])
    nt.links.new(sep.outputs["Green"], b.inputs["Roughness"])
    nt.links.new(sep.outputs["Blue"], b.inputs["Metallic"])
    return m


def shoot(az, el, path):
    a, e = math.radians(az), math.radians(el)
    d = Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e)))
    # frame: the box's extent across the view, with a margin
    right = Vector((math.cos(a), math.sin(a), 0))
    up = d.cross(right).normalized() if abs(el) < 89 else Vector((0, 1, 0))
    corners = [Vector((x, y, z)) for x in (lo.x, hi.x) for y in (lo.y, hi.y) for z in (lo.z, hi.z)]
    span = max(max(abs((c - centre).dot(right)) for c in corners), max(abs((c - centre).dot(up)) for c in corners))
    cam.data.ortho_scale = 2.25 * span
    cam.location = centre + d * (3 * max(size))
    cam.rotation_euler = (-d).to_track_quat("-Z", "Y").to_euler()
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)


tmp = os.path.join(tempfile.gettempdir(), "_turn_" + name)
os.makedirs(tmp, exist_ok=True)
shots = []
for kind in ("textured", "clay"):
    m = material(kind)
    for o in objs:
        o.data.materials.clear()
        o.data.materials.append(m)
    for label, az, el in CAMS if kind == "textured" else [("clay, three-quarter", -35, 18)]:
        p = os.path.join(tmp, "%s_%s.png" % (kind, label.replace(" ", "_").replace(",", "")))
        shoot(az, el, p)
        shots.append((label, p))

# one sheet: seven views and a caption
from PIL import Image, ImageDraw, ImageFont  # noqa: E402
try:
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
    bold = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)
except OSError:
    font = ImageFont.load_default(size=18)
    bold = ImageFont.load_default(size=24)
lib = json.load(open(os.path.join(ROOT, "assets", "props", "library.json"))).get(name, {})
ledger = [json.loads(l) for l in open(os.path.join(ROOT, "factory", "ledger.jsonl")) if '"%s"' % name in l]
last = next((r for r in reversed(ledger) if r.get("op") == "build" and r.get("name") == name), {})
cols, T = 4, 360
sheet = Image.new("RGB", (cols * T, 70 + 2 * T + 40), (246, 244, 239))
d = ImageDraw.Draw(sheet)
s = lib.get("size") or [0, 0, 0]
d.text((14, 12), name, fill=(30, 30, 30), font=bold)
d.text((14, 44), "%.0f x %.0f x %.0f mm (W x H x D)   %s triangles   built in %s s   quality gate: %s" % (
    s[0] * 1000, s[1] * 1000, s[2] * 1000, lib.get("tris", "?"), last.get("seconds", "?"),
    "pass" if last.get("pass") else "FAIL"), fill=(70, 70, 70), font=font)
for i, (label, p) in enumerate(shots):
    im = Image.open(p).convert("RGB").resize((T, T))
    x, y = (i % cols) * T, 70 + (i // cols) * T
    sheet.paste(im, (x, y))
    d.text((x + 10, y + 8), label, fill=(240, 240, 240), font=font)
out = os.path.join(out_dir, name + ".png")
sheet.save(out)
print("TURNAROUND", out)
