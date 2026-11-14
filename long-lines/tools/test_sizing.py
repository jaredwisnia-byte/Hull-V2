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


def test_identify_from_sheet_names():
    assert sizing.identify(["003_typewriter"])["category"] == "typewriter"
    assert sizing.identify(["002_cassette_recorder"])["category"] == "cassette_recorder"
    assert sizing.identify(["TYPE: CASSETTE RECORDER"])["category"] == "cassette_recorder"
    assert sizing.identify(["wall_telephone_v2"])["category"] == "wall_telephone"   # longest match wins
    assert sizing.identify(["005_hairdryer"])["category"] == "hair_dryer"           # alias
    assert sizing.identify(["MADE IN CANADA"]) is None                             # 'can' is a whole word only
    assert sizing.identify(["mystery_gadget"]) is None


def test_fit_scale_lands_inside_envelope():
    # The typewriter sheet's front (W x H) and implied depth in pixels.
    fit = sizing.fit_scale("typewriter", 600, 300, 587)
    s = fit["mm_per_px"] / 1000
    assert not fit["conflict"]
    assert sizing.envelope("typewriter", 600 * s, 587 * s, 300 * s) == []
    # A drawing far too flat for a stand mixer cannot fit: flag it, still return a scale.
    bad = sizing.fit_scale("stand_mixer", 1000, 50, 100)
    assert bad["conflict"] and bad["mm_per_px"] > 0


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
