"""Production API shared by the CLI, factory orders and legacy experiment launchers."""
import json
import copy
import time
from pathlib import Path

import bpy

from .. import bake, core, mats
from ..runtime import scratch_dir
from .manifest import load_manifest
from .placement import place
from .reconstruction import reconstruct, triangle_count
from .export import finish


def build_geometry(manifest_path, work_dir=None):
    cfg, root = load_manifest(manifest_path)
    work = Path(work_dir or scratch_dir("components_" + cfg["name"]))
    objects, frames, rows = {}, {}, []
    prototypes = {}
    specs = {p["name"]: p for p in cfg["parts"]}
    for spec in cfg["parts"]:
        prototype = spec.get("prototype")
        # Placement is excluded: shared prototypes keep local geometry and paint coordinates.
        key = json.dumps({k: v for k, v in spec.items() if k not in {"name", "position", "parent", "attachment", "mount", "mount_pixel"}}, sort_keys=True)
        if prototype and key in prototypes:
            mesh, frame, row = prototypes[key]
            obj = core.link(bpy.data.objects.new(spec["name"], mesh.copy()))
            frame, row = copy.deepcopy(frame), copy.deepcopy(row)
            row["name"], row["reused_prototype"] = spec["name"], prototype
        else:
            obj, frame, row = reconstruct(spec, cfg, root, work)
            if prototype:
                prototypes[key] = (obj.data.copy(), copy.deepcopy(frame), copy.deepcopy(row))
        row["attachment"] = place(obj, spec, objects, frames, specs)
        obj["component_origin"] = row["attachment"]["position"]
        from mathutils import Matrix
        obj['component_transform'] = row['attachment'].get('transform', [list(r) for r in Matrix.Translation(row['attachment']['position'])])
        group = obj.vertex_groups.new(name="hull_component_" + spec["name"])
        group.add(list(range(len(obj.data.vertices))), 1, "REPLACE")
        objects[spec["name"]], frames[spec["name"]] = obj, frame
        rows.append(row)
        bpy.context.view_layer.update()
    for mesh, _, _ in prototypes.values():
        bpy.data.meshes.remove(mesh)
    total = sum(triangle_count(o) for o in objects.values())
    if total > cfg["triangle_limit"]:
        raise RuntimeError("geometry exceeds the shared triangle limit")
    return cfg, {"parts": rows, "geometry_triangles": total, "triangle_limit": cfg["triangle_limit"],
                 "assumptions": cfg.get("assumptions", []), "dimensions_assumed": cfg.get("dimensions_assumed", True)}


def build(manifest_path, output_dir, work_dir=None, save_blend=True):
    started = time.monotonic()
    core.reset()
    mats.reset()
    cfg, report = build_geometry(manifest_path, work_dir)
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    info = bake.finish(cfg["name"], str(output_dir), cfg.get("texture", 1024), cfg.get("samples", 12),
                       triangle_budget=cfg["triangle_limit"])
    report.update(finish(cfg, output_dir, save_blend))
    report.update({"name": cfg["name"], "bake": info, "seconds": round(time.monotonic() - started, 2)})
    destination = output_dir / cfg["name"] / "build-report.json"
    destination.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
