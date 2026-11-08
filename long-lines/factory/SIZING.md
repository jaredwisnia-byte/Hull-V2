# Sizing manual

How big things should be, and why. The data is `factory/sizing_manual.json`; `tools/propkit/sizing.py`
reads it. This page explains the logic so a person (or a new session) can extend it.

The idea: a modeller doesn't guess that a fridge handle stands out 45 mm. They know a hand has to
close round it, so it needs room for a finger behind the bar, a little clearance, and the bar itself.
The manual writes that reasoning down once, as formulas over a few facts about bodies and everyday
objects. Change a fact and every size that depends on it follows.

## 1. Facts

Measured things everything else is built from (all in mm):

| Group | Facts |
| --- | --- |
| Hands | finger 20, fingernail 4, hand_width 90, pinch 8, clearance 10, handle_bar 15 |
| Heights above the floor | toe_kick_height 100, seat_height 450, knee_height 500, counter_height 910, waist_height 1000, chest_height 1300, eye_height 1550, reach_height 1900 |
| Objects | glass_diameter 85, glass_height 120, spout 20, door_thickness 45, screw_head 8 |
| Buildings | brick_width 92, masonry_wall 400, rain_drip 30 |

Add a fact when a new rule needs one. Give it a one-line "why" saying what was measured.

## 2. Part sizes

Each kind of part has a depth range (`min`, `default`, `max`). Each can be a plain number or a
formula using facts, `+ - * /`, `min()` and `max()`. Some examples:

| Part | Depth | Reasoning |
| --- | --- | --- |
| handle (out) | finger to finger + clearance + handle_bar + 15 (20-60 mm, default 45) | a hand closes round it |
| dispenser (in) | glass_diameter + clearance to glass_diameter + 55 (95-140, default 105) | a glass fits under the spout |
| window (in) | brick_width to masonry_wall × 3/4 (92-300, default 200) | glass sits back about half the wall |
| sill (out) | rain_drip + 10 to rain_drip + 90 (40-120, default 70) | the nose throws water clear of the wall |
| seam (in) | 3-8, at least a fingernail wide | the gap round a door, not a slot |

Not every number has a formula. Hinges, keys, vents and trim are period measurements with a "why".
That's fine: a formula is worth writing only when a fact really drives the size.

The factory uses these to clamp every part (side view measurement, else depth map, else default).
`parts_catalog.json` is now generated from the manual (`python3 tools/propkit/sizing.py --catalogue`).

## 3. Where a part can be

A part's first guess comes from its colour and shape in the part map. The `where` rules then check
it is somewhere that kind of part can actually be. If not, `else` names what it is instead, and the
check repeats down the chain.

| Rule | Meaning |
| --- | --- |
| `touches_floor` | bottom within 15 mm (or 2% of height) of the floor |
| `near_side: f` | centre within fraction f of the left or right edge |
| `max_width_mm`, `min_width_frac` | how wide it may be, in mm or as a share of the object |
| `min_length_mm`, `min_height_mm` | its long side, or its height, must be at least this |
| `height_mm: [lo, hi]` | must lie between these heights above the floor (null = open) |
| `views: [...]` | which views it can appear in |
| `max_per_view: n` | keep the n biggest; the rest go to `else` |
| `for: {type: {...}}` | extra rules for one object type, or `appliance` for all of `appliance_types` |

Current chains:
- foot: on the floor, near a corner, no wider than 1.5 hands, two per view → else kick_plate → else trim
- handle: at least a palm long → else trim
- hinge: on an edge → else trim
- knob: no wider than a palm → else trim
- dispenser: front only, tall enough for a glass, between waist − 200 mm and eye height → else recess
- seam on an appliance: above the toe kick → else vent (the kick grille)

The build report lists every renamed part with the reason (`was`, `because`), and a `renamed` count.

## 4. Object envelopes

`envelopes` gives a believable width, depth and height per category, for 1960s-70s New York. Bounds
can be formulas too (a dishwasher is no taller than the counter). Intake adds a "check size" note to
the order when the manifest's dimensions fall outside, and the build reports `size_warnings`.

## Adding things

- **New kind of object:** add its envelope, and if it's an appliance add it to `appliance_types`.
  Most of the time that is all: the part rules already apply.
- **New kind of part:** add it under `out` or `in` with a depth and a why; add a `where` if it can
  only be in certain places. Teach `_kind` in `sheetset.py` to guess it if the shape alone tells.
- **A size looks wrong:** find which fact or formula produced it (the report gives the rule's why)
  and fix it there, not in code.

Still outside the manual: knobs and buttons found as painted circles on the hull and atlas lines use
`tools/propkit/part_rules.py` (depth as a share of diameter).
