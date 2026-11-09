"""The assembly line: work orders in, finished props and their final renders out, every station timed.

    python3 tools/line.py NAME [NAME ...]         run these orders down the line
    python3 tools/line.py --drawn                 every order built from a drawing (hull and hull_parts lines;
                                                  bench_ orders belong to the benchmark tools)

Stations, in order, for each order (each runs in its own Blender worker; a failed station stops that order
and the line moves on to the next):
  1 intake   if the order names its source sheet ("sheet", "sheet_spec"): the views are cut from the sheet
             (tools/sheet_blobs.py) and any removable guide lines taken out (propkit/guides.py, when the
             order says "guides"); otherwise the views on file are checked
  2 build    geometry, paint, bake, export and the quality gate (tools/factory.py build): ships it to the
             prop library, or flags it for a person
  3 render   the final renders (tools/render_turnaround.py) -> docs/renders/NAME.png
  4 report   factory KPIs (factory/REPORT.md), the line's own summary (docs/renders/LINE.md) and a
             contact sheet of everything that came off the line (docs/renders/line.png)
Python's string hashing is pinned (PYTHONHASHSEED=0) so the same orders give the same props.
"""
import glob
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ORDERS = os.path.join(ROOT, "factory", "orders")
SRC = os.path.join(ROOT, "assets", "source_textures")
OUT = os.path.join(ROOT, "docs", "renders")
ENV = dict(os.environ, PYTHONHASHSEED=os.environ.get("PYTHONHASHSEED", "0"))
DRAWN = ("hull", "hull_parts")


def blender(script, *args, timeout=1800):
    p = subprocess.run(["blender", "-b", "--factory-startup", "--python-exit-code", "1", "-P",
                        os.path.join(HERE, script), "--", *args], cwd=ROOT, env=ENV, text=True,
                       capture_output=True, timeout=timeout)
    return p.returncode, p.stdout + p.stderr


def order_of(name):
    return json.load(open(os.path.join(ORDERS, name + ".json")))


def intake(o):
    if o.get("sheet") and o.get("sheet_spec"):
        rc, log = blender("sheet_blobs.py", "crop", os.path.join(SRC, o["sheet"]), os.path.join(ROOT, o["sheet_spec"]),
                          o["views_folder"].split("/")[0])
        if rc:
            return False, "cutting views failed: " + log[-400:]
        cut = log.count("CROP ")
        note = "%d views cut from %s" % (cut, o["sheet"])
        if o.get("hull", {}).get("guides"):
            rc, log = blender(os.path.join("propkit", "guides.py"), "clean", os.path.join(SRC, o["views_folder"]))
            if rc:
                return False, "removing guides failed: " + log[-400:]
            note += "; guide lines read and painted out"
        return True, note
    folder = os.path.join(SRC, o["views_folder"])
    views = glob.glob(os.path.join(folder, "v_*.png")) + glob.glob(os.path.join(folder, "*", "v_*.png"))
    return (bool(views), "%d views on file" % len(views) if views else "no views in " + folder)


def run(names):
    os.makedirs(OUT, exist_ok=True)
    rows = []
    for name in names:
        o = order_of(name)
        row = {"name": name, "line": o.get("line"), "stations": {}}
        print("== %s (%s)" % (name, o.get("line")), flush=True)
        t = time.time()
        ok, note = intake(o)
        row["stations"]["intake"] = {"s": round(time.time() - t, 1), "ok": ok, "note": note}
        print("   intake  %5.1fs  %s" % (time.time() - t, note), flush=True)
        if ok:
            t = time.time()
            rc, log = blender("factory.py", "build", name, timeout=3600)
            o = order_of(name)
            ok = rc == 0 and o.get("status") == "shipped"
            led = [json.loads(l) for l in open(os.path.join(ROOT, "factory", "ledger.jsonl")) if '"%s"' % name in l]
            last = next((r for r in reversed(led) if r.get("op") == "build" and r.get("name") == name), {})
            note = ("shipped" if ok else "flagged: %s" % (last.get("fails") or log[-300:]))
            row["stations"]["build"] = {"s": round(time.time() - t, 1), "ok": ok, "note": note,
                                        "stages": last.get("stage_seconds"), "tris": last.get("metrics", {}).get("tris")}
            print("   build   %5.1fs  %s %s" % (time.time() - t, note, last.get("stage_seconds") or ""), flush=True)
        if ok:
            t = time.time()
            rc, log = blender("render_turnaround.py", name, OUT)
            ok = rc == 0
            row["stations"]["render"] = {"s": round(time.time() - t, 1), "ok": ok,
                                         "note": "docs/renders/%s.png" % name if ok else log[-300:]}
            print("   render  %5.1fs  %s" % (time.time() - t, row["stations"]["render"]["note"]), flush=True)
        row["ok"] = ok
        row["total_s"] = round(sum(s["s"] for s in row["stations"].values()), 1)
        rows.append(row)
    # station 4: report
    blender("factory.py", "report")
    lines = ["# Assembly line run", "", "| Order | Line | Intake | Build | Render | Total | Result |", "|---|---|---|---|---|---|---|"]
    for r in rows:
        st = r["stations"]
        cell = lambda k: ("%.0f s" % st[k]["s"]) if k in st else "-"
        lines.append("| %s | %s | %s | %s | %s | %.0f s | %s |" % (r["name"], r["line"], cell("intake"), cell("build"),
                                                                   cell("render"), r["total_s"], "shipped" if r["ok"] else "stopped"))
    lines += ["", "Stations: intake (views cut from the sheet, guide lines removed) -> build (geometry, paint, bake, "
              "export, quality gate) -> render (docs/renders/NAME.png). Run with `python3 tools/line.py --drawn`."]
    for r in rows:
        lines += ["", "## %s" % r["name"]] + ["- %s: %s" % (k, v["note"]) for k, v in r["stations"].items()]
    open(os.path.join(OUT, "LINE.md"), "w").write("\n".join(lines) + "\n")
    json.dump(rows, open(os.path.join(OUT, "line_run.json"), "w"), indent=1)
    contact([r["name"] for r in rows if r["ok"]])
    print("\n".join(lines[:4 + len(rows)]))
    return rows


def contact(names):
    """One picture of everything that came off the line: each prop's three-quarter and front views."""
    from PIL import Image, ImageDraw
    tiles = []
    for n in names:
        p = os.path.join(OUT, n + ".png")
        if not os.path.exists(p):
            continue
        im = Image.open(p).convert("RGB")
        T = 360
        tq = im.crop((T, 70 + T, 2 * T, 70 + 2 * T))          # three-quarter (second row, second tile)
        fr = im.crop((0, 70, T, 70 + T))
        t = Image.new("RGB", (2 * T, T + 30), (246, 244, 239))
        t.paste(fr, (0, 30))
        t.paste(tq, (T, 30))
        ImageDraw.Draw(t).text((8, 6), n, fill=(30, 30, 30))
        tiles.append(t)
    if not tiles:
        return
    cols = 2
    w, h = tiles[0].size
    sheet = Image.new("RGB", (cols * w, ((len(tiles) + cols - 1) // cols) * h), (246, 244, 239))
    for i, t in enumerate(tiles):
        sheet.paste(t, ((i % cols) * w, (i // cols) * h))
    sheet.save(os.path.join(OUT, "line.png"))


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--drawn" in args:
        names = sorted(os.path.basename(p)[:-5] for p in glob.glob(os.path.join(ORDERS, "*.json"))
                       if not p.endswith(".sheet.json") and json.load(open(p)).get("line") in DRAWN
                       and not os.path.basename(p).startswith(("exp_", "bench_")))
    else:
        names = [a for a in args if not a.startswith("--")]
    rows = run(names)
    sys.exit(0 if all(r["ok"] for r in rows) else 1)
