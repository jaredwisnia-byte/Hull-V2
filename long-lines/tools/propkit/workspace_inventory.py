"""Read-only, bounded-summary inventory of a workspace tree.

The report never calls an item orphaned merely because it is large or old.
Unclassified root items are candidates for an owner/retention review.
"""

from datetime import datetime, timezone
from functools import lru_cache
import os
from pathlib import Path


@lru_cache(maxsize=1)
def _compressed_size_api():
    import ctypes
    function = ctypes.WinDLL('kernel32', use_last_error=True).GetCompressedFileSizeW
    function.argtypes = (ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_ulong))
    function.restype = ctypes.c_ulong
    return function


def allocated_size(path):
    """Report Windows allocated bytes, including transparent compression.

    This is a per-file allocation observation, not a deduplicated drive-usage
    total: separate paths to one hard-linked file can be counted twice.
    """
    if os.name != 'nt':
        return None
    import ctypes
    high = ctypes.c_ulong()
    ctypes.set_last_error(0)
    low = _compressed_size_api()(str(path), ctypes.byref(high))
    if low == 0xFFFFFFFF and ctypes.get_last_error():
        code = ctypes.get_last_error()
        raise OSError(code, os.strerror(code), str(path))
    return (high.value << 32) | low


def scan(root, classification=None, previous=None, include_allocated=False):
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
    allocated_bytes = 0
    allocated_files = 0
    allocation_errors = []
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
                        if include_allocated:
                            bucket.setdefault('allocated_bytes', 0)
                            bucket.setdefault('allocated_files', 0)
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
                            if include_allocated:
                                try:
                                    allocation = allocated_size(entry.path)
                                    if allocation is not None:
                                        bucket['allocated_bytes'] += allocation
                                        bucket['allocated_files'] += 1
                                        allocated_bytes += allocation
                                        allocated_files += 1
                                except OSError as error:
                                    allocation_errors.append({
                                        'path': entry.path, 'error': str(error)})
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
        if include_allocated:
            bucket['allocated_partial'] = (bucket['partial'] or
                                           bucket['allocated_files'] != bucket['files'])
            old_bucket = old.get(name, {})
            prior_allocated = old_bucket.get('allocated_bytes')
            bucket['delta_allocated_bytes'] = (
                bucket['allocated_bytes'] - prior_allocated
                if prior_allocated is not None and not bucket['allocated_partial']
                and not old_bucket.get('allocated_partial', True) else None)
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
        "allocated_bytes_observed": allocated_bytes if include_allocated else None,
        "allocated_file_count": allocated_files if include_allocated else None,
        "allocated_partial": (partial or allocated_files != file_count)
        if include_allocated else None,
        "allocation_errors": allocation_errors if include_allocated else [],
        "file_count": file_count,
        "directory_count": directory_count,
        "partial": partial,
        "errors": errors,
        "top_level": dict(sorted(top.items())),
        "no_longer_at_root": removed_top_level,
        "review_candidates": sorted(
            name for name in top if name not in classification
        ),
        "notes": "Review candidates are unclassified root items, not verified orphans. Items no longer at the root may have been moved and are not verified deletions."
    }
