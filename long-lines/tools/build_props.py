"""Builds library props: model, bake, export, and record in the manifest.

    blender -b --factory-startup -P tools/build_props.py -- all
    blender -b --factory-startup -P tools/build_props.py -- tv sofa --samples 16
    blender -b --factory-startup -P tools/build_props.py -- --list
    blender -b --factory-startup -P tools/build_props.py -- --tag kitchen

Options: --samples N (default 24), --tex N (override texture size), --skip-built.
"""
import importlib
import os
import pkgutil
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
ROOT = os.path.normpath(os.path.join(HERE, ".."))
OUT = os.path.join(ROOT, "assets", "props")
MANIFEST = os.path.join(OUT, "library.json")

import propkit  # noqa: E402
from propkit import bake, core, mats  # noqa: E402
import props  # noqa: E402

for mod in pkgutil.iter_modules(props.__path__):
    importlib.import_module("props." + mod.name)

args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
samples, tex_override, names, skip = 24, None, [], False
i = 0
while i < len(args):
    a = args[i]
    if a == "--samples":
        samples = int(args[i + 1]); i += 1
    elif a == "--tex":
        tex_override = int(args[i + 1]); i += 1
    elif a == "--skip-built":
        skip = True
    elif a == "--list":
        for n, p in sorted(propkit.PROPS.items()):
            print("%-24s %5d  %-10s %s" % (n, p["tex"], p["kind"], ",".join(p["tags"])))
        sys.exit(0)
    elif a == "--tag":
        names += [n for n, p in propkit.PROPS.items() if args[i + 1] in p["tags"]]; i += 1
    elif a == "all":
        names += sorted(propkit.PROPS)
    else:
        names.append(a)
    i += 1

failed = []
for n in names:
    if n not in propkit.PROPS:
        print("UNKNOWN", n)
        failed.append(n)
        continue
    if skip and os.path.exists(os.path.join(OUT, n, n + ".glb")):
        continue
    p = propkit.PROPS[n]
    t0 = time.time()
    try:
        core.reset()
        mats.reset()
        p["fn"]()
        info = bake.finish(n, OUT, tex_override or p["tex"], samples, tags=p["tags"])
        info.update({"tags": p["tags"], "desc": p["desc"], "kind": p["kind"]})
        bake.update_manifest(MANIFEST, n, info)
        print("BUILT %-22s %6d tris  %4d px  %5.1fs" % (n, info["tris"], info["tex"], time.time() - t0))
    except Exception:
        traceback.print_exc()
        print("FAILED", n)
        failed.append(n)
print("DONE %d built, %d failed %s" % (len(names) - len(failed), len(failed), " ".join(failed)))
