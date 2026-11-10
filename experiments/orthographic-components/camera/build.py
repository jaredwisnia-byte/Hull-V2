"""Compatibility launcher; production implementation lives in propkit.components."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.environ['HULL_TOOLS'])
sys.path.insert(0, os.environ['HULL_PYTHON_DEPS'])
from propkit.components.pipeline import build

base = Path(__file__).resolve().parent
output = Path(os.environ.get('HULL_OUTPUT', str(base / 'output')))
result = build(base / 'manifest.json', output)
print(json.dumps(result))
