"""Hull V2 operations: doctor, check, qualify, audit, promote and package."""

from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parent
for folder in reversed([ROOT / ".hull-runtime", ROOT / ".hull-models/runtime"]):
    if folder.is_dir():
        sys.path.insert(0, str(folder))
sys.path.insert(0, str(ROOT / "long-lines/tools"))

if __name__ == "__main__":
    from propkit.maintenance import main

    raise SystemExit(main(ROOT))
