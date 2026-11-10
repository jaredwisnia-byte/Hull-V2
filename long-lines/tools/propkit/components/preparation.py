"""Reviewable crop extraction and scale preparation from user-labelled regions."""
import copy
import json
from pathlib import Path

from PIL import Image, ImageDraw

from .dimensions import from_height
from .manifest import validate_manifest


def prepare(recipe, output):
    from ..hull import silhouette
    recipe = Path(recipe).resolve()
    cfg = json.loads(recipe.read_text(encoding="utf-8-sig"))
    cfg = copy.deepcopy(cfg)
    # Validate identifiers and schema before using names as output filenames.
    for part in cfg.get("parts", []):
        if "height_anchor" in part:
            if "dimensions" in part:
                raise ValueError("choose supplied dimensions or height_anchor, not both")
            part["dimensions"] = [1, 1, 1]
    cfg = validate_manifest(cfg)
    for part in cfg["parts"]:
        if "height_anchor" in part:
            part.pop("dimensions")
    output = Path(output).resolve()
    if output == recipe.parent:
        raise ValueError("preparation output must be separate from the source recipe")
    output.mkdir(parents=True, exist_ok=True)
    rows = []
    for part in cfg["parts"]:
        ref = Path(part.get("reference", cfg.get("reference", "")))
        ref = ref if ref.is_absolute() else recipe.parent / ref
        part["reference"] = str(ref.resolve())
        for key in ("part_map",):
            if part.get(key, cfg.get(key)):
                path = Path(part.get(key, cfg.get(key)))
                part[key] = str((path if path.is_absolute() else recipe.parent / path).resolve())
        part["masks"] = {view: str((Path(path) if Path(path).is_absolute() else recipe.parent / path).resolve()) for view, path in part.get("masks", {}).items()}
        if part.get('surface_detail', {}).get('height_map'):
            path = Path(part['surface_detail']['height_map'])
            part['surface_detail']['height_map'] = str((path if path.is_absolute() else recipe.parent / path).resolve())
        sizes = {}
        with Image.open(ref) as source:
            source = source.convert("RGB")
            overlay = source.copy()
            draw = ImageDraw.Draw(overlay)
            for view, box in part["views"].items():
                if len(box) != 4 or any(type(v) is not int for v in box) or min(box) < 0 or box[2] <= box[0] or box[3] <= box[1] or box[2] > source.width or box[3] > source.height:
                    raise ValueError(f"{part['name']}.{view}: invalid source region")
                path = output / f"{part['name']}_{view}.png"
                source.crop(box).save(path)
                mask, _ = silhouette(str(path))
                sizes[view] = [mask.shape[1], mask.shape[0]]
                draw.rectangle(box, outline="red", width=2)
                draw.text((box[0], box[1]), view, fill="red")
            overlay.save(output / f"{part['name']}_regions.png")
        anchor = part.pop("height_anchor", None)
        if anchor is not None:
            if "dimensions" in part:
                raise ValueError("choose supplied dimensions or height_anchor, not both")
            side = "right" if "right" in sizes else "left"
            if "front" not in sizes or side not in sizes:
                raise ValueError("height scaling requires front and side silhouettes")
            part["dimensions"] = from_height(sizes["front"], sizes[side], anchor["metres"])
            cfg["dimensions_assumed"] = True
            cfg.setdefault("assumptions", []).append(f"{part['name']}: dimensions scaled from height anchor {anchor['metres']} m; {anchor.get('source', 'unspecified source')}")
        rows.append({"name": part["name"], "silhouette_pixels": sizes, "dimensions": part.get("dimensions"), "height_anchor": anchor})
    cfg = validate_manifest(cfg)
    (output / "manifest.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    (output / "preparation-report.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    return str(output / "manifest.json")
