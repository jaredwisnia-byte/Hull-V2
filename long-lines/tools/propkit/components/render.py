"""Portable verification renders for exported component assemblies."""
import math
from pathlib import Path

import bpy
from mathutils import Vector
from PIL import Image, ImageDraw, ImageFont


def render(model, output, mode="textured", resolution=640):
    if mode not in {"textured", "clay", "wireframe"}:
        raise ValueError("unknown render mode")
    if resolution < 64:
        raise ValueError("resolution must be at least 64")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(Path(model).resolve()))
    objects = [o for o in bpy.data.objects if o.type == "MESH"]
    if not objects:
        raise ValueError("model contains no meshes")
    bpy.context.view_layer.update()
    points = [o.matrix_world @ Vector(c) for o in objects for c in o.bound_box]
    lo = Vector([min(p[i] for p in points) for i in range(3)])
    hi = Vector([max(p[i] for p in points) for i in range(3)])
    center, size = (lo + hi) / 2, max(hi - lo)
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 24
    scene.cycles.use_denoising = False
    scene.render.resolution_x = scene.render.resolution_y = resolution
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = True
    scene.world = bpy.data.worlds.new("Inspection studio")
    scene.world.use_nodes = True
    scene.world.node_tree.nodes["Background"].inputs["Strength"].default_value = .65
    for offset, energy in [((-3, -4, 5), 450), ((4, -2, 3), 250), ((0, 4, 4), 400)]:
        light = bpy.data.lights.new("Inspection softbox", "AREA")
        light.energy, light.size = energy, 4
        obj = bpy.data.objects.new(light.name, light)
        scene.collection.objects.link(obj)
        obj.location = center + Vector(offset)
        obj.rotation_euler = (center - obj.location).to_track_quat("-Z", "Y").to_euler()
    if mode != "textured":
        material = bpy.data.materials.new("Geometry inspection")
        material.use_nodes = True
        nodes = material.node_tree
        shader = nodes.nodes["Principled BSDF"]
        shader.inputs["Base Color"].default_value = (.45, .45, .45, 1)
        shader.inputs["Roughness"].default_value = .8
        if mode == "wireframe":
            wire = nodes.nodes.new("ShaderNodeWireframe")
            wire.use_pixel_size = True
            wire.inputs["Size"].default_value = .7
            mix = nodes.nodes.new("ShaderNodeMixRGB")
            mix.inputs[1].default_value = (.6, .6, .6, 1)
            mix.inputs[2].default_value = (.01, .01, .01, 1)
            nodes.links.new(wire.outputs[0], mix.inputs[0])
            nodes.links.new(mix.outputs[0], shader.inputs["Base Color"])
        for obj in objects:
            obj.data.materials.clear()
            obj.data.materials.append(material)
    camera = bpy.data.objects.new("Inspection camera", bpy.data.cameras.new("Inspection camera"))
    scene.collection.objects.link(camera)
    scene.camera = camera
    camera.data.type = "ORTHO"
    camera.data.ortho_scale = size * 1.5
    camera.data.clip_start = min(.001, size / 100)
    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    from ..runtime import scratch_dir
    temporary = Path(scratch_dir("render_" + output.stem))
    sheet = Image.new("RGB", (resolution * 2, resolution * 2 + 60), (232, 234, 235))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 20)
    except OSError:
        font = ImageFont.load_default()
    draw.text((16, 15), f"{Path(model).stem} | {mode}", font=font, fill=(25, 35, 45))
    for i, (label, azimuth, elevation) in enumerate([("FRONT", 0, 0), ("FRONT RIGHT", 40, 24), ("REAR LEFT", -140, 24), ("TOP", 0, 89.9)]):
        a, e = math.radians(azimuth), math.radians(elevation)
        direction = Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e)))
        camera.location = center + direction * size * 4
        camera.rotation_euler = (-direction).to_track_quat("-Z", "Y").to_euler()
        path = temporary / f"{i}.png"
        scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        with Image.open(path) as image:
            background = Image.new("RGBA", image.size, (232, 234, 235, 255))
            background.alpha_composite(image.convert("RGBA"))
            x, y = i % 2 * resolution, 60 + i // 2 * resolution
            sheet.paste(background.convert("RGB"), (x, y))
            draw.text((x + 12, y + 12), label, font=font, fill=(25, 35, 45))
    sheet.save(output)
    return str(output)
