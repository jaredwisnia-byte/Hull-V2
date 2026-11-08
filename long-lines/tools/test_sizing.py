"""Tests for the sizing manual. Plain Python: python3 tools/test_sizing.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from propkit import sizing  # noqa: E402

BOX = {"span": 760, "height": 1650}


def box(x0, x1, z0, z1, **kw):
    b = dict(BOX, x0=x0, x1=x1, z0=z0, z1=z1)
    b.update(kw)
    return b


def test_formulas():
    assert sizing.mm("finger + clearance") == 30
    assert sizing.mm("max(finger, 3) * 2") == 40
    assert sizing.mm(7) == 7
    for bad in ("__import__('os')", "finger ** 2", "nonsense + 1"):
        try:
            sizing.mm(bad)
            raise AssertionError("accepted " + bad)
        except (ValueError, KeyError):
            pass


def test_catalogue_is_consistent():
    cat = sizing.catalogue()
    for side in ("out", "in"):
        for k, e in cat[side].items():
            lo, hi = e["depth_mm"]
            assert lo <= e["default"] <= hi, k
            assert e["why"], k
    assert cat["out"]["handle"]["default"] == 45      # finger + clearance + bar
    assert cat["in"]["dispenser"]["depth_mm"][0] == 95
    assert cat["in"]["seam"]["width_min_mm"] == 4


def test_placement():
    # a real foot: on the floor at a corner
    assert sizing.place("out", "foot", box(10, 80, 0, 40)) == ("foot", [])
    # a full-width band on the floor is the kick plate
    assert sizing.place("out", "foot", box(0, 760, 0, 130))[0] == "kick_plate"
    # a sliver above the floor is trim
    assert sizing.place("out", "foot", box(200, 300, 45, 50))[0] == "trim"
    # a handle shorter than a palm is trim; a long one stays
    assert sizing.place("out", "handle", box(300, 370, 80, 83))[0] == "trim"
    assert sizing.place("out", "handle", box(50, 110, 640, 1090))[0] == "handle"
    # appliance seams in the toe zone are the kick grille; furniture seams are left alone
    assert sizing.place("in", "seam", box(30, 700, 30, 45), "fridge")[0] == "vent"
    assert sizing.place("in", "seam", box(30, 700, 30, 45), "cabinet")[0] == "seam"
    assert sizing.place("in", "seam", box(30, 700, 1119, 1134), "fridge")[0] == "seam"
    # a dispenser on the side, or too low for a glass, is a recess
    assert sizing.place("in", "dispenser", box(300, 500, 1000, 1250), "fridge", "front")[0] == "dispenser"
    assert sizing.place("in", "dispenser", box(300, 500, 1000, 1250), "fridge", "right")[0] == "recess"
    assert sizing.place("in", "dispenser", box(300, 500, 1000, 1080), "fridge", "front")[0] == "recess"
    assert sizing.max_per_view("out", "foot") == 2


def test_envelopes():
    assert sizing.envelope("fridge", 0.775, 0.75, 1.65) == []
    assert len(sizing.envelope("fridge", 0.775, 0.75, 16.5)) == 1     # cm typed as dm
    assert sizing.envelope("dishwasher", 0.6, 0.6, 0.95)               # taller than the counter
    assert sizing.envelope("unknown_category", 9, 9, 9) == []


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
