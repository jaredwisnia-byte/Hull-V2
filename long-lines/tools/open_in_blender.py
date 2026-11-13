"""Open a library prop in Blender's window with its textures connected.

Library GLBs carry placeholder materials (the baked albedo/normal/ORM maps
are separate PNGs), so a plain File > Import shows them grey. This script imports the GLB and wires the
three maps beside it into a normal Principled material.

    blender --python long-lines/tools/open_in_blender.py -- fridge_1_set
    blender --python long-lines/tools/open_in_blender.py -- path/to/model.glb

Or in Blender: Scripting tab > Open this file > set NAME below > Run Script.
"""
import os
import sys

import bpy

NAME = ""   # used when run from the Scripting tab without arguments

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.path.normpath(os.path.join(HERE, "..", "assets", "props"))
arg = sys.argv[sys.argv.index("--") + 1] if "--" in sys.argv else NAME
if arg.endswith(".glb"):
    path = os.path.abspath(arg)
    folder, name = os.path.dirname(path), os.path.basename(path)[:-4]
else:
    sys.path.insert(0, HERE)
    from propkit.warehouse import asset_directory
    folder, name = str(asset_directory(LIB, arg)), arg
    path = os.path.join(folder, name + ".glb")

for o in list(bpy.data.objects):          # start from an empty scene
    bpy.data.objects.remove(o)
bpy.ops.import_scene.gltf(filepath=path)

maps = {k: os.path.join(folder, "%s_%s.png" % (name, k)) for k in ("albedo", "normal", "orm")}
if os.path.exists(maps["albedo"]):
    m = bpy.data.materials.new(name + "_textured")
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]

    def tex(key, cs):
        n = nt.nodes.new("ShaderNodeTexImage")
        n.image = bpy.data.images.load(maps[key])
        n.image.colorspace_settings.name = cs
        return n

    nt.links.new(tex("albedo", "sRGB").outputs["Color"], b.inputs["Base Color"])
    if os.path.exists(maps["normal"]):
        nm = nt.nodes.new("ShaderNodeNormalMap")
        nt.links.new(tex("normal", "Non-Color").outputs["Color"], nm.inputs["Color"])
        nt.links.new(nm.outputs["Normal"], b.inputs["Normal"])
    if os.path.exists(maps["orm"]):
        sep = nt.nodes.new("ShaderNodeSeparateColor")
        nt.links.new(tex("orm", "Non-Color").outputs["Color"], sep.inputs["Color"])
        nt.links.new(sep.outputs["Green"], b.inputs["Roughness"])
        nt.links.new(sep.outputs["Blue"], b.inputs["Metallic"])
    for o in bpy.data.objects:
        if o.type == "MESH":
            o.data.materials.clear()
            o.data.materials.append(m)
for area in getattr(bpy.context.screen, "areas", []):   # material preview so the textures show
    if area.type == "VIEW_3D":
        area.spaces.active.shading.type = "MATERIAL"
print("Opened", path)
