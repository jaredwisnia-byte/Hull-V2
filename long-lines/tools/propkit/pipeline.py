"""Image-only orchestration. Geometry stays in the existing factory engines.

Callbacks keep this station testable without importing or duplicating factory
dispatch. All file freshness checks belong here, before packaging or reporting.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import time


def is_fresh(path, started_ns):
    return path.is_file() and path.stat().st_mtime_ns >= started_ns


def available_digest(path):
    """Failure reporting must also work when the source file is unreadable."""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def render_asset(name, destination, render_script, library_root=None):
    import bpy
    command = [
        bpy.app.binary_path, "-b", "--factory-startup", "--python-use-system-env",
        "--python-exit-code", "1", "-P", str(render_script),
        "--", name, str(destination),
    ]
    started_ns = time.time_ns()
    import os
    environment = os.environ.copy()
    if library_root is not None:
        environment['HULL_LIBRARY_ROOT'] = str(library_root)
    process = subprocess.run(command, capture_output=True, text=True, env=environment)
    (destination / "render.log").write_text(process.stdout + process.stderr)
    image = destination / (name + ".png")
    if process.returncode == 0 and is_fresh(image, started_ns):
        return str(image)
    return None


def _build_image(image, output, *, build_order, library_root, render_script, export_model,
                 cad_export=False, view_distance_m=None):
    """Intake -> native work order -> build/QA -> fresh exports -> diagnostics."""
    from sheet_blobs import automatic
    from . import engineering

    image = Path(image).resolve()
    destination = Path(output).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    result = {
        "input_image": str(image),
        "input_sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
        "runtime_llm": False,
        "status": "needs_review",
    }
    intake = automatic(image, destination / "intake")
    if intake["status"] != "ready_to_build":
        result["intake_failure"] = intake.get(
            "failure", "unresolved visual assignments")
    else:
        order = json.loads(Path(intake["work_order"]).read_text())
        order['cad_export'] = bool(cad_export)
        if view_distance_m is not None:
            if not 0.1 <= float(view_distance_m) <= 100:
                raise ValueError('viewing distance must be between 0.1 and 100 metres')
            order['view_distance_m'] = float(view_distance_m)
        name = order["name"]
        result["assumptions"] = order["assumptions"]
        warnings = [part["name"] for part in order.get("parts", [])
                    if part.get("depth_inference", {}).get("needs_review")]
        if order.get('unresolved_component_regions'):
            warnings.append('unresolved_companion_parts')
        if order.get('physical_part_graph',{}).get('needs_review'):
            warnings.append('unresolved_physical_part_ownership')
        if order.get("automatic_depth"):
            from .preflight import inspect_order
            order["view_consistency"] = inspect_order(
                order, Path(library_root).parent / "source_textures",
                destination / "view-consistency",
            )
            result["view_consistency"] = order["view_consistency"]
            if order["view_consistency"]["status"] == "needs_review":
                warnings.append("view_consistency")
        result["inference_warnings"] = warnings
        build_started_ns = time.time_ns()
        result["qa"] = build_order(order)
        warnings.extend(order.get('inference_warnings', []))
        warnings.extend(result['qa'].get('inference_warnings', []))
        library_root = result['qa'].get('artifact_library_root', library_root)
        from .warehouse import asset_directory
        artifact = asset_directory(library_root, name) / (name + '.glb')
        if is_fresh(artifact, build_started_ns):
            result.update(export_model(name, library_root, destination))
            if order.get("automatic_depth"):
                result.update(engineering.export(order, destination))
            result["render"] = render_asset(name, destination, render_script, library_root)
            if result["qa"]["pass"] and result["render"] and not warnings:
                result["status"] = "complete"
        else:
            result["export_failure"] = "Current build did not produce a fresh model"
    result["seconds"] = round(time.monotonic() - started, 2)
    from .memory_outcomes import record
    result['build_memory']=record(result,{'source':str(image),'station':'image_pipeline'})
    (destination / "result.json").write_text(json.dumps(result, indent=2))
    print("AUTOMATIC_RESULT", json.dumps(result))
    return result


def build_image(image, output, **stations):
    """Persist a reviewable failure report even if a station raises unexpectedly."""
    import traceback
    destination = Path(output).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    try:
        return _build_image(image, destination, **stations)
    except Exception as error:
        log = destination / "pipeline-error.log"
        log.write_text(traceback.format_exc())
        source = Path(image).resolve()
        result = {
            "input_image": str(source),
            "input_sha256": available_digest(source),
            "runtime_llm": False,
            "status": "needs_review",
            "pipeline_failure": str(error),
            "error_log": str(log),
            "seconds": round(time.monotonic() - started, 2),
        }
        from .memory_outcomes import record
        result['build_memory']=record(result,{'source':str(source),'station':'image_pipeline_failure'})
        (destination / "result.json").write_text(json.dumps(result, indent=2))
        print("AUTOMATIC_RESULT", json.dumps(result))
        return result
