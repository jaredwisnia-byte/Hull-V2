"""Read-only retention checks for a reviewed set of workspace evidence.

The manifest grants no permission to move, compress or delete a file. A new
file, changed file, or incomplete scan requires an owner to review the set.
"""

import hashlib
import json
import os
from pathlib import Path
import re


def _relative_path(root, value):
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        raise ValueError("Manifest paths must be root-relative with / separators")
    parts = value.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise ValueError("Manifest path has an empty or unsafe component: " + value)
    path = root.joinpath(*parts)
    if not path.resolve().is_relative_to(root):
        raise ValueError("Manifest path escapes the workspace: " + value)
    return path


def _digest(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify(manifest_path, verify_hashes=False):
    """Compare a bounded, owner-reviewed array set with its recorded evidence."""
    manifest_path = Path(manifest_path).resolve(strict=True)
    source_before = manifest_path.read_bytes()
    manifest = json.loads(source_before)
    if not isinstance(manifest, dict) or manifest.get("schema") != 1:
        raise ValueError("Unsupported retention manifest schema")
    root_value = manifest.get("root")
    if not isinstance(root_value, str) or not Path(root_value).is_absolute():
        raise ValueError("Retention manifest needs an absolute workspace root")
    root = Path(root_value).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Retention workspace root is not a directory")
    managed = manifest.get("managed_roots")
    listed = manifest.get("files")
    budget = manifest.get("budget_logical_bytes")
    if (not isinstance(managed, list) or not managed or
            not isinstance(listed, list) or not listed or
            isinstance(budget, bool) or not isinstance(budget, int) or budget < 0):
        raise ValueError("Retention manifest needs managed roots, files and a byte budget")
    managed_paths = [_relative_path(root, value) for value in managed]
    if len(set(managed_paths)) != len(managed_paths):
        raise ValueError("Duplicate managed root")
    if any(not path.is_dir() for path in managed_paths):
        raise ValueError("A managed root is missing or is not a directory")
    expected = {}
    seen_paths = set()
    for item in listed:
        if not isinstance(item, dict):
            raise ValueError("Retention file entry is not an object")
        name = item.get("path")
        path = _relative_path(root, name)
        size, digest = item.get("bytes"), item.get("sha256")
        if (path in seen_paths or not any(path.is_relative_to(parent)
                                        for parent in managed_paths) or
                path.suffix.lower() != ".npy" or
                isinstance(size, bool) or not isinstance(size, int) or size < 0 or
                not isinstance(digest, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", digest) or
                not all(isinstance(item.get(key), str) and item[key].strip()
                        for key in ("owner", "role", "decision"))):
            raise ValueError("Invalid or duplicate retention file entry: " + str(name))
        expected[name] = item
        seen_paths.add(path)

    observed = set()
    scan_errors = []
    for parent in managed_paths:
        def on_error(error):
            scan_errors.append(str(error))
        for directory, dirs, files in os.walk(parent, onerror=on_error):
            for dirname in dirs:
                if (Path(directory) / dirname).is_symlink():
                    scan_errors.append("Symlink directory in managed root: " +
                                       str(Path(directory) / dirname))
            for filename in files:
                path = Path(directory) / filename
                if path.suffix.lower() == ".npy":
                    observed.add(path.relative_to(root).as_posix())
    results = []
    total_bytes = 0
    for name, item in expected.items():
        path = _relative_path(root, name)
        result = {"path": name, "expected_bytes": item["bytes"],
                  "status": "missing"}
        try:
            if path.is_symlink():
                result["status"] = "symlink"
            elif path.is_file():
                before = path.stat()
                result["actual_bytes"] = before.st_size
                total_bytes += before.st_size
                if before.st_size != item["bytes"]:
                    result["status"] = "size_mismatch"
                elif verify_hashes:
                    actual_hash = _digest(path)
                    after = path.stat()
                    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                        result["status"] = "changed_during_hash"
                    elif actual_hash.lower() != item["sha256"].lower():
                        result["status"] = "hash_mismatch"
                    else:
                        result["status"] = "verified"
                else:
                    result["status"] = "metadata_match"
        except OSError as error:
            result["status"] = "unreadable"
            result["error"] = str(error)
        results.append(result)
    unlisted = sorted(observed - set(expected))
    manifest_unchanged = source_before == manifest_path.read_bytes()
    return {
        "pass": (not scan_errors and not unlisted and
                 all(item["status"] in ("verified", "metadata_match") for item in results)
                 and total_bytes <= budget and manifest_unchanged),
        "manifest": str(manifest_path), "root": str(root),
        "managed_roots": managed,
        "hashes_checked": verify_hashes,
        "manifest_unchanged": manifest_unchanged,
        "budget_logical_bytes": budget, "observed_logical_bytes": total_bytes,
        "unlisted_arrays": unlisted, "scan_errors": scan_errors,
        "files": results,
        "collection_authorized": False,
    }
