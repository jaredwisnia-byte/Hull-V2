"""Build each part in a local frame; preserve its source paint coordinates."""
import json
from pathlib import Path

import bpy
from PIL import Image

from .. import core, texturing
from ..hull import HULL_REPORT, hull_prop, polygon_hull, silhouette


def triangle_count(obj):
    return sum(len(p.vertices) - 2 for p in obj.data.polygons)


def reconstruct(spec, cfg, source_root, work):
    name = spec["name"]
    directory = Path(work) / name
    directory.mkdir(parents=True, exist_ok=True)
    reference = Path(spec.get("reference", cfg.get("reference")))
    reference = reference if reference.is_absolute() else source_root / reference
    masks, paintings, frames = {}, {}, {}
    with Image.open(reference) as image:
        image = image.convert("RGB")
        part_map = spec.get("part_map", cfg.get("part_map"))
        map_image = None
        if part_map:
            path = Path(part_map)
            with Image.open(path if path.is_absolute() else source_root / path) as source:
                map_image = source.convert("RGB")
            if map_image.size != image.size:
                raise ValueError(f"{name}: part map must align exactly with its reference canvas")
        for view, box in spec["views"].items():
            if box[2] > image.width or box[3] > image.height:
                raise ValueError(f"{name}.{view}: crop extends beyond {reference.name}")
            path = directory / f"{view}_input.png"
            image.crop(box).save(path)
            if view in spec.get("masks", {}):
                from .masks import masked_crop
                explicit = Path(spec["masks"][view])
                mask, paint, bounds = masked_crop(image, explicit if explicit.is_absolute() else source_root / explicit, box)
            elif map_image is None:
                mask, paint, bounds = silhouette(str(path), with_box=True)
            else:
                from .. import sheetset
                mapping = {"painted_sheet": {"view_bboxes_px": spec["views"]}}
                view_data = sheetset.view(mapping, {"painted_sheet": image, "part_map": map_image,
                                                    "depth_map": Image.new("RGB", image.size, (128, 128, 128))}, view)
                mask = view_data["carve"] if spec.get("mask_mode", "body") == "body" else view_data["obj"]
                paint, bounds = view_data["paint"], view_data["bb"]
            masks[view] = (mask, paint)
            frames[view] = {"box": box, "bounds": bounds, "shape": mask.shape}
            path = directory / f"{view}_paint.png"
            paint.save(path)
            paintings[view] = str(path)
    width, depth, height = spec["dimensions"]
    geometry = {k: masks[k] for k in spec["geometry_views"]}
    HULL_REPORT.clear()
    if spec["method"] == "round":
        obj = hull_prop({}, height, width_m=width, depth_m=depth, sil_override=geometry,
                        name=name, res=cfg.get("reconstruction_resolution", 64), paint=False,
                        features=False, sections=False, smooth_iters=1, decimate=.12, revolve=True)
    else:
        obj = polygon_hull({k: v[0] for k, v in geometry.items()}, width, depth, height,
                           name=name, tolerance=spec.get("contour_tolerance", 1.1),
                           bevel_frac=spec.get("bevel_fraction", .01))
    inference = json.loads(json.dumps(HULL_REPORT, default=str))
    before = triangle_count(obj)
    if before > spec["budget"]:
        modifier = obj.modifiers.new("Component triangle allocation", "DECIMATE")
        modifier.ratio = spec["budget"] / before * .97
        core.apply_mods(obj)
    count = triangle_count(obj)
    if count > spec["budget"]:
        raise RuntimeError(f"{name}: could not meet triangle allocation")
    if cfg.get("pad_paint", False):
        for view, (mask, image) in masks.items():
            path = directory / f"{view}_padded.png"
            texturing.pad_paint(image, mask).save(path)
            paintings[view] = str(path)
    projection = texturing.project(obj, paintings, width, depth, height, others=[], name=name,
                                  rough=spec.get("roughness", .65), power=cfg.get("projection_power", 4))
    return obj, frames, {"name": name, "triangles": count, "budget": spec["budget"],
                         "hull_report": inference, "projection": projection}
