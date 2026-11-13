"""Read-only, bounded-summary inventory of a workspace tree.

The report never calls a folder orphaned merely because it is large or old.
Unclassified Hull folders are candidates for an owner/retention review.
"""

from datetime import datetime, timezone
import os
from pathlib import Path


def scan(root, classification=None, previous=None):
    root = Path(root).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Workspace root must be a directory")
    classification = classification or {}
    previous = previous or {}
    if previous and previous.get("root") != str(root):
        raise ValueError("Previous inventory has a different workspace root")
    old = previous.get("top_level", {})
    top = {}
    errors = []
    incomplete = set()
    total_bytes = 0
    file_count = 0
    directory_count = 0
    stack = [(root, None)]
    while stack:
        directory, owner = stack.pop()
        directory_count += 1
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    try:
                        if entry.is_symlink():
                            continue
                        top_name = owner or entry.name
                        bucket = top.setdefault(top_name, {"bytes": 0, "files": 0,
                                                           "kind": None})
                        if entry.is_dir(follow_symlinks=False):
                            if owner is None:
                                bucket["kind"] = "directory"
                            stack.append((Path(entry.path), top_name))
                        elif entry.is_file(follow_symlinks=False):
                            if owner is None:
                                bucket["kind"] = "file"
                            size = entry.stat(follow_symlinks=False).st_size
                            bucket["bytes"] += size
                            bucket["files"] += 1
                            total_bytes += size
                            file_count += 1
                    except OSError as error:
                        incomplete.add(top_name)
                        errors.append({"path": entry.path, "error": str(error)})
        except OSError as error:
            incomplete.add(owner or "[root]")
            errors.append({"path": str(directory), "error": str(error)})
    partial = bool(errors)
    for name, bucket in top.items():
        bucket["role"] = classification.get(name)
        bucket["partial"] = name in incomplete or "[root]" in incomplete
        prior = old.get(name, {}).get("bytes")
        bucket["delta_bytes"] = (bucket["bytes"] - prior
                                 if prior is not None and not bucket["partial"]
                                 and not old[name].get("partial") else None)
    # Absence at the root is evidence of a change, not evidence of deletion.
    # If the root itself could not be scanned, even that observation is unknown.
    removed_top_level = None if "[root]" in incomplete else [
        {"name": name, "prior_bytes": old[name].get("bytes"),
         "prior_role": old[name].get("role"),
         "prior_partial": old[name].get("partial", False)}
        for name in sorted(set(old) - set(top))
    ]
    return {
        "schema": 1,
        "captured_utc": datetime.now(timezone.utc).isoformat(),
        "root": str(root),
        "total_bytes": total_bytes,
        "file_count": file_count,
        "directory_count": directory_count,
        "partial": partial,
        "errors": errors,
        "top_level": dict(sorted(top.items())),
        "no_longer_at_root": removed_top_level,
        "review_candidates": sorted(
            name for name, item in top.items() if item["kind"] == "directory"
            and name.startswith("Hull-") and name not in classification
        ),
        "notes": "Review candidates have no assigned role; they are not verified orphans. Items no longer at the root may have been moved and are not verified deletions."
    }
