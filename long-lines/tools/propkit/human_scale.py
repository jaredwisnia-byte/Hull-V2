"""Human scale: how big a drawn object is, without looking anything up.

The drawing gives every proportion but no size. One table of the adult human body
(factory/human_scale.json) gives size: each object type in the reference handbook lists its
contacts, the places it meets the body (a handset spans ear to mouth, a finger goes into a dial
hole, a seat is at knee height). Each contact measured in the drawing says what the drawing's scale
could be, as a range (people differ, and objects fit them loosely). Several contacts cross-check
each other: the scale is chosen inside the range of the largest group that agrees. A contact
outside it means the drawing is out of proportion there (an artist drew the holes too small), and
the report says so and by how much.

    anchors = [human_scale.anchor(contact, measured_in_drawing_units), ...]
    scale, report = human_scale.solve(anchors)        # metres per drawing unit
"""
import itertools
import json
import math
import os

PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                    "factory", "human_scale.json")
_DATA = None


def data():
    global _DATA
    if _DATA is None:
        _DATA = json.load(open(PATH))
    return _DATA


def human(name):
    """(5th, 50th, 95th percentile) of a body measure, in metres."""
    lo, mid, hi = data()["measures"][name]
    return lo / 1000.0, mid / 1000.0, hi / 1000.0


def size_range(spec):
    """{"human": measure, "factor": [lo, hi]} -> (lo, nominal, hi) in metres."""
    lo, mid, hi = human(spec["human"])
    f0, f1 = spec["factor"]
    return lo * f0, mid * math.sqrt(f0 * f1), hi * f1


def anchor(contact, measured):
    """One contact measured in the drawing (drawing units) -> the scales it allows."""
    lo, nom, hi = size_range(contact)
    return {"part": contact["part"], "measure": contact["measure"], "human": contact["human"],
            "measured": measured, "lo": lo / measured, "nominal": nom / measured, "hi": hi / measured,
            "why": contact.get("why", "")}


def solve(anchors):
    """The scale (metres per drawing unit) the largest agreeing group of anchors allows.

    Groups are compared by size, then by containing the first-listed (primary) anchor. Inside the
    group's common range the scale is the geometric mean of their nominal scales, clipped to it.
    Returns (scale, report)."""
    if not anchors:
        raise ValueError("no human-scale contacts measured")
    n = len(anchors)
    best = None
    for k in range(n, 0, -1):
        for grp in itertools.combinations(range(n), k):
            lo = max(anchors[i]["lo"] for i in grp)
            hi = min(anchors[i]["hi"] for i in grp)
            if lo <= hi:
                key = (k, 0 in grp)
                if best is None or key > best[0]:
                    best = (key, grp, lo, hi)
        if best:
            break
    _, grp, lo, hi = best
    nom = math.exp(sum(math.log(anchors[i]["nominal"]) for i in grp) / len(grp))
    scale = min(max(nom, lo), hi)
    rows = []
    for i, a in enumerate(anchors):
        size = a["measured"] * scale
        r = {"contact": "%s %s ~ %s" % (a["part"], a["measure"], a["human"]),
             "measured": round(a["measured"], 5),
             "size_mm": round(size * 1000, 1),
             "human_range_mm": [round(a["lo"] * a["measured"] * 1000, 1), round(a["hi"] * a["measured"] * 1000, 1)],
             "agrees": i in grp}
        if i not in grp:
            # how far the drawing is out of proportion here: the size it would need / the size it gets
            r["drawing_off_by"] = round(a["nominal"] / scale, 2)
        rows.append(r)
    spread = max(anchors[i]["nominal"] for i in grp) / min(anchors[i]["nominal"] for i in grp)
    return scale, {"scale_range": [lo, hi], "agreeing": len(grp), "of": n,
                   "nominal_spread": round(spread, 2), "contacts": rows}


def check(spec, size_m):
    """Is a size within what the body allows? -> (ok, (lo, hi) mm)."""
    lo, _, hi = size_range(spec)
    return lo <= size_m <= hi, (round(lo * 1000, 1), round(hi * 1000, 1))
