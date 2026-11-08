"""Renders a labelled grid of baked library props for review.
    blender -b --factory-startup -P tools/contact_sheet.py -- OUT.png [names|all|--tag T] [--size 300]
"""
import json
import math
import os
import sys

import bpy
from mathutils import Vector
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.normpath(os.path.join(HERE, "..", "assets", "props"))
args = sys.argv[sys.argv.index("--") + 1:]
out, rest = args[0], args[1:]
size = 300
if "--size" in rest:
    size = int(rest[rest.index("--size") + 1])
manifest = json.load(open(os.path.join(LIB, "library.json")))
names = []
i = 0
while i < len(rest):
    a = rest[i]
    if a == "all":
        names += sorted(manifest)
    elif a == "--tag":
        names += sorted(n for n, e in manifest.items() if rest[i + 1] in e["tags"]); i += 1
    elif a == "--size":
        i += 1
    else:
        names.append(a)
    i += 1

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.engine = "CYCLES"
sc.cycles.samples = 12
sc.cycles.use_denoising = False
sc.render.resolution_x = sc.render.resolution_y = size
sc.view_settings.view_transform = "Standard"
w = bpy.data.worlds.new("w")
sc.world = w
w.use_nodes = True
w.node_tree.nodes["Background"].inputs["Color"].default_value = (0.09, 0.1, 0.12, 1)
for nm, loc, e, col in (("key", (-2, -3, 3), 260, (1, 0.86, 0.7)), ("fill", (3, -1, 1.5), 90, (0.6, 0.72, 0.95))):
    l = bpy.data.objects.new(nm, bpy.data.lights.new(nm, "AREA"))
    l.data.energy, l.data.size, l.data.color = e, 2.5, col
    l.location = loc
    l.rotation_euler = (Vector((0, 0, 0.3)) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    sc.collection.objects.link(l)
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
sc.collection.objects.link(cam)
sc.camera = cam
tiles = []
for n in names:
    d = os.path.join(LIB, n)
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=os.path.join(d, n + ".glb"))
    objs = [o for o in bpy.data.objects if o not in before and o.type == "MESH"]
    m = bpy.data.materials.new(n)
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    def tex(fn, cs):
        t = nt.nodes.new("ShaderNodeTexImage")
        t.image = bpy.data.images.load(os.path.join(d, fn))
        t.image.colorspace_settings.name = cs
        return t
    nt.links.new(tex(n + "_albedo.png", "sRGB").outputs[0], b.inputs["Base Color"])
    sep = nt.nodes.new("ShaderNodeSeparateColor")
    nt.links.new(tex(n + "_orm.png", "Non-Color").outputs[0], sep.inputs[0])
    nt.links.new(sep.outputs[1], b.inputs["Roughness"])
    nt.links.new(sep.outputs[2], b.inputs["Metallic"])
    nm_ = nt.nodes.new("ShaderNodeNormalMap")
    nt.links.new(tex(n + "_normal.png", "Non-Color").outputs[0], nm_.inputs["Color"])
    nt.links.new(nm_.outputs[0], b.inputs["Normal"])
    for o in objs:
        o.data.materials.clear()
        o.data.materials.append(m)
    pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    lo = Vector([min(p[k] for p in pts) for k in range(3)])
    hi = Vector([max(p[k] for p in pts) for k in range(3)])
    c = (lo + hi) / 2
    r = (hi - lo).length / 2
    cam.data.lens = 50
    dist = r / math.tan(cam.data.angle / 2) * 1.05
    dirv = Vector((0.55, -1.0, 0.45)).normalized()
    cam.location = c + dirv * dist
    cam.rotation_euler = (c - cam.location).to_track_quat("-Z", "Y").to_euler()
    path = os.path.join(os.path.dirname(out), "_tile_%s.png" % n)
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    tiles.append((n, path))
    for o in objs:
        bpy.data.objects.remove(o)
cols = min(6, max(1, len(tiles)))
rows = (len(tiles) + cols - 1) // cols
sheet = Image.new("RGB", (cols * size, rows * (size + 24)), (20, 20, 22))
dr = ImageDraw.Draw(sheet)
f = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 15)
for k, (n, p) in enumerate(tiles):
    x, y = (k % cols) * size, (k // cols) * (size + 24)
    sheet.paste(Image.open(p), (x, y))
    dr.text((x + 6, y + size + 3), n, font=f, fill=(235, 220, 190))
    os.remove(p)
sheet.save(out)
print("SHEET", out, len(tiles))
