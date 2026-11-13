"""One operations entry point; existing stations retain their own algorithms.

Checks never update golden baselines, delete releases, install dependencies or
change code. Reports declare capability coverage and retain failed observations.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import zipfile
import uuid
from . import warehouse


def git(root, *args):
    return subprocess.check_output(
        ["git", "-c", "safe.directory=" + str(root), *args],
        cwd=root,
        text=True,
        encoding="utf-8",
    )


def load_plan(root):
    plan = json.loads(
        (root / "long-lines/factory/checks.json").read_text(encoding="utf-8")
    )
    if plan.get("schema") != 1:
        raise ValueError("Unsupported check manifest")
    seen = set()
    for check in plan["checks"]:
        if check["id"] in seen or check["capability"] not in (
            "core",
            "blender",
            "godot",
            "cad",
            "vision",
        ):
            raise ValueError("Duplicate or unknown check capability")
        seen.add(check["id"])
        if check.get("runner", "python") not in ("python", "blender"):
            raise ValueError("Unknown check runner: " + check["id"])
        if (
            check.get("script")
            and not warehouse.inside(root, check["script"]).is_file()
        ):
            raise ValueError("Missing declared check: " + check["id"])
    return plan


def doctor(root, required=("core",), blender=None, godot=None):
    evidence = {
        "python": sys.version.split()[0],
        "packages": {},
        "tools": {},
        "fails": [],
    }
    if "core" in required:
        if sys.version_info[:2] != (3, 13):
            evidence["fails"].append(
                "Qualified core requires Python 3.13; other versions are not certified"
            )
        modules = {
            "numpy": "numpy",
            "scipy": "scipy",
            "Pillow": "PIL",
            "scikit-image": "skimage",
            "opencv-python-headless": "cv2",
        }
        pins = dict(
            re.findall(
                r"^([\w-]+)==([^\s]+)$",
                (root / "requirements-core.txt").read_text(),
                re.M,
            )
        )
        for package, module in modules.items():
            try:
                importlib.import_module(module)
                version = importlib.metadata.version(package)
                evidence["packages"][package] = version
                if version != pins[package]:
                    evidence["fails"].append(package + " differs from qualified pin")
            except (
                ImportError,
                OSError,
                importlib.metadata.PackageNotFoundError,
            ) as error:
                evidence["fails"].append(package + ": " + str(error))
    if "cad" in required:
        try:
            importlib.import_module("OCP")
        except (ImportError, OSError) as error:
            evidence["fails"].append("CAD backend required: " + str(error))
    if "vision" in required:
        pins = dict(re.findall(
            r"^([\w-]+)==([^\s]+)$",
            (root / "requirements-vision.txt").read_text(), re.M,
        ))
        for package, module in (("rapidocr", "rapidocr"),
                                ("onnxruntime", "onnxruntime")):
            try:
                importlib.import_module(module)
                version = importlib.metadata.version(package)
                evidence["packages"][package] = version
                if version != pins[package]:
                    evidence["fails"].append(package + " differs from qualified pin")
            except (ImportError, OSError, importlib.metadata.PackageNotFoundError) as error:
                evidence["fails"].append(package + ": " + str(error))
    for capability, configured, expected in [
        ("blender", blender or os.environ.get("HULL_BLENDER"), "Blender 5.2.3"),
        ("godot", godot or os.environ.get("HULL_GODOT"), "4.4.1"),
    ]:
        if capability not in required:
            continue
        executable = configured or shutil.which(capability)
        if not executable:
            evidence["fails"].append("Required executable unavailable: " + capability)
            continue
        try:
            process = subprocess.run(
                [executable, "--version"], capture_output=True, text=True, timeout=30
            )
            version = process.stdout.strip().splitlines()[0]
            evidence["tools"][capability] = {
                "path": str(Path(executable).resolve()),
                "version": version,
            }
            if process.returncode or not version.startswith(expected):
                evidence["fails"].append(
                    capability + " is outside the tested version profile"
                )
        except (OSError, subprocess.TimeoutExpired, IndexError) as error:
            evidence["fails"].append(capability + ": " + str(error))
    evidence["pass"] = not evidence["fails"]
    evidence["qualified_capabilities"] = list(required) if evidence["pass"] else []
    return evidence


def choose_profiles(paths):
    """Cheap docs checks; unknown changes conservatively require core checks."""
    if not paths:
        return ["core"]
    profiles = set()
    for raw in paths:
        name = raw.replace("\\", "/")
        if name == "requirements-vision.txt" or name.startswith(
            ("long-lines/tools/propkit/vision", "long-lines/tools/sheet_blobs")
        ) or name.startswith(("long-lines/tools/test_automatic_intake",
                              "long-lines/tools/test_automatic_build")):
            profiles.update(("core", "blender", "vision"))
            continue
        if name.startswith("long-lines/scripts/") or (
            name.startswith("long-lines/tests/") and name.endswith(".gd")
        ):
            profiles.add("godot")
        elif name.startswith("long-lines/tools/") or (
            name.startswith("long-lines/factory/") and name.endswith(".json")
        ):
            profiles.add("core")
            if any(
                part in name for part in ("propkit/", "factory.py", "geometry_baseline")
            ):
                profiles.add("blender")
        elif name.startswith("long-lines/assets/"):
            profiles.update(("core", "blender"))
        elif name.endswith((".md", ".png", ".jpg")):
            continue
        else:
            profiles.add("core")
    return sorted(profiles)


def repository_audit(root):
    fails = []
    warnings = []
    plan = load_plan(root)
    for filename in (
        "README.md",
        "CONTRIBUTING.md",
        "SECURITY.md",
        "long-lines/factory/OPERATIONS.md",
    ):
        if not (root / filename).is_file():
            fails.append("Missing operating document: " + filename)
    workflow = (root / ".github/workflows/hull-contracts.yml").read_text()
    if "paths:" in workflow:
        fails.append(
            "Required core workflow must not silently skip configuration changes"
        )
    for path in (root / ".github/workflows").glob("*.yml"):
        text = path.read_text()
        if not re.search(r"permissions:\s*\n\s+contents: read", text):
            fails.append("No default read-only token policy: " + path.name)
        for action in re.findall(r"uses:\s*([^\s#]+)", text):
            if not action.startswith("./") and not re.search(r"@[0-9a-f]{40}$", action):
                fails.append("Action is not pinned: " + action)
    tracked = git(root, "ls-files").splitlines()
    large = []
    for name in tracked:
        path = root / name
        if path.is_file() and path.stat().st_size > 10 * 1024 * 1024:
            large.append({"path": name, "bytes": path.stat().st_size})
    if large:
        warnings.append(
            "Tracked large files need an asset/history policy; no history was rewritten"
        )
    warnings.append(
        "Server-side branch rules, secret-scanning settings and review enforcement require separate hosted verification"
    )
    return {
        "pass": not fails,
        "fails": fails,
        "warnings": warnings,
        "declared_checks": len(plan["checks"]),
        "large_tracked_files": sorted(large, key=lambda x: -x["bytes"])[:20],
        "scope": "local repository policy; not a vulnerability or physical-quality certification",
    }


def source_identity(root):
    """Fingerprint code and station configuration, excluding changing run records."""
    files = [root / "hull.py", root / "requirements-core.txt",
             root / "requirements-vision.txt"]
    for directory, pattern in [
        ("long-lines/tools", "*.py"),
        ("long-lines/scripts", "*.gd"),
        ("long-lines/tests", "*.gd"),
        (".github", "*.yml"),
    ]:
        files.extend((root / directory).rglob(pattern))
    files.extend((root / "long-lines/factory").glob("*.json"))
    return {
        p.relative_to(root).as_posix(): warehouse.digest(p)
        for p in files
        if p.is_file()
    }


def run_checks(root, profiles, output, blender=None, godot=None):
    if "vision" in profiles and "blender" not in profiles:
        raise ValueError("Vision qualification requires the Blender profile")
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    identity = source_identity(root)
    health = doctor(root, profiles, blender, godot)
    plan = load_plan(root)
    missing = set(profiles) - {check["capability"] for check in plan["checks"]}
    if missing:
        raise ValueError(
            "No checks registered for required profiles: " + ", ".join(sorted(missing))
        )
    policy = repository_audit(root)
    results = []
    if health["pass"]:
        for check in plan["checks"]:
            if check["capability"] not in profiles:
                continue
            script = check.get("script")
            if check.get("runner") == "blender" or check["capability"] == "blender":
                command = [
                    health["tools"]["blender"]["path"],
                    "-b",
                    "--factory-startup",
                    "--python-use-system-env",
                    "--python-exit-code",
                    "1",
                    "-t",
                    "3",
                    "-P",
                    str(root / script),
                ]
            elif check["capability"] == "godot":
                command = [
                    health["tools"]["godot"]["path"],
                    "--headless",
                    "--path",
                    str(root / "long-lines"),
                    *check["args"],
                ]
            elif check.get("args"):
                command = [sys.executable, *check["args"]]
            else:
                command = [sys.executable, str(root / script)]
            environment = os.environ.copy()
            environment["PYTHONPATH"] = os.pathsep.join(
                [
                    str(root / "long-lines/tools"),
                    *sys.path,
                    environment.get("PYTHONPATH", ""),
                ]
            )
            environment.update(
                PYTHONHASHSEED="0",
                OPENBLAS_NUM_THREADS="1",
                HULL_TRACE_BACKEND="classical",
                APPDATA=str(output / "user-data"),
            )
            started = time.monotonic()
            try:
                process = subprocess.run(
                    command,
                    cwd=root,
                    env=environment,
                    capture_output=True,
                    text=True,
                    timeout=check.get("timeout_s", 300),
                )
                text = process.stdout + process.stderr
                code = process.returncode
            except (OSError, subprocess.TimeoutExpired) as error:
                text = str(error)
                code = -1
            (output / (check["id"] + ".log")).write_text(text, encoding="utf-8")
            skipped = sum(int(n) for n in re.findall(r"skipped=(\d+)", text))
            passed = code == 0 and not skipped
            results.append(
                {
                    "id": check["id"],
                    "capability": check["capability"],
                    "pass": passed,
                    "exit_code": code,
                    "skipped": skipped,
                    "seconds": round(time.monotonic() - started, 3),
                    "log": check["id"] + ".log",
                }
            )
            print(check["id"], "PASS" if passed else "FAIL", flush=True)
    unchanged = identity == source_identity(root)
    result = {
        "pass": health["pass"]
        and policy["pass"]
        and unchanged
        and all(r["pass"] for r in results),
        "profiles": profiles,
        "source_unchanged_during_checks": unchanged,
        "repository_policy": policy,
        "runtime": health,
        "checks": results,
        "physical_geometry_verified": False,
        "source_hashes": identity,
    }
    warehouse.atomic_json(output / "qualification.json", result)
    return result


def package(root, destination):
    """A deterministic code bundle from committed bytes, excluding user assets."""
    destination = Path(destination).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    selected = []
    for name in git(root, "ls-tree", "-r", "--name-only", "HEAD").splitlines():
        path = Path(name)
        allowed = (
            name.startswith(
                (
                    "long-lines/tools/",
                    "long-lines/scripts/",
                    "long-lines/tests/",
                    "long-lines/data/",
                    "long-lines/shaders/",
                    "long-lines/scenes/",
                    "long-lines/factory/",
                    ".github/",
                )
            )
            or name
            in (
                "hull.py",
                "Hull.cmd",
                "README.md",
                "CONTRIBUTING.md",
                "SECURITY.md",
                "LICENSE",
                ".gitignore",
                "CLAUDE.md",
                "KNOWLEDGE_FILE.md",
                "long-lines/project.godot",
                "long-lines/README.md",
                "long-lines/CLAUDE.md",
                "long-lines/docs/LESSONS.md",
            )
            or name.startswith("requirements")
            or name.startswith("docs/")
        )
        if (
            allowed
            and "/orders/" not in name
            and (
                path.suffix.lower()
                in (
                    ".py",
                    ".gd",
                    ".json",
                    ".md",
                    ".txt",
                    ".yml",
                    ".yaml",
                    ".cmd",
                    ".godot",
                    ".gdshader",
                    ".tscn",
                )
                or name in ("LICENSE", ".gitignore", ".github/CODEOWNERS")
            )
            and path.name not in ("ledger.jsonl", "REPORT.md")
        ):
            selected.append(name)
    metadata = {
        "kind": "code_only",
        "commit": git(root, "rev-parse", "HEAD").strip(),
        "tree": git(root, "rev-parse", "HEAD^{tree}").strip(),
        "files": {},
        "excludes": "models, trained weights, dependencies, user images, generated assets and private run records",
    }
    with zipfile.ZipFile(
        destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as archive:
        for name in sorted(selected):
            raw = subprocess.check_output(
                ["git", "-c", "safe.directory=" + str(root), "show", "HEAD:" + name],
                cwd=root,
            )
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, raw)
            metadata["files"][name] = hashlib.sha256(raw).hexdigest()
        info = zipfile.ZipInfo("PACKAGE-MANIFEST.json", date_time=(1980, 1, 1, 0, 0, 0))
        info.create_system = 3
        info.external_attr = 0o100644 << 16
        info.compress_type = zipfile.ZIP_DEFLATED
        archive.writestr(info, json.dumps(metadata, indent=2, sort_keys=True))
    return {
        "path": str(destination),
        "sha256": warehouse.digest(destination),
        "files": len(selected),
        "kind": "code_only",
    }


def incident(receipt_path, hypothesis, outcome, next_action):
    """Append learning evidence without revising a candidate's measurements."""
    receipt_path = Path(receipt_path).resolve()
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if not all(value.strip() for value in (hypothesis, outcome, next_action)):
        raise ValueError(
            "An incident needs a hypothesis, observed outcome and next action"
        )
    record = {
        "schema": 1,
        "time": datetime.now(timezone.utc).isoformat(),
        "run_id": receipt["run_id"],
        "receipt_sha256": warehouse.digest(receipt_path),
        "hypothesis": hypothesis,
        "observed_outcome": outcome,
        "next_action": next_action,
        "qa_overridden": False,
    }
    path = receipt_path.parent / "incidents" / (uuid.uuid4().hex + ".json")
    warehouse.atomic_json(path, record)
    return {"pass": True, "path": str(path), "qa_overridden": False}


def main(root):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("doctor", "check", "qualify", "audit"):
        sub = commands.add_parser(name)
        sub.add_argument(
            "--profiles", default="core,blender,godot" if name == "qualify" else "core"
        )
        sub.add_argument("--blender")
        sub.add_argument("--godot")
        sub.add_argument(
            "--output", type=Path, default=root / ".hull-maintenance/latest"
        )
        sub.add_argument("--changed-files", nargs="*")
    sub = commands.add_parser("package")
    sub.add_argument("--output", type=Path, required=True)
    sub = commands.add_parser("promote")
    sub.add_argument("receipt", type=Path)
    sub.add_argument("--qualification", type=Path, required=True)
    sub = commands.add_parser("verify-release")
    sub.add_argument("name")
    sub = commands.add_parser("rollback")
    sub.add_argument("receipt", type=Path)
    sub.add_argument("--expected-release", required=True)
    sub = commands.add_parser("incident")
    sub.add_argument("receipt", type=Path)
    sub.add_argument("--hypothesis", required=True)
    sub.add_argument("--outcome", required=True)
    sub.add_argument("--next-action", required=True)
    args = parser.parse_args()
    try:
        if args.command == "package":
            result = package(root, args.output)
        elif args.command == "promote":
            result = warehouse.promote(
                args.receipt, root / "long-lines/assets/props", args.qualification
            )
        elif args.command == "verify-release":
            result = warehouse.verify_release(
                root / "long-lines/assets/props", args.name
            )
        elif args.command == "rollback":
            result = warehouse.rollback(
                args.receipt, root / "long-lines/assets/props", args.expected_release
            )
        elif args.command == "incident":
            result = incident(
                args.receipt, args.hypothesis, args.outcome, args.next_action
            )
        elif args.command == "audit":
            result = repository_audit(root)
            warehouse.atomic_json(args.output / "repository-audit.json", result)
        else:
            profiles = (
                choose_profiles(args.changed_files)
                if args.changed_files is not None
                else args.profiles.split(",")
            )
            if not set(profiles) <= {"core", "blender", "godot", "cad", "vision"}:
                raise ValueError("Unknown capability profile")
            if args.command == "doctor":
                result = doctor(root, profiles, args.blender, args.godot)
            else:
                result = run_checks(
                    root, profiles, args.output, args.blender, args.godot
                )
        print(json.dumps(result, indent=2))
        return 0 if result.get("pass", True) else 1
    except (
        OSError,
        ValueError,
        KeyError,
        RuntimeError,
        subprocess.SubprocessError,
    ) as error:
        print(json.dumps({"pass": False, "error": str(error)}))
        return 1
