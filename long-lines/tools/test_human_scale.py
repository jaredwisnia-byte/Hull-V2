"""Tests for human scale (propkit/human_scale.py) and the handbook's contacts. Plain python3.

    python3 tools/test_human_scale.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from propkit import handbook as HB, human_scale as HS  # noqa: E402

fails = []


def check(cond, msg):
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


# the body table: every range ordered, every contact names a real measure
for k, (lo, mid, hi) in HS.data()["measures"].items():
    check(lo < mid < hi, "%s range ordered" % k)
for name, e in HB.data()["objects"].items():
    for c in e.get("contacts", []):
        check(c["human"] in HS.data()["measures"], "%s: contact %s uses a known measure" % (name, c["part"]))
        check(c["factor"][0] < c["factor"][1], "%s: contact %s factor range ordered" % (name, c["part"]))
    # no product sizes in the handbook: sizes come from the drawing and the body
    for pn, p in e.get("parts", {}).items():
        check(not any(f.endswith("_mm") for f in p), "%s.%s holds no looked-up sizes" % (name, pn))

phone = {c["part"]: c for c in HB.contacts(HB.entry("wall_telephone_rotary"))}

# a drawing in proportion: handset 1.3 units tall, cap 0.36 units -> both agree, scale near the middle
a = [HS.anchor(phone["handset"], 1.3), HS.anchor(phone["cap"], 0.36)]
k, rep = HS.solve(a)
check(rep["agreeing"] == 2, "in-proportion drawing: both contacts agree")
check(0.15 < k * 1.3 < 0.25, "handset comes out 150-250 mm (%.0f)" % (k * 1300))

# the same drawing with finger holes drawn half size: the holes are outvoted and reported
a.append(HS.anchor(phone["dial_wheel"], 0.0085 / k * 0.5 * 1.0))
k2, rep2 = HS.solve(a)
holes = rep2["contacts"][2]
check(rep2["agreeing"] == 2 and not holes["agrees"], "half-size finger holes are outvoted")
check(abs(k2 - k) < 1e-9, "outvoted contact does not move the scale")
check(holes.get("drawing_off_by", 0) > 1.5, "report says the holes are drawn too small (x%.2f)" % holes.get("drawing_off_by", 0))

# scale does not depend on drawing units: the same drawing in pixels gives the same metres
a_px = [HS.anchor(phone["handset"], 1.3 * 227), HS.anchor(phone["cap"], 0.36 * 227)]
k3, _ = HS.solve(a_px)
check(abs(k3 * 227 - k) < 1e-9, "drawing units cancel out")

# a single contact still sizes the drawing (its nominal)
k4, rep4 = HS.solve([HS.anchor(phone["handset"], 1.0)])
check(abs(k4 - HS.size_range(phone["handset"])[1]) < 1e-9, "one contact: its typical size")

# a seat 0.45 units high is a person's knee height at scale ~1
sofa = {c["measure"]: c for c in HB.contacts(HB.entry("sofa"))}
k5, _ = HS.solve([HS.anchor(sofa["top_height"], 0.46), HS.anchor(sofa["depth"], 0.53)])
check(0.85 < k5 < 1.15, "a real-sized sofa needs no rescale (x%.2f)" % k5)

print("\n%d failed" % len(fails) if fails else "\nall passed")
sys.exit(1 if fails else 0)
