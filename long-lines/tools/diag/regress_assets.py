"""Retained, isolated asset regression; never edits the real library or baseline.

--update-baseline writes an OBSERVATION PROPOSAL in --output, not a golden file.
A baseline comparison is not release approval; inherited fixtures may be defective.
"""

import argparse
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
from propkit import warehouse

ROOT = TOOLS.parent
CASES = {
    "car": (
        "factory/orders/car_sedan_tan.json",
        "assets/source_textures/car_sedan_tan",
    ),
    "coffee": (
        "factory/orders/coffee_maker_drip.json",
        "assets/source_textures/coffee_maker_drip/assembly",
    ),
    "sofa": (
        "factory/fixtures/fixture_sofa_parts.json",
        "assets/source_textures/fixture_sofa_parts/assembly",
    ),
    "wallphone": (
        "factory/fixtures/fixture_wallphone_parts.json",
        "assets/source_textures/fixture_wallphone_parts/assembly",
    ),
}
BASE = ROOT / "factory/geometry_baseline.json"


def compare(metrics, baseline):
    failures = []
    for key in ("iou_mean", "ridge_deg", "folds_per_1k", "tris"):
        if not isinstance(metrics.get(key), (int, float)) or not math.isfinite(
            metrics[key]
        ):
            failures.append("Missing finite metric: " + key)
    if failures:
        return failures
    if not baseline:
        return ["No reviewed comparison baseline"]
    if metrics["iou_mean"] < baseline["iou_mean"] - 0.005:
        failures.append("Silhouette IoU fell beyond .005 allowance")
    if metrics["folds_per_1k"] > baseline["folds_per_1k"] + 0.5:
        failures.append("Fold rate rose beyond .5/1k allowance")
    if metrics["ridge_deg"] > baseline["ridge_deg"] + 0.3:
        failures.append("Ridge score rose beyond .3 degree allowance")
    return failures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", default=",".join(CASES))
    parser.add_argument(
        "--blender", default=os.environ.get("HULL_BLENDER", shutil.which("blender"))
    )
    parser.add_argument("--output", "--keep", type=Path)
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Retain observation proposal; never edits the reviewed baseline",
    )
    args = parser.parse_args()
    names = args.only.split(",")
    if not set(names) <= CASES.keys():
        parser.error("Unknown fixture")
    if not args.blender:
        parser.error("Provide --blender or HULL_BLENDER")
    output = (
        args.output or ROOT.parent / ".hull-maintenance/regression"
    ).resolve() / uuid.uuid4().hex
    work = output / "repository/long-lines"
    work.mkdir(parents=True)
    shutil.copytree(
        ROOT / "tools", work / "tools", ignore=shutil.ignore_patterns("__pycache__")
    )
    shutil.copytree(
        ROOT / "factory",
        work / "factory",
        ignore=shutil.ignore_patterns("orders", "ledger.jsonl", "REPORT.md"),
    )
    (work / "factory/orders").mkdir()
    warehouse.atomic_json(work / "assets/props/library.json", {})
    environment = dict(
        os.environ,
        PYTHONHASHSEED="0",
        HULL_RELEASE_POLICY="hold",
        HULL_RUN_ROOT=str(output / "runs"),
        OPENBLAS_NUM_THREADS="1",
    )
    base = json.loads(BASE.read_text())
    results = {}

    def run(script, argv, log):
        command = [
            args.blender,
            "-b",
            "--factory-startup",
            "--python-use-system-env",
            "--python-exit-code",
            "1",
            "-t",
            "3",
            "-P",
            str(work / script),
            "--",
            *map(str, argv),
        ]
        process = subprocess.run(
            command,
            cwd=work,
            env=environment,
            capture_output=True,
            text=True,
            timeout=1200,
        )
        (output / log).write_text(process.stdout + process.stderr, encoding="utf-8")
        if process.returncode:
            raise RuntimeError("Native process failed; inspect " + log)

    for name in names:
        started = time.monotonic()
        try:
            order_path, views = CASES[name]
            order = json.loads((ROOT / order_path).read_text())
            folder = warehouse.inside(
                ROOT / "assets/source_textures", order["views_folder"]
            )
            target = warehouse.inside(
                work / "assets/source_textures", order["views_folder"]
            )
            shutil.copytree(folder, target)
            asset = "exp_regress_" + name
            for key in ("measured", "attempts", "qa", "last_run", "run_directory"):
                order.pop(key, None)
            order.update(name=asset, status="pending")
            warehouse.atomic_json(work / "factory/orders" / (asset + ".json"), order)
            run("tools/factory.py", ["build", asset], name + "-build.log")
            saved = json.loads(
                (work / "factory/orders" / (asset + ".json")).read_text()
            )
            current = json.loads((Path(saved["last_run"]) / "result.json").read_text())
            candidate_library = Path(current["artifact_library_root"])
            glb = warehouse.asset_directory(candidate_library, asset) / (asset + ".glb")
            metric_path = output / (name + "-metrics.json")
            run(
                "tools/diag/metrics.py",
                [glb, work / views, "--json", metric_path],
                name + "-metrics.log",
            )
            metrics = json.loads(metric_path.read_text())
            failures = compare(metrics, base.get(name))
            if current.get("artifact_audit", {}).get("pass") is not True:
                failures.append("Candidate artifact/input audit failed")
            if current["pass"] is not True:
                failures.append("Build QA failed: " + "; ".join(current["fails"]))
            if current.get("inference_warnings"):
                failures.append("Build has unresolved inference warnings")
            results[name] = {
                "metrics": metrics,
                "failures": failures,
                "receipt": current.get("candidate_receipt"),
                "build_disposition": current["disposition"],
            }
        except (
            OSError,
            ValueError,
            KeyError,
            RuntimeError,
            subprocess.SubprocessError,
        ) as error:
            results[name] = {"failures": [str(error)]}
        results[name]["seconds"] = round(time.monotonic() - started, 2)
        print(
            name,
            "FAIL" if results[name]["failures"] else "PASS",
            results[name]["failures"],
            flush=True,
        )
    result = {
        "pass": all(not r["failures"] for r in results.values()),
        "cases": results,
        "baseline_sha256": warehouse.digest(BASE),
        "baseline_changed": False,
        "output": str(output),
        "scope": "retained isolated observations; not physical depth certification",
    }
    warehouse.atomic_json(output / "regression.json", result)
    if args.update_baseline:
        warehouse.atomic_json(
            output / "baseline-proposal.json",
            {
                "review_status": "unreviewed",
                "observations": results,
                "baseline_sha256": warehouse.digest(BASE),
                "instructions": "Review each fixture, known failures and measurement validity before a separate baseline change",
            },
        )
    print("ASSET REGRESSION:", json.dumps(result))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
