"""What real parts are like: the logic a modeller applies when a flat painting
shows a knob, a dial or a button. The hull builder detects these features in the
painted views and turns them into geometry sized by these rules.

Sizes are from real 1960s-70s consumer goods (metres). protrude = how far the
part stands proud of the surface it sits on, as a fraction of its diameter.
"""

RULES = {
    # Channel / volume knobs on TVs, radios, stoves: 2-4 cm across, stand out
    # 15-25 mm, ridged so fingers can grip them. A painted circle over ~45 mm is
    # usually a knob with its numbered dial ring around it, so depth is capped.
    # Painted stove/appliance knobs are often drawn with their dial ring (up to ~90 mm);
    # the knob itself is never wider than max_real (the cylinder is clamped to it).
    "knob": {"diameter": (0.015, 0.09), "protrude": 0.6, "min_depth": 0.008, "max_depth": 0.025,
             "flutes": 18, "bevel": 0.25, "max_real": 0.055},
    # Push buttons: small, shallow.
    "button": {"diameter": (0.006, 0.015), "protrude": 0.35, "min_depth": 0.003, "max_depth": 0.008,
               "flutes": 0, "bevel": 0.3, "max_real": 0.015},
}


def classify_circle(diameter_m):
    """Which part a round painted feature most likely is, from its real size."""
    for name in ("button", "knob"):
        lo, hi = RULES[name]["diameter"]
        if lo <= diameter_m <= hi:
            return name
    return None


def depth_for(part, diameter_m):
    r = RULES[part]
    return max(r["min_depth"], min(r["max_depth"], diameter_m * r["protrude"]))
