"""FACTORY_V1 command: validate -> build -> export -> reimport QA -> renders -> qa.json.

    python3 long-lines/tools/factory_v1.py path/to/asset.json [--out DIR] [--blender PATH] [--no-render]

Runs with the system Python (needs Pillow + jsonschema for the preflight) and calls Blender
twice: once to build and export the GLB, once in a fresh process to inspect only the
exported file. Outputs go to long-lines/factory/out/<asset_id>/ (git-ignored), never into
the asset library. Exit code 0 only when every QA check passes.
"""
import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "factory", "out")

spec = importlib.util.spec_from_file_location("validate_package", os.path.join(HERE, "validate_package.py"))
validate_package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validate_package)

DIM_TOL = (0.01, 0.003)   # 1% or 3 mm, whichever is larger


def blender(binary, *args):
    cmd = [binary, "-b", "--factory-startup", "--python-exit-code", "1",
           "-P", os.path.join(HERE, "factory_v1_blender.py"), "--"] + list(args)
    t = time.time()
    p = subprocess.run(cmd, capture_output=True, text=True)
    return p.returncode, p.stdout[-4000:] + p.stderr[-4000:], round(time.time() - t, 1)


def dims_check(declared, measured):
    errs = [abs(m - d) for m, d in zip(measured, declared)]
    ok = all(e <= max(DIM_TOL[0] * d, DIM_TOL[1]) for e, d in zip(errs, declared))
    return ok, [round(e * 1000, 1) for e in errs]


def contact_sheet(previews, path, title):
    from PIL import Image, ImageDraw, ImageFont
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 22)
    except OSError:
        font = ImageFont.load_default()
    names = ["front", "side", "rear", "top", "threequarter"]
    tiles = [Image.open(previews[n]).convert("RGB") for n in names if n in previews]
    if not tiles:
        return None
    w, h = tiles[0].size
    sheet = Image.new("RGB", (w * 3, h * 2 + 50), (20, 21, 24))
    d = ImageDraw.Draw(sheet)
    d.text((14, 12), title, font=font, fill=(240, 222, 180))
    for i, (n, t) in enumerate(zip(names, tiles)):
        x, y = (i % 3) * w, 50 + (i // 3) * h
        sheet.paste(t, (x, y))
        d.text((x + 10, y + 8), n, font=font, fill=(235, 235, 235))
    sheet.save(path)
    return path


def run(asset_path, out=None, binary="blender", render=True):
    asset_path = os.path.realpath(asset_path)
    asset = json.load(open(asset_path, encoding="utf-8"))
    out = os.path.realpath(out or os.path.join(OUT, asset.get("asset_id", "unknown")))
    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(out)
    qa = {"asset_id": asset.get("asset_id"), "package": asset_path, "output_dir": out, "pass": False,
          "stages": {}, "failures": []}
    fail = qa["failures"].append

    def finish():
        qa["pass"] = not qa["failures"]
        json.dump(qa, open(os.path.join(out, "qa.json"), "w"), indent=1)
        return qa

    # 1 preflight
    pre = validate_package.validate(asset_path)
    qa["stages"]["preflight"] = {"pass": pre["pass"], "errors": pre["errors"], "warnings": pre["warnings"]}
    if not pre["pass"]:
        for e in pre["errors"]:
            fail("[preflight] " + e)
        return finish()
    # 2 build + export
    code, log, secs = blender(binary, "build", asset_path, out)
    qa["stages"]["build"] = {"exit_code": code, "seconds": secs}
    if code != 0 or not os.path.exists(os.path.join(out, "build.json")):
        fail("[builder] Blender build failed: " + log[-1500:])
        return finish()
    core = json.load(open(os.path.join(out, "core.json")))
    record = json.load(open(os.path.join(out, "build.json")))
    qa["operations_used"] = core["operations_used"]
    qa["unsupported"] = core["unsupported"]
    qa["warnings"] = core["warnings"]
    qa["registration"] = core["registration"]
    for e in core["errors"]:
        fail("[manifest/builder] " + e)
    for u in core["unsupported"]:
        fail("[unsupported] %s %s: %s" % (u["what"], u["item"], u["why"]))
    qa["stages"]["export"] = {"glb": record["glb"], "bytes": record["glb_bytes"]}
    # 3 fresh-Blender inspection of the exported GLB
    args = ["verify", out] + ([] if render else ["--no-render"])
    code, log, secs = blender(binary, *args)
    qa["stages"]["reimport"] = {"exit_code": code, "seconds": secs}
    if code != 0 or not os.path.exists(os.path.join(out, "verify.json")):
        fail("[export] reimport/QA failed: " + log[-1500:])
        return finish()
    ver = json.load(open(os.path.join(out, "verify.json")))
    for e in ver["failures"]:
        fail("[export/geometry] " + e)
    parts = {}
    for pid, c in core["parts"].items():
        v = ver["parts"].get(pid, {})
        parts[pid] = {
            "construction": c["construction"], "semantic_class": c["semantic_class"], "built": c.get("built", False),
            "in_glb": v.get("present", False), "class_kept": v.get("class_kept"),
            "closed_required": c.get("closed_required"), "manifold_after_reimport": v.get("manifold"),
            "open_edges": v.get("open_edges"), "triangles": v.get("triangles"),
            "uv_samples_matched": v.get("uv_samples_matched"), "texel_density": v.get("texel_density"),
            "bbox_m": v.get("bbox_m"), "declared_dimensions_m": c.get("declared_dimensions_m"),
            "gap_to_parent_mm": v.get("gap_to_parent_mm")}
    qa["parts"] = parts
    qa["all_parts_built"] = all(p["built"] and p["in_glb"] for p in parts.values())
    qa["manifold_where_required"] = all(p["manifold_after_reimport"] for p in parts.values() if p["closed_required"])
    qa["uvs_survived_glb"] = all(v.get("uv_roundtrip_ok") for v in ver["parts"].values() if v.get("present"))
    qa["openings"] = ver["openings"]
    qa["triangles"] = ver["triangles"]
    # 4 dimensions: brief envelope vs the main body or the whole assembly
    d = asset["brief"]["dimensions_m"]
    declared = [d["width"], d["depth"], d["height"]]
    roots = [pid for pid, c in core["parts"].items() if not c.get("parent")]
    body = ver["parts"].get(roots[0], {}).get("bbox_m") if len(roots) == 1 else None
    ok_all, err_all = dims_check(declared, ver["overall_bbox_m"])
    ok_body, err_body = dims_check(declared, body) if body else (False, None)
    qa["dimensions"] = {"declared_m": declared, "overall_m": ver["overall_bbox_m"], "overall_err_mm": err_all,
                        "main_body_m": body, "main_body_err_mm": err_body,
                        "matches": "overall" if ok_all else "main_body" if ok_body else None}
    if not (ok_all or ok_body):
        fail("[manifest] built size %s / body %s does not match the brief %s" % (ver["overall_bbox_m"], body, declared))
    for pid, p in parts.items():
        dd = p.get("declared_dimensions_m")
        if dd and p.get("bbox_m"):
            over = [round((b - a) * 1000, 1) for a, b in zip(dd, p["bbox_m"])]
            p["size_minus_declared_mm"] = over
            if min(over) < -3:
                fail("[manifest/builder] part %s is smaller than declared by %s mm" % (pid, over))
            if max(over) > 3:
                qa["warnings"].append("part %s exceeds its declared base size by %s mm (painted relief on its face)" % (pid, over))
    # 5 previews
    if render:
        qa["previews"] = ver.get("previews", {})
        sheet = contact_sheet(qa["previews"], os.path.join(out, "%s_views.png" % qa["asset_id"]),
                              "%s  (FACTORY_V1 interpreter, reimported GLB)" % qa["asset_id"])
        qa["previews"]["sheet"] = sheet
        if not sheet:
            fail("[export] no previews rendered")
    return finish()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("package")
    ap.add_argument("--out")
    ap.add_argument("--blender", default=os.environ.get("BLENDER", "blender"))
    ap.add_argument("--no-render", action="store_true")
    a = ap.parse_args(argv)
    qa = run(a.package, a.out, a.blender, not a.no_render)
    print(json.dumps({k: qa.get(k) for k in ("asset_id", "pass", "failures", "triangles", "dimensions", "openings", "output_dir")}, indent=1))
    return 0 if qa["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
