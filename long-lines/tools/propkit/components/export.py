"""Restore baked materials and named meshes after the one shared atlas bake."""
import json
import struct
from pathlib import Path

import bpy

from .. import core


def baked_material(base):
    material = bpy.data.materials.new(base.name + "_baked")
    material.use_nodes = True
    nodes = material.node_tree
    shader = nodes.nodes["Principled BSDF"]

    def texture(suffix, space):
        node = nodes.nodes.new("ShaderNodeTexImage")
        node.image = bpy.data.images.load(str(base.with_name(base.name + "_" + suffix + ".png")))
        node.image.colorspace_settings.name = space
        return node

    nodes.links.new(texture("albedo", "sRGB").outputs["Color"], shader.inputs["Base Color"])
    normal = nodes.nodes.new("ShaderNodeNormalMap")
    nodes.links.new(texture("normal", "Non-Color").outputs["Color"], normal.inputs["Color"])
    nodes.links.new(normal.outputs["Normal"], shader.inputs["Normal"])
    split = nodes.nodes.new("ShaderNodeSeparateColor")
    nodes.links.new(texture("orm", "Non-Color").outputs["Color"], split.inputs["Color"])
    nodes.links.new(split.outputs["Green"], shader.inputs["Roughness"])
    nodes.links.new(split.outputs["Blue"], shader.inputs["Metallic"])
    return material


def exported_triangles(path):
    with open(path, "rb") as source:
        header = source.read(20)
        if len(header) != 20 or header[:4] != b"glTF":
            raise ValueError("not a GLB")
        length, kind = struct.unpack_from("<II", header, 12)
        if kind != 0x4e4f534a:
            raise ValueError("missing GLB JSON chunk")
        data = json.loads(source.read(length))
    count = 0
    for mesh in data.get("meshes", []):
        for primitive in mesh["primitives"]:
            if primitive.get("mode", 4) != 4 or "indices" not in primitive:
                raise ValueError("expected indexed triangles")
            count += data["accessors"][primitive["indices"]]["count"] // 3
    return count


def finish(cfg, out_root, save_blend=True):
    base = Path(out_root) / cfg["name"] / cfg["name"]
    joined = bpy.context.view_layer.objects.active
    joined.data.materials.clear()
    joined.data.materials.append(baked_material(base))
    objects = {}
    for spec in cfg["parts"][1:]:
        core.select_only(joined)
        group = joined.vertex_groups.get("hull_component_" + spec["name"])
        if group is None:
            raise RuntimeError("baking lost component identity: " + spec["name"])
        before = set(bpy.data.objects)
        joined.vertex_groups.active_index = group.index
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="DESELECT")
        bpy.ops.object.vertex_group_select()
        bpy.ops.mesh.separate(type="SELECTED")
        bpy.ops.object.mode_set(mode="OBJECT")
        added = set(bpy.data.objects) - before
        if len(added) != 1:
            raise RuntimeError("could not preserve component: " + spec["name"])
        obj = added.pop()
        obj.name = spec["name"]
        objects[spec["name"]] = obj
    joined.name = cfg["parts"][0]["name"]
    objects[joined.name] = joined
    bpy.context.view_layer.update()
    for spec in cfg["parts"]:
        obj = objects[spec["name"]]
        if not spec.get("use_normal_map", True):
            material = obj.data.materials[0].copy()
            obj.data.materials[0] = material
            for link in list(material.node_tree.nodes["Principled BSDF"].inputs["Normal"].links):
                material.node_tree.links.remove(link)
        if spec.get("parent"):
            world = obj.matrix_world.copy()
            obj.parent = objects[spec["parent"]]
            obj.matrix_parent_inverse = obj.parent.matrix_world.inverted()
            obj.matrix_world = world
    core.select_only(joined)
    for obj in objects.values():
        obj.select_set(True)
    bpy.ops.export_scene.gltf(filepath=str(base.with_suffix(".glb")), export_format="GLB", use_selection=True)
    total = exported_triangles(base.with_suffix(".glb"))
    if total > cfg["triangle_limit"]:
        raise RuntimeError(f"export exceeds assembly triangle limit: {total}")
    if save_blend:
        bpy.ops.file.pack_all()
        bpy.ops.wm.save_as_mainfile(filepath=str(base.with_suffix(".blend")))
    return {"exported_triangles": total, "components": list(objects), "blend_saved": save_blend}
