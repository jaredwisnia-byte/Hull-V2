"""Identical three-quarter render of a GLB, framed on ALL its meshes (B exports one mesh per panel).
blender -b --factory-startup -P stress_render.py -- FOLDER NAME OUT.png"""
import math, os, sys
import bpy
from mathutils import Vector
a = sys.argv[sys.argv.index("--") + 1:]
folder, name, out = a
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=os.path.join(folder, name + ".glb"))
objs = [o for o in bpy.data.objects if o.type == "MESH"]
m = bpy.data.materials.new("m"); m.use_nodes = True; nt = m.node_tree; b = nt.nodes["Principled BSDF"]
def tex(fn, cs):
    n = nt.nodes.new("ShaderNodeTexImage"); n.image = bpy.data.images.load(os.path.join(folder, fn)); n.image.colorspace_settings.name = cs; return n
al = tex(name + "_albedo.png", "sRGB"); nt.links.new(al.outputs["Color"], b.inputs["Base Color"])
nr = tex(name + "_normal.png", "Non-Color"); nm = nt.nodes.new("ShaderNodeNormalMap"); nt.links.new(nr.outputs["Color"], nm.inputs["Color"]); nt.links.new(nm.outputs["Normal"], b.inputs["Normal"])
for o in objs:
    o.data.materials.clear(); o.data.materials.append(m)
pts = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
lo = Vector([min(p[i] for p in pts) for i in range(3)]); hi = Vector([max(p[i] for p in pts) for i in range(3)])
c = (lo + hi) / 2; r = (hi - lo).length / 2
sc = bpy.context.scene; sc.render.engine = "CYCLES"; sc.cycles.samples = 48; sc.cycles.use_denoising = False
sc.render.resolution_x = sc.render.resolution_y = 480
w = bpy.data.worlds.new("w"); sc.world = w; w.use_nodes = True
w.node_tree.nodes["Background"].inputs["Color"].default_value = (0.42, 0.44, 0.48, 1); w.node_tree.nodes["Background"].inputs["Strength"].default_value = 1.6
sun = bpy.data.objects.new("s", bpy.data.lights.new("s", "SUN")); sun.data.energy = 3; sun.rotation_euler = (math.radians(50), 0, math.radians(-30)); sc.collection.objects.link(sun)
cam = bpy.data.objects.new("c", bpy.data.cameras.new("c")); sc.collection.objects.link(cam); sc.camera = cam
cam.data.lens = 85; d = Vector((0.62, -0.75, 0.45)).normalized()
cam.location = c + d * r * 6.2; cam.rotation_euler = (c - cam.location).to_track_quat("-Z", "Y").to_euler()
sc.render.filepath = out; bpy.ops.render.render(write_still=True)
