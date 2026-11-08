"""Joins a recipe's parts, unwraps, bakes and exports one prop."""

import json
import math
import os

import bpy
import numpy as np

from . import core, mats


def finish(name, out_root, tex=1024, samples=24):
    """Bakes albedo / normal / ORM maps for everything built since core.reset()
    and writes <out_root>/<name>/<name>.glb plus textures. Returns manifest info."""
    out = os.path.join(out_root, name)
    os.makedirs(out, exist_ok=True)
    parts = [p for p in core.PARTS if p.name in bpy.data.objects]
    bpy.ops.object.select_all(action="DESELECT")
    for p in parts:
        p.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.object.convert(target="MESH")
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    obj.name = name
    bpy.context.scene.cursor.location = (0, 0, 0)
    bpy.ops.object.origin_set(type="ORIGIN_CURSOR")
    me = obj.data
    for uv in list(me.uv_layers):
        me.uv_layers.remove(uv)
    me.uv_layers.new(name="UVMap")
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=math.radians(60), island_margin=0.004, area_weight=0.0, scale_to_bounds=True)
    bpy.ops.uv.pack_islands(margin=0.004)
    bpy.ops.object.mode_set(mode="OBJECT")

    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = samples
    scene.cycles.use_denoising = False  # some builds lack OIDN; bakes then fail silently
    scene.render.bake.margin = max(4, tex // 128)
    core.select_only(obj)

    used = {s.material.name for s in obj.material_slots if s.material}
    infos = [i for n, i in mats.BAKE.items() if i["mat"].name in used]

    def target(img):
        for i in infos:
            nt = i["mat"].node_tree
            node = nt.nodes.get("bake_target") or nt.nodes.new("ShaderNodeTexImage")
            node.name = "bake_target"
            node.image = img
            nt.nodes.active = node

    def emit(key):
        for i in infos:
            nt = i["mat"].node_tree
            em = nt.nodes.get("bake_emit") or nt.nodes.new("ShaderNodeEmission")
            em.name = "bake_emit"
            nt.links.new(i[key], em.inputs["Color"])
            nt.links.new(em.outputs["Emission"], i["out"].inputs["Surface"])

    def new_img(n, cs):
        img = bpy.data.images.new(n, tex, tex, alpha=False)
        img.colorspace_settings.name = cs
        return img

    def save(img, fn):
        img.filepath_raw = os.path.join(out, fn)
        img.file_format = "PNG"
        img.save()

    def px(img):
        a = np.empty(tex * tex * 4, dtype=np.float32)
        img.pixels.foreach_get(a)
        return a

    alb = new_img(name + "_albedo", "sRGB")
    target(alb)
    emit("albedo")
    bpy.ops.object.bake(type="EMIT")
    save(alb, name + "_albedo.png")
    r = new_img(name + "_r", "Non-Color")
    target(r)
    emit("rough")
    bpy.ops.object.bake(type="EMIT")
    mt = new_img(name + "_m", "Non-Color")
    target(mt)
    emit("metal")
    bpy.ops.object.bake(type="EMIT")
    nrm = new_img(name + "_normal", "Non-Color")
    target(nrm)
    for i in infos:
        i["mat"].node_tree.links.new(i["bsdf"].outputs["BSDF"], i["out"].inputs["Surface"])
    scene.cycles.samples = 4
    bpy.ops.object.bake(type="NORMAL", normal_space="TANGENT")
    save(nrm, name + "_normal.png")
    orm = new_img(name + "_orm", "Non-Color")
    a = np.ones(tex * tex * 4, dtype=np.float32)
    a[1::4] = px(r)[0::4]
    a[2::4] = px(mt)[0::4]
    orm.pixels.foreach_set(a)
    save(orm, name + "_orm.png")

    for poly in me.polygons:
        poly.material_index = 0
    me.materials.clear()
    me.materials.append(bpy.data.materials.new(name))
    core.select_only(obj)
    bpy.ops.export_scene.gltf(filepath=os.path.join(out, name + ".glb"), export_format="GLB",
                              use_selection=True, export_materials="PLACEHOLDER", export_yup=True)
    dims = obj.dimensions
    bb = [obj.matrix_world @ v.co for v in me.vertices]
    lo = [min(v[i] for v in bb) for i in range(3)]
    hi = [max(v[i] for v in bb) for i in range(3)]
    tris = sum(len(p.vertices) - 2 for p in me.polygons)
    # Godot axes: x = x, y = z, z = -y
    return {"size": [round(dims.x, 4), round(dims.z, 4), round(dims.y, 4)],
            "min": [round(lo[0], 4), round(lo[2], 4), round(-hi[1], 4)],
            "max": [round(hi[0], 4), round(hi[2], 4), round(-lo[1], 4)],
            "tris": tris, "tex": tex}


def update_manifest(path, name, entry):
    data = {}
    if os.path.exists(path):
        with open(path) as f:
            data = json.load(f)
    data[name] = entry
    with open(path, "w") as f:
        json.dump(dict(sorted(data.items())), f, indent=1)
