"""Asset-level geometry regression: rebuild reference assets from their own orders under exp_ names,
measure them (tools/diag/metrics.py) and compare with factory/geometry_baseline.json.

    python3 tools/diag/regress_assets.py [--update-baseline] [--only car,coffee,sofa]

Each case must keep its silhouette (IoU no more than 0.005 below the baseline), stay free of folds
(per 1000 faces no more than the baseline + 0.5) and not get ridgier (ridge_deg no more than the
baseline + 0.3). The library, ledger and REPORT are restored and the exp_ outputs deleted afterwards.
About 6 minutes. The fast synthetic suite is tools/test_hull_geometry.py.
"""
import json
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
CASES = {   # name -> (order file, reference views for the silhouette)
    "car": ("factory/orders/car_sedan_tan.json", "assets/source_textures/car_sedan_tan"),
    "coffee": ("factory/orders/coffee_maker_drip.json", "assets/source_textures/coffee_maker_drip/assembly"),
    "sofa": ("factory/fixtures/fixture_sofa_parts.json", "assets/source_textures/fixture_sofa_parts/assembly"),
    "wallphone": ("factory/fixtures/fixture_wallphone_parts.json", "assets/source_textures/fixture_wallphone_parts/assembly"),
}
BASE = os.path.join(ROOT, "factory", "geometry_baseline.json")
RESTORE = ["assets/props/library.json", "factory/REPORT.md", "factory/ledger.jsonl"]


def run(cmd):
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)


def main():
    only = sys.argv[sys.argv.index("--only") + 1].split(",") if "--only" in sys.argv else list(CASES)
    update = "--update-baseline" in sys.argv
    base = json.load(open(BASE)) if os.path.exists(BASE) else {}
    saved = {p: open(os.path.join(ROOT, p), "rb").read() for p in RESTORE}
    results, fails = {}, []
    try:
        for case in only:
            order_path, views = CASES[case]
            name = "exp_regress_" + case
            o = json.load(open(os.path.join(ROOT, order_path)))
            for k in ("measured", "attempts", "qa"):
                o.pop(k, None)
            o.update(name=name, status="pending")
            json.dump(o, open(os.path.join(ROOT, "factory", "orders", name + ".json"), "w"), indent=1)
            t = time.time()
            run(["blender", "-b", "--factory-startup", "-P", "tools/factory.py", "--", "build", name])
            secs = round(time.time() - t, 1)
            status = json.load(open(os.path.join(ROOT, "factory", "orders", name + ".json")))["status"]
            out = os.path.join("/tmp", name + "_metrics.json")
            run(["blender", "-b", "--factory-startup", "-P", "tools/diag/metrics.py", "--",
                 "assets/props/%s/%s.glb" % (name, name), views, "--json", out])
            m = json.load(open(out))
            m.update(seconds=secs, status=status)
            results[case] = m
            b = base.get(case)
            msg = []
            if status != "shipped":
                msg.append("build not shipped (%s)" % status)
            if b:
                if m["iou_mean"] < b["iou_mean"] - 0.005:
                    msg.append("silhouette IoU %.4f < baseline %.4f - 0.005" % (m["iou_mean"], b["iou_mean"]))
                if m["folds_per_1k"] > b["folds_per_1k"] + 0.5:
                    msg.append("folds/1k %.2f > baseline %.2f + 0.5" % (m["folds_per_1k"], b["folds_per_1k"]))
                if m["ridge_deg"] > b["ridge_deg"] + 0.3:
                    msg.append("ridge %.2f > baseline %.2f + 0.3" % (m["ridge_deg"], b["ridge_deg"]))
            print("%-7s %s  iou %.4f ridge %.2f folds/1k %.2f  %ss  %s" % (case, "FAIL" if msg else "ok  ", m["iou_mean"],
                  m["ridge_deg"], m["folds_per_1k"], secs, "; ".join(msg)))
            if msg:
                fails.append(case)
    finally:
        for p, data in saved.items():
            open(os.path.join(ROOT, p), "wb").write(data)
        for case in only:
            name = "exp_regress_" + case
            for p in ("assets/props/" + name, "factory/orders/%s.json" % name):
                full = os.path.join(ROOT, p)
                if os.path.isdir(full):
                    shutil.rmtree(full)
                elif os.path.exists(full):
                    os.remove(full)
    if update:
        base.update({k: {f: v[f] for f in ("iou_mean", "ridge_deg", "folds_per_1k", "tris")} for k, v in results.items()})
        json.dump(base, open(BASE, "w"), indent=1)
        print("baseline updated")
    print("ASSET REGRESSION: %d failed" % len(fails))
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
