"""Renders a quick look at a baked prop: three views side by side.
    blender --background --factory-startup --python tools/preview_prop.py -- <dir> <name> <out.png>
"""
import math
import os
import sys

import bpy
from mathutils import Vector

args = sys.argv[sys.argv.index("--") + 1:]
folder, name, out = args[0], args[1], args[2]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=os.path.join(folder, name + ".glb"))
obj = [o for o in bpy.data.objects if o.type == "MESH"][0]
m = bpy.data.materials.new("preview")
m.use_nodes = True
nt = m.node_tree
bsdf = nt.nodes["Principled BSDF"]


def tex(fn, cs):
    n = nt.nodes.new("ShaderNodeTexImage")
    n.image = bpy.data.images.load(os.path.join(folder, fn))
    n.image.colorspace_settings.name = cs
    return n


alb = tex(name + "_albedo.png", "sRGB")
nt.links.new(alb.outputs["Color"], bsdf.inputs["Base Color"])
orm = tex(name + "_orm.png", "Non-Color")
sep = nt.nodes.new("ShaderNodeSeparateColor")
nt.links.new(orm.outputs["Color"], sep.inputs[0])
nt.links.new(sep.outputs["Green"], bsdf.inputs["Roughness"])
nt.links.new(sep.outputs["Blue"], bsdf.inputs["Metallic"])
nrm = tex(name + "_normal.png", "Non-Color")
nm = nt.nodes.new("ShaderNodeNormalMap")
nt.links.new(nrm.outputs["Color"], nm.inputs["Color"])
nt.links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
obj.data.materials.clear()
obj.data.materials.append(m)

scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.samples = int(os.environ.get("PREVIEW_SAMPLES", "48"))
scene.cycles.use_denoising = False
scene.render.resolution_x = 640
scene.render.resolution_y = 720
scene.render.film_transparent = False
world = bpy.data.worlds.new("w")
scene.world = world
world.use_nodes = True
world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.05, 0.055, 0.065, 1)
world.node_tree.nodes["Background"].inputs["Strength"].default_value = 1.0
floor = bpy.data.objects.new("floor", bpy.data.meshes.new("f"))
import bmesh
bm = bmesh.new()
bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=3)
bm.to_mesh(floor.data)
scene.collection.objects.link(floor)
fm = bpy.data.materials.new("floor")
fm.use_nodes = True
fm.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.25, 0.17, 0.1, 1)
floor.data.materials.append(fm)
key = bpy.data.objects.new("key", bpy.data.lights.new("key", "AREA"))
key.data.energy = 220
key.data.size = 1.2
key.data.color = (1.0, 0.85, 0.65)
key.location = (-1.6, -1.8, 2.2)
key.rotation_euler = (Vector((0, 0, 0.9)) - key.location).to_track_quat("-Z", "Y").to_euler()
scene.collection.objects.link(key)
fill = bpy.data.objects.new("fill", bpy.data.lights.new("fill", "AREA"))
fill.data.energy = 70
fill.data.size = 2.0
fill.data.color = (0.6, 0.72, 0.95)
fill.location = (2.0, -1.0, 1.4)
fill.rotation_euler = (Vector((0, 0, 0.8)) - fill.location).to_track_quat("-Z", "Y").to_euler()
scene.collection.objects.link(fill)
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
cam.data.lens = 50
scene.collection.objects.link(cam)
scene.camera = cam
center = Vector((0, 0, obj.dimensions.z * 0.42))
dist = max(obj.dimensions) * 2.1
frames = []
views = [("front3q", -35, 12), ("side", -80, 8), ("closeup", -18, 5)]
for tag, az, el in views:
    d = dist * (0.5 if tag == "closeup" else 1.0)
    c = center + (Vector((0.18, 0, 0.12)) if tag == "closeup" else Vector())
    # Blender front is -Y.
    a = math.radians(az)
    e = math.radians(el)
    cam.location = c + Vector((math.sin(a) * math.cos(e) * -1 * -1, -math.cos(a) * math.cos(e), math.sin(e))) * d
    cam.location.x = c.x + math.sin(-a) * -d * math.cos(e)
    cam.rotation_euler = (c - cam.location).to_track_quat("-Z", "Y").to_euler()
    path = out.replace(".png", "_%s.png" % tag)
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    frames.append(path)
print("FRAMES", " ".join(frames))
