"""Diagnostic renders of a library prop: the same cameras in six modes, to tell geometry from paint.

    blender -b --factory-startup -P tools/diag/render_modes.py -- NAME OUT_DIR [--cams front34,side,...]
          [--glb PATH]   (default assets/props/NAME/NAME.glb, maps beside it)

Modes: clay (no texture), wire (wireframe over clay), albedo (texture only, no lighting), normals
(shading normals as colour), facets (true face normals: shows terraces the smooth shading hides),
depth (distance from the camera), textured (albedo + normal + ORM maps, lit).
Cameras are placed from the object's bounding box, so any prop works.
"""
import math
import os
import sys

import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
name, out = argv[0], argv[1]
cams = "front34,side,top34,hood".split(",")
glb = None
if "--cams" in argv:
    cams = argv[argv.index("--cams") + 1].split(",")
if "--glb" in argv:
    glb = argv[argv.index("--glb") + 1]
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
glb = glb or os.path.join(ROOT, "assets", "props", name, name + ".glb")
base = glb[:-4]
os.makedirs(out, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=glb)
objs = [o for o in bpy.data.objects if o.type == "MESH"]
bpy.context.view_layer.update()
lo = Vector((1e9,) * 3)
hi = Vector((-1e9,) * 3)
for o in objs:
    for c in o.bound_box:
        w = o.matrix_world @ Vector(c)
        lo = Vector(map(min, lo, w))
        hi = Vector(map(max, hi, w))
centre = (lo + hi) / 2
size = max(hi - lo)
sc = bpy.context.scene
sc.render.engine = "CYCLES"
sc.cycles.use_denoising = False
sc.render.resolution_x, sc.render.resolution_y = 900, 640
w = bpy.data.worlds.new("w")
w.use_nodes = True
w.node_tree.nodes["Background"].inputs["Color"].default_value = (0.32, 0.34, 0.38, 1)
w.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.8
sc.world = w
lights = []
for nm, d, e in (("key", (-0.6, -0.9, 0.7), 3.2), ("fill", (0.8, -0.2, 0.4), 1.0), ("rim", (0.2, 1, 0.6), 1.4)):
    L = bpy.data.lights.new(nm, "SUN")
    L.energy = e
    L.angle = 0.15
    lo_ = bpy.data.objects.new(nm, L)
    sc.collection.objects.link(lo_)
    lo_.rotation_euler = (-Vector(d)).to_track_quat("-Z", "Y").to_euler()
    lights.append(lo_)
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
sc.collection.objects.link(cam)
sc.camera = cam
cam.data.clip_end = size * 50

# camera name -> (azimuth deg, elevation deg, distance in object sizes, target offset as a share of the box)
CAMS = {"front34": (-40, 10, 1.9, (0, 0, 0)), "side": (-90, 6, 1.9, (0, 0, 0)), "top34": (-30, 45, 1.9, (0, 0, 0)),
        "back34": (140, 15, 1.9, (0, 0, 0)), "front": (0, 6, 1.9, (0, 0, 0)), "full34": (-35, 8, 2.8, (0, 0, 0)),
        "fullside": (-90, 6, 2.8, (0, 0, 0)),
        "hood": (-25, 25, 0.75, (0, -0.3, 0.2)), "rear_quarter": (-55, 15, 0.8, (-0.3, 0.2, 0.25))}


def mat(kind, img=None):
    m = bpy.data.materials.new(kind)
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    outn = nt.nodes.new("ShaderNodeOutputMaterial")
    if kind == "clay":
        b = nt.nodes.new("ShaderNodeBsdfPrincipled")
        b.inputs["Base Color"].default_value = (0.55, 0.55, 0.55, 1)
        b.inputs["Roughness"].default_value = 0.6
        nt.links.new(b.outputs[0], outn.inputs[0])
        return m
    if kind == "wire":
        e = nt.nodes.new("ShaderNodeEmission")
        e.inputs["Color"].default_value = (0.02, 0.02, 0.05, 1)
        nt.links.new(e.outputs[0], outn.inputs[0])
        return m
    e = nt.nodes.new("ShaderNodeEmission")
    nt.links.new(e.outputs[0], outn.inputs[0])
    if kind == "albedo":
        t = nt.nodes.new("ShaderNodeTexImage")
        t.image = bpy.data.images.load(base + "_albedo.png")
        nt.links.new(t.outputs["Color"], e.inputs["Color"])
    elif kind in ("normals", "facets"):
        g = nt.nodes.new("ShaderNodeNewGeometry")
        vm = nt.nodes.new("ShaderNodeVectorMath")
        vm.operation = "MULTIPLY_ADD"
        vm.inputs[1].default_value = (0.5, 0.5, 0.5)
        vm.inputs[2].default_value = (0.5, 0.5, 0.5)
        nt.links.new(g.outputs["Normal" if kind == "normals" else "True Normal"], vm.inputs[0])
        nt.links.new(vm.outputs[0], e.inputs["Color"])
    elif kind == "depth":
        cd = nt.nodes.new("ShaderNodeCameraData")
        mr = nt.nodes.new("ShaderNodeMapRange")
        mr.inputs["From Min"].default_value = 0.0
        mr.inputs["From Max"].default_value = 1.0
        nt.links.new(cd.outputs["View Z Depth"], mr.inputs["Value"])
        nt.links.new(mr.outputs[0], e.inputs["Color"])
        m["depth_node"] = mr.name
    elif kind == "textured":
        nt.nodes.remove(e)
        b = nt.nodes.new("ShaderNodeBsdfPrincipled")
        nt.links.new(b.outputs[0], outn.inputs[0])

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


MATS = {k: mat(k) for k in ("clay", "wire", "albedo", "normals", "facets", "depth", "textured")}
wires = []
for o in objs:
    d = o.copy()
    d.data = o.data.copy()
    sc.collection.objects.link(d)
    wm = d.modifiers.new("w", "WIREFRAME")
    wm.thickness = size * 0.0008
    wm.use_replace = True
    d.data.materials.clear()
    d.data.materials.append(MATS["wire"])
    wires.append(d)


def set_mode(mode):
    for o in objs:
        o.data.materials.clear()
        o.data.materials.append(MATS["clay" if mode == "wire" else mode])
    for d in wires:
        d.hide_render = mode != "wire"
    lit = mode in ("clay", "wire", "textured")
    sc.cycles.samples = 48 if lit else 4
    for l in lights:
        l.hide_render = not lit
    sc.world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.8 if lit else 0.0


for cname in cams:
    az, el, dist, off = CAMS[cname]
    a, e_ = math.radians(az), math.radians(el)
    t = centre + Vector((off[0] * (hi - lo).x, off[1] * (hi - lo).y, off[2] * (hi - lo).z))
    d = Vector((math.sin(a) * math.cos(e_), -math.cos(a) * math.cos(e_), math.sin(e_)))
    cam.data.lens = 50
    cam.location = t + d * size * dist
    cam.rotation_euler = (t - cam.location).to_track_quat("-Z", "Y").to_euler()
    near = (cam.location - centre).length - size * 0.6
    far = (cam.location - centre).length + size * 0.6
    mr = MATS["depth"].node_tree.nodes[MATS["depth"]["depth_node"]]
    mr.inputs["From Min"].default_value, mr.inputs["From Max"].default_value = far, near
    for mode in ("textured", "clay", "wire", "albedo", "normals", "facets", "depth"):
        set_mode(mode)
        sc.render.filepath = os.path.join(out, "%s_%s.png" % (cname, mode))
        bpy.ops.render.render(write_still=True)
    print("CAM", cname)
