"""Validate assembly data without importing Blender or silently inventing dimensions."""
import copy
import json
import math
import re
from pathlib import Path

VIEWS = {"front", "back", "left", "right", "top"}


def positive(value, label, integer=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{label} must be positive and finite")
    if integer and type(value) is not int:
        raise ValueError(f"{label} must be an integer")


def validate_manifest(data):
    if not isinstance(data, dict):
        raise ValueError("manifest must be an object")
    cfg = copy.deepcopy(data)
    if not isinstance(cfg.get("name"), str) or not re.fullmatch(r"[A-Za-z0-9_-]+", cfg["name"]):
        raise ValueError("name must contain only letters, digits, underscores or hyphens")
    positive(cfg.get("triangle_limit"), "triangle_limit", True)
    positive(cfg.get("texture", 1024), "texture", True)
    positive(cfg.get("projection_power", 4), "projection_power")
    positive(cfg.get("reconstruction_resolution", 64), "reconstruction_resolution", True)
    if not isinstance(cfg.get("parts"), list) or not cfg["parts"]:
        raise ValueError("parts must be a nonempty list")
    expanded = []
    if not isinstance(cfg.get("prototypes", {}), dict):
        raise ValueError("prototypes must be an object")
    for part in cfg["parts"]:
        if not isinstance(part, dict):
            raise ValueError("each part must be an object")
        prototype = part.get("prototype")
        if prototype:
            template = cfg.get("prototypes", {}).get(prototype)
            if not isinstance(template, dict):
                raise ValueError(f"unknown prototype: {prototype}")
            expanded.append({**copy.deepcopy(template), **part})
        else:
            expanded.append(part)
    cfg["parts"] = expanded
    names = set()
    for part in cfg["parts"]:
        name = part.get("name")
        if type(part.get('texture_upscale', 1)) is not int or part.get('texture_upscale', 1) not in (1,2,4):
            raise ValueError('texture_upscale must be 1, 2 or 4')
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", name) or name in names:
            raise ValueError("part names must be unique filesystem-safe identifiers")
        names.add(name)
        if part.get("method") not in {"polygon", "round"}:
            raise ValueError(f"{name}: method must be polygon or round")
        dimensions = part.get("dimensions", [])
        if not isinstance(dimensions, (list, tuple)) or len(dimensions) != 3:
            raise ValueError(f"{name}: dimensions must be [width, depth, height] in metres")
        for value in dimensions:
            positive(value, f"{name}.dimensions")
        if "surface_error_m" in part:
            positive(part["surface_error_m"], f"{name}.surface_error_m")
        positive(part.get("budget"), f"{name}.budget", True)
        position = part.setdefault("position", [0, 0, 0])
        if not isinstance(position, (list, tuple)) or len(position) != 3 or any(isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v) for v in position):
            raise ValueError(f"{name}: position must contain three finite numbers")
        views = part.get("views", {})
        if not isinstance(views, dict) or not views or not set(views) <= VIEWS:
            raise ValueError(f"{name}: unknown or missing views")
        if not isinstance(part.get("reference", cfg.get("reference")), str):
            raise ValueError(f"{name}: reference image is required")
        if part.get("mask_mode", "body") not in {"body", "object"}:
            raise ValueError(f"{name}: mask_mode must be body or object")
        if part.get("part_map", cfg.get("part_map")) is not None and not isinstance(part.get("part_map", cfg.get("part_map")), str):
            raise ValueError(f"{name}: part_map must be an image path")
        for view, box in views.items():
            if not isinstance(box, (list, tuple)) or len(box) != 4 or any(type(v) is not int for v in box) or min(box) < 0 or box[2] <= box[0] or box[3] <= box[1]:
                raise ValueError(f"{name}.{view}: invalid pixel crop")
        masks = part.get("masks", {})
        if not isinstance(masks, dict) or not set(masks) <= set(views) or any(not isinstance(v, str) for v in masks.values()):
            raise ValueError(f"{name}: masks must map supplied views to image paths")
        detail = part.get("surface_detail")
        if detail is not None:
            if not isinstance(detail, dict) or detail.get("view") not in views:
                raise ValueError("surface_detail requires a supplied view")
            positive(detail.get("depth_m"), "surface detail depth")
            match = detail.get('minimum_match', .2)
            if isinstance(match, bool) or not isinstance(match, (int,float)) or not math.isfinite(match) or not 0 <= match <= 1:
                raise ValueError('minimum_match must be between zero and one')
            if detail["depth_m"] > min(dimensions) * .07:
                raise ValueError("surface detail exceeds 7 percent of part thickness")
            if "height_map" in detail and not isinstance(detail["height_map"], str):
                raise ValueError("height_map must be a path")
            if part.get("use_normal_map") is False:
                raise ValueError("surface detail requires use_normal_map")
        geometry = part.setdefault("geometry_views", list(views))
        if not isinstance(geometry, list) or not geometry or not set(geometry) <= set(views):
            raise ValueError(f"{name}: geometry_views must select supplied views")
        if part["method"] == "round" and ("front" not in geometry or not {"right", "left"}.intersection(geometry)):
            raise ValueError(f"{name}: round reconstruction needs front and a side view")
        axes = {"front": "y", "back": "y", "left": "x", "right": "x", "top": "z"}
        if part["method"] == "polygon" and len({axes[v] for v in geometry}) < 2:
            raise ValueError(f"{name}: at least two geometry views must constrain depth")
        for key, default in [("contour_tolerance", 1.1), ("bevel_fraction", .01)]:
            value = part.get(key, default)
            if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or value < 0:
                raise ValueError(f"{name}.{key} must be finite and nonnegative")
        axis = part.get("circular_axis")
        if axis not in (None, "vertical", "front-to-back"):
            raise ValueError(f"{name}: unsupported circular_axis")
        if axis:
            a, b = (dimensions[0], dimensions[1] if axis == "vertical" else dimensions[2])
            if not math.isclose(a, b, rel_tol=.01):
                raise ValueError(f"{name}: circular dimensions disagree; specify equal diameters")
        # Accept the checkpoint recipes, normalize them to general attachment constraints.
        if "mount" in part and "attachment" not in part:
            if part["mount"] == "top":
                part["attachment"] = {"parent": cfg["parts"][0]["name"], "face": "top", "overlap": .001}
            elif part["mount"] == "lens_mount":
                part["attachment"] = {"parent": cfg["parts"][0]["name"], "face": "front", "pixel": part.get("mount_pixel"), "overlap": .006}
            else:
                raise ValueError(f"{name}: unknown legacy mount")
    for part in cfg["parts"]:
        attachment = part.get("attachment")
        if attachment is not None and not isinstance(attachment, dict):
            raise ValueError("attachment must be an object")
        if attachment is None:
            part.pop("attachment", None)
        if attachment:
            if attachment.get("parent") not in names or attachment["parent"] == part["name"]:
                raise ValueError(f"{part['name']}: unknown/self attachment parent")
            if "landmarks" in attachment:
                if any(k in attachment for k in ("face", "pixel", "overlap")):
                    raise ValueError("landmarks cannot be mixed with face seating")
                landmarks = attachment["landmarks"]
                if not isinstance(landmarks, list) or len(landmarks) < 3:
                    raise ValueError("at least three attachment landmarks required")
                for pair in landmarks:
                    for key in ("source", "target"):
                        point = pair.get(key) if isinstance(pair, dict) else None
                        if not isinstance(point, list) or len(point) != 3 or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in point):
                            raise ValueError("landmarks must contain finite source and target 3D points")
                positive(attachment.get("tolerance_m", .001), "attachment tolerance")
            elif attachment.get("face") not in {"front", "back", "left", "right", "top"}:
                raise ValueError(f"{part['name']}: unknown attachment face")
            overlap = attachment.get("overlap", .001)
            if isinstance(overlap, bool) or not isinstance(overlap, (int, float)) or not math.isfinite(overlap) or overlap < 0:
                raise ValueError("attachment overlap must be finite and nonnegative")
            if "pixel" in attachment:
                pixel = attachment["pixel"]
                if attachment["face"] != "front" or not isinstance(pixel, list) or len(pixel) != 2 or any(type(v) is not int or v < 0 for v in pixel):
                    raise ValueError("pixel attachment requires two nonnegative front-view pixel coordinates")
        if part.get("parent") and (part["parent"] not in names or part["parent"] == part["name"]):
            raise ValueError(f"{part['name']}: unknown/self hierarchy parent")
    # One ceiling applies to every component together, before any expensive build.
    if sum(p["budget"] for p in cfg["parts"]) > cfg["triangle_limit"]:
        raise ValueError("sum of component budgets exceeds the assembly triangle_limit")
    ordered = []
    pending = list(cfg["parts"])
    while pending:
        ready = [p for p in pending if {v for v in (p.get("parent"), p.get("attachment", {}).get("parent")) if v} <= {p["name"] for p in ordered}]
        if not ready:
            raise ValueError("cyclic component dependencies")
        for part in ready:
            ordered.append(part)
            pending.remove(part)
    cfg["parts"] = ordered
    return cfg


def load_manifest(path):
    path = Path(path).resolve()
    with path.open(encoding="utf-8-sig") as source:
        cfg = validate_manifest(json.load(source))
    return cfg, path.parent
