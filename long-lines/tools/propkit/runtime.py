"""Portable, writable scratch paths for Blender workers."""
import os
import re
import tempfile
from pathlib import Path


def scratch_dir(name):
    root = Path(os.environ.get("HULL_WORK_DIR", Path(tempfile.gettempdir()) / "hull-v2"))
    directory = root / re.sub(r"[^A-Za-z0-9_.-]", "_", name)
    directory.mkdir(parents=True, exist_ok=True)
    return str(directory.resolve())
