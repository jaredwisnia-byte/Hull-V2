"""Render a finished exported trim GLB into a labelled three-view PNG.

Run: blender -b --factory-startup -P long-lines/tools/preview_trim.py -- NAME
Requires the baked GLB, albedo, normal and ORM maps in assets/props/NAME.
"""
import math
import os
import sys

import bpy
from mathutils import Vector
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.normpath(os.path.join(HERE, "..", "assets", "props"))
name = sys.argv[sys.argv.index("--") + 1]
folder = os.path.join(LIB, name)

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=os.path.join(folder, name + ".glb"))
objects = [o for o in bpy.data.objects if o.type == "MESH"]
if not objects:
    raise RuntimeError("GLB has no mesh objects: " + name)

mat = bpy.data.materials.new(name + "_preview")
mat.use_nodes = True
nodes = mat.node_tree.nodes
bsdf = nodes.get("Principled BSDF")
def image_node(filename, colour_space):
    node = nodes.new("ShaderNodeTexImage")
    node.image = bpy.data.images.load(os.path.join(folder, name + filename), check_existing=True)
    node.image.colorspace_settings.name = colour_space
    return node

mat.node_tree.links.new(image_node("_albedo.png", "sRGB").outputs["Color"], bsdf.inputs["Base Color"])
orm = image_node("_orm.png", "Non-Color")
sep = nodes.new("ShaderNodeSeparateColor")
mat.node_tree.links.new(orm.outputs["Color"], sep.inputs[0])
mat.node_tree.links.new(sep.outputs["Green"], bsdf.inputs["Roughness"])
mat.node_tree.links.new(sep.outputs["Blue"], bsdf.inputs["Metallic"])
normal = nodes.new("ShaderNodeNormalMap")
mat.node_tree.links.new(image_node("_normal.png", "Non-Color").outputs["Color"], normal.inputs["Color"])
mat.node_tree.links.new(normal.outputs["Normal"], bsdf.inputs["Normal"])
for o in objects:
    o.data.materials.clear()
    o.data.materials.append(mat)

points = [o.matrix_world @ Vector(corner) for o in objects for corner in o.bound_box]
lo = Vector([min(p[i] for p in points) for i in range(3)])
hi = Vector([max(p[i] for p in points) for i in range(3)])
size = hi - lo
centre = (lo + hi) * .5

scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.samples = 12
scene.cycles.use_denoising = False
scene.render.resolution_x = 380
scene.render.resolution_y = 340
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.film_transparent = False
world = bpy.data.worlds.new("preview_world")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs["Color"].default_value = (.12, .13, .15, 1)
world.node_tree.nodes["Background"].inputs["Strength"].default_value = .75
scene.world = world
for light_name, pos, energy, colour in (
    ("key", (-2.5, -3, 3.5), 450, (1, .91, .8)),
    ("fill", (2.5, 1, 2), 270, (.74, .84, 1))):
    light = bpy.data.objects.new(light_name, bpy.data.lights.new(light_name, "AREA"))
    scene.collection.objects.link(light)
    light.location = pos
    light.data.energy = energy
    light.data.size = 3
    light.data.color = colour
    light.rotation_euler = (centre - light.location).to_track_quat("-Z", "Y").to_euler()

camera = bpy.data.objects.new("preview_camera", bpy.data.cameras.new("preview_camera"))
scene.collection.objects.link(camera)
scene.camera = camera
camera.data.type = "ORTHO"

# The second camera looks almost straight down a length of moulding so the
# cross-section has a useful visible scale instead of appearing as a line.
views = [
    ("Front", Vector((0, -1, .15)), max(size.z * 1.5, size.x * .98, .16)),
    ("End profile", Vector((1, -.08, .08)), max(size.z * 1.8, size.y * 1.8, .15)),
    ("Three-quarter", Vector((.65, -1, .48)), max(size.z * 1.7, size.x * 1.02, .2)),
]
tiles = []
for label, direction, scale in views:
    camera.location = centre + direction.normalized() * max(3, size.length * 2)
    camera.rotation_euler = (centre - camera.location).to_track_quat("-Z", "Y").to_euler()
    camera.data.ortho_scale = scale
    path = os.path.join(folder, "_preview_temp.png")
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    tiles.append((label, Image.open(path).convert("RGB").copy()))
    os.remove(path)

sheet = Image.new("RGB", (1140, 390), (29, 30, 34))
draw = ImageDraw.Draw(sheet)
try:
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
except OSError:
    font = ImageFont.load_default()
for i, (label, img) in enumerate(tiles):
    sheet.paste(img, (i * 380, 0))
    draw.text((i * 380 + 12, 351), label, fill=(235, 226, 210), font=font)
out = os.path.join(folder, "_preview.png")
sheet.save(out)
print("TRIM_PREVIEW", out)
