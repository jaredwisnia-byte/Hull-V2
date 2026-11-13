"""The sizing manual (factory/sizing_manual.json, explained in factory/SIZING.md), as code.

- catalogue(): every part kind's depth range in mm, worked out from the manual's facts.
  Same shape as the old parts_catalog.json, plus the formula behind each number.
- place(): does a part of this kind make sense where it was found? If not, what is it?
- envelope(): is an object of this category a believable size?

Pure Python: usable from Blender, the factory and plain tests.
    python3 tools/propkit/sizing.py --catalogue   rewrite factory/parts_catalog.json
    python3 tools/propkit/sizing.py --facts       print every derived number
"""
import ast
import json
import operator
import os

HERE = os.path.dirname(os.path.abspath(__file__))
MANUAL_PATH = os.path.join(HERE, "..", "..", "factory", "sizing_manual.json")
_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}
_FUNCS = {"min": min, "max": max}
_cache = {}


def manual():
    if "m" not in _cache:
        with open(MANUAL_PATH, encoding="utf-8") as stream:
            _cache["m"] = json.load(stream)
    return _cache["m"]


def facts():
    return {k: v["mm"] for k, v in manual()["facts"].items()}


def mm(expr, env=None):
    """A number, or a formula over the facts ("finger + clearance"), in millimetres."""
    if expr is None or isinstance(expr, (int, float)):
        return expr
    env = env or facts()

    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return n.value
        if isinstance(n, ast.Name):
            if n.id not in env:
                raise KeyError("sizing manual: unknown fact '%s' in '%s'" % (n.id, expr))
            return env[n.id]
        if isinstance(n, ast.BinOp) and type(n.op) in _OPS:
            return _OPS[type(n.op)](ev(n.left), ev(n.right))
        if isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.USub):
            return -ev(n.operand)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in _FUNCS:
            return _FUNCS[n.func.id](*[ev(a) for a in n.args])
        raise ValueError("sizing manual: can't read '%s'" % expr)
    return float(ev(ast.parse(str(expr), mode="eval")))


def catalogue():
    """{"out"|"in": {kind: {"depth_mm": [lo, hi], "default", "why", "formula", ...}}}"""
    if "cat" in _cache:
        return _cache["cat"]
    env = facts()
    cat = {}
    for side, kinds in manual()["parts"].items():
        cat[side] = {}
        for kind, r in kinds.items():
            d = r["depth"]
            lo, df, hi = mm(d["min"], env), mm(d["default"], env), mm(d["max"], env)
            if not lo <= df <= hi:
                raise ValueError("sizing manual: %s %s default %.0f outside %.0f-%.0f" % (side, kind, df, lo, hi))
            e = {"depth_mm": [round(lo, 1), round(hi, 1)], "default": round(df, 1), "why": r["why"],
                 "formula": {k: d[k] for k in ("min", "default", "max") if isinstance(d[k], str)}}
            if "width_min" in r:
                e["width_min_mm"] = mm(r["width_min"], env)
            cat[side][kind] = e
    _cache["cat"] = cat
    return cat


def _group(object_type):
    return "appliance" if (object_type or "") in manual()["appliance_types"] else None


def _rule(side, kind, object_type):
    r = dict(manual()["parts"][side].get(kind, {}).get("where", {}))
    special = r.pop("for", {})
    for key in (object_type, _group(object_type)):
        if key and key in special:
            r.update(special[key])
    return r


def check(side, kind, box, object_type=None, view=None):
    """Why this part can't be a `kind` where it is, or None if it can.
    box: {"x0","x1","z0","z1"} mm within the view (z up from the floor), "span" and "height" mm."""
    r = _rule(side, kind, object_type)
    if not r:
        return None
    env = facts()
    w, h = box["x1"] - box["x0"], box["z1"] - box["z0"]
    if "views" in r and view and view not in r["views"]:
        return "not on the %s" % "/".join(r["views"])
    if r.get("touches_floor") and box["z0"] > max(15.0, 0.02 * box["height"]):
        return "does not reach the floor"
    if "near_side" in r:
        c = (box["x0"] + box["x1"]) / 2 / box["span"]
        if min(c, 1 - c) > r["near_side"]:
            return "not near a side"
    if "max_width_mm" in r and w > mm(r["max_width_mm"], env):
        return "wider than %.0f mm" % mm(r["max_width_mm"], env)
    if "min_width_frac" in r and w < r["min_width_frac"] * box["span"]:
        return "narrower than %d%% of the object" % round(100 * r["min_width_frac"])
    if "min_length_mm" in r and max(w, h) < mm(r["min_length_mm"], env):
        return "shorter than %.0f mm" % mm(r["min_length_mm"], env)
    if "min_height_mm" in r and h < mm(r["min_height_mm"], env):
        return "lower than %.0f mm" % mm(r["min_height_mm"], env)
    if "height_mm" in r:
        lo, hi = r["height_mm"]
        lo, hi = mm(lo, env), mm(hi, env)
        if (lo is not None and box["z0"] < lo - 1) or (hi is not None and box["z1"] > hi + 1):
            return "outside %s-%s mm above the floor" % ("%.0f" % lo if lo is not None else "",
                                                          "%.0f" % hi if hi is not None else "")
    return None


def place(side, kind, box, object_type=None, view=None):
    """The kind a part should be, following the manual's 'else' chain until one fits.
    Returns (kind, [reasons]); reasons is empty when the first guess was right."""
    reasons, seen = [], set()
    while kind not in seen:
        seen.add(kind)
        why = check(side, kind, box, object_type, view)
        if why is None:
            return kind, reasons
        nxt = _rule(side, kind, object_type).get("else")
        reasons.append("%s: %s" % (kind, why))
        if not nxt:
            return kind, reasons
        kind = nxt
    return kind, reasons


def max_per_view(side, kind, object_type=None):
    return _rule(side, kind, object_type).get("max_per_view")


def fallback(side, kind, object_type=None):
    return _rule(side, kind, object_type).get("else")


def envelope(category, width_m=None, depth_m=None, height_m=None):
    """Warnings (list of str) when an object is outside its category's believable size."""
    env = manual()["envelopes"].get(category)
    if not env:
        return []
    out = []
    for dim, val in (("width", width_m), ("depth", depth_m), ("height", height_m)):
        if val is None or dim not in env:
            continue
        lo, hi = (mm(x) for x in env[dim])
        v = val * 1000
        if not lo <= v <= hi:
            out.append("%s %.0f mm is outside %.0f-%.0f mm for a %s" % (dim, v, lo, hi, category))
    return out


def write_catalogue(path=None):
    path = path or os.path.join(HERE, "..", "..", "factory", "parts_catalog.json")
    cat = catalogue()
    doc = {"_note": "GENERATED from factory/sizing_manual.json by tools/propkit/sizing.py --catalogue. "
                    "Edit the manual, not this file. Millimetres; 'out' = stands proud, 'in' = recess depth."}
    doc.update(cat)
    with open(path, "w") as f:
        json.dump(doc, f, indent=1)
        f.write("\n")
    return path


if __name__ == "__main__":
    import sys
    if "--catalogue" in sys.argv:
        print("wrote", write_catalogue())
    if "--facts" in sys.argv or len(sys.argv) == 1:
        for side, kinds in catalogue().items():
            for k, e in kinds.items():
                print("%-4s %-13s %6.1f-%6.1f  default %6.1f  %s" % (side, k, e["depth_mm"][0], e["depth_mm"][1],
                                                                       e["default"], e["formula"] or ""))
