# Benchmark: sheet-first construction vs the legacy factory

November 9 2026. Run in the session's cloud container (Blender 4.0.2, Cycles CPU): no folder on
Jared's computer was shared, so "local" here means this container.

- **Version A (legacy):** the production lines on `claude/trusting-dirac-bxfmv6`: atlas (oven, armchair),
  sheetset (fridge), extrude (crown), hull (TV). Normal factory build: gate, one automatic correction, ledger.
- **Version B (sheet-first):** PR branch `chatgpt/sheetfirst-panels-v1` at `466beda`, run unmodified from its own
  git worktree (`intake_sheetfirst` + `build`).

Neither pipeline's modelling code was changed for this benchmark. The only changes were benchmark tools
(renderer, measurements) and one input-table entry (`categories.json: armchair_atlas`, a size for version A).

## The ten models

| | Shared reference | Real size W x D x H (m) |
| --- | --- | --- |
| Oven | Jared's appliance atlas 3 (white electric range) | 0.76 x 0.66 x 0.91 (+ backguard) |
| Refrigerator | fridge_1 sheet set from ChatGPT (painted, depth, part map, section) | 0.775 x 0.75 x 1.65 |
| Crown moulding | trim sheet 6: ornate crown strip + drawn profile | 1.2 x 0.165 x 0.28 |
| Television | Jared's painted TV sheet (five views) | 0.662 x 0.308 x 0.48 |
| Armchair | furniture sheet 2: armchair parts atlas | 0.80 x 0.85 x 0.85 |

Comparison sheets (reference | A | B, rows: front, side, rear, three-quarter, top, UV layout):
`compare_oven.png`, `compare_fridge.png`, `compare_crown.png`, `compare_tv.png`, `compare_armchair.png`.
Identical cameras placed from the agreed real box (a wrongly sized model shows it), identical lights and
samples; each model shaded with its own exported albedo, normal and ORM maps. GLBs: `glb/`. UV layouts: `uv/`.
Numbers: `measurements.csv`. Inputs: `inputs/<object>/` (A work order, B manifest + depth atlas).

## Measured (automated)

| Object | Ver | Gate | Build s | Tris | Max size err % | Outline IoU (front/side/top) | Profile IoU | Front texture corr. | Open edges | UV angle-distorted % | Authored input values |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Oven | A | pass | 19.8 | 5028 | 3.3 | n/a | | 0.937 | 0 | 0.0 | 9 |
| Oven | B | pass | 2.8 | 3808 | 0.3 | n/a | | 0.920 | 376 | 0.0 | 104 |
| Fridge | A | pass | 8.1 | 1792 | 1.8 | 0.988 / 0.979 / 0.958 | | 0.850 | 4 | 12.8 | 2 |
| Fridge | B | pass | 2.8 | 7584 | **9.3** | 0.988 / 0.962 / 0.962 | | **0.974** | 516 | 15.4 | 87 |
| Crown | A | pass | 12.5 | 76 | 0.0 | | **0.952** | 0.603 | 0 | 3.0 | 5 |
| Crown | B | **FAIL** (UV stretch 22%) | 0.7 | 7680 | 11.8 | | **0.0** | **0.880** | 304 | 19.2 | 19 |
| TV | A | pass | 30.4 | 24766 | 0.1 | 0.908 / 0.886 / 0.938 | | 0.518 | 0 | 49.8 | 1 |
| TV | B | pass | 3.6 | 13216 | 6.5 | 0.890 / 0.952 / 0.940 | | **0.952** | 636 | **100.0** | 87 |
| Armchair | A | pass | 20.5 | 1504 | 2.9 | n/a | | n/a | 0 | 0.0 | 7 |
| Armchair | B | pass | 3.3 | 3168 | 3.0 | n/a | | n/a | 424 | 0.0 | 155 |

How to read them:
- *Outline IoU*: the model's orthographic silhouette against the reference view's outline (only where an
  orthographic reference exists). *Profile IoU*: the crown's end-on outline against the drawn section.
  B's crown scores 0 because it is an open sheet: seen end-on it is an edge with no profile.
- *Front texture correlation*: the model's flat-lit front render against the reference front (grayscale,
  over the object). Higher = painted details land in the right place, sharper.
- *Open edges*: edges with only one face. 0 = closed solid. All B models are open surface patches (by design, v1).
- *UV angle-distorted %*: surface whose texture is sheared/squashed more than 2:1 in one direction.
  B's TV is 100% because every panel had to be declared "allow_stretch" (painted top view 44% off).
- *Authored input values*: numbers a person/AI has to write for the build (panel ids, sizes, rectangles,
  origins, axes, grids). B's figure excludes the depth atlases, which were authored by per-object rules
  (`prep_sheetfirst_inputs.py`, ~250 lines): circles for knobs, dark regions for screens/windows, the
  crown profile turned into relief, cushion bulges.
- Gate pass means technically valid, not good: open-surface lines are not checked as solids.

Two of my own measurement bugs were found and fixed before scoring (reference masks taken from a corner
pixel; preview framing on one mesh of B's multi-mesh GLBs). A third measure (crown slice) failed its own
validation (A scored 0.55 against 0.95 end-on) and is not used.

## Visual assessment (subjective, from the comparison sheets; 1 = unusable, 5 = ship it)

| Object | A | B | What decides it |
| --- | --- | --- | --- |
| Oven | **4** | 3 | Fronts nearly identical; B crisper paint. **B's back is open: from behind you see the inside of the front panel.** A is a closed body with separate door/drawer slabs and 3-D coil burners. |
| Refrigerator | **4.5** | 2.5 | A has the rounded cabinet, closed and clean. **B has dark fringes and square notched corners on every edge** (the sheet background inside the rounded views is carried onto rectangular panels; no corner panels exist), and is 7-9% oversize. B's flat faces are sharper. |
| Crown moulding | **4** | 1.5 | A builds the real profile (0.95 against the drawing); its top face is smeared. **B cannot make a moulding with thickness**: a relief sheet with no ends, gate-flagged for UV stretch. B's ornament is crisper face-on. |
| Television | 3.5 | 3.5 | A: closed, real knobs, but the voxel surface is soft and lumpy and the paint blurry. B: crisp box and the sharpest paint of all ten, but black background fringes, every panel stretched, open. Tie. |
| Armchair | 1 | **2** | A is a box with an armchair painted on it. B is recognisably an armchair (back, seat, arms) but floating panels, black background rectangles round the arms, no legs or arm tops. B wins; neither is acceptable. |

## Stress test (oven, five variants: avocado repaint, 36-inch wide, deeper and taller, a different painted design (harvest gold sheet), no drawer)

`stress/stress_sheet.png`. **Both systems built all five automatically, with no modelling-code change, and all
ten look like credible ranges.** Version A needed one input change per variant (a size number, or new panel
labels for the other sheet). Version B needed every panel's size and position recomputed and 20 stretch
declarations across the variants: I scripted that (`stress_test.py`), but such a generator is extra machinery
the legacy line doesn't need. B kept its open back in every variant.

## Answers

1. **Does the sheet-first system actually produce better models?** No. On the five objects it wins one
   (armchair, where both fail), ties one (TV), and loses three (oven, refrigerator, crown) on geometry. Its one
   consistent advantage is texture sharpness and placement on flat faces (front-texture correlation higher
   on 3 of 4 measurable objects: fridge 0.97 vs 0.85, crown 0.88 vs 0.60, TV 0.95 vs 0.52; oven 0.92 vs 0.94).
2. **Where is it superior?** Flat, box-like faces seen head-on (TV, oven front, fridge faces): crisper paint
   because it uses the painted pixels directly instead of re-baking. And objects the legacy atlas line can't
   shape at all (the armchair), because panels can be placed anywhere.
3. **Where does the original system outperform it?** Everywhere geometry matters: closed solids (B is open on
   all five: 304-636 open edges), rounded edges (fridge), true profiles and thickness (crown), real protruding
   parts (knobs, handles, coil burners as geometry), clean silhouettes without background fringes, correct
   size without manual sizing. It also needs ~10x fewer authored input values.
4. **Does it reduce texture distortion?** Not in general. It has no area distortion on flat panels, but any
   panel whose painting doesn't match real proportions must be stretched (10 of 26 panels here, 100% of the TV),
   and relief displacement stretches steep faces (crown 19% vs 3%). What it reduces is *resampling blur*.
5. **Does the extra preparation outweigh the benefits?** Not for these objects. Each B object needed a
   hand-made construction manifest (87-155 values) plus a depth atlas authored by object-specific rules,
   against 1-9 values for A; and ChatGPT's paintings are not drawn to scale, so stretch overrides are routine.
   The sharper paint does not pay for open shells, fringes and missing profiles.
6. **Can both run without human intervention?** Once inputs exist, yes: both built every benchmark and stress
   model with no repairs. But B's inputs (panel placement, sizes, depth atlases) need a person or a generator
   written per object family; A's inputs are a one-line work order (labels + sizes), with geometry inferred.
7. **Which is more suitable for mass production?** The legacy factory. Its input cost per asset is far lower,
   it produces closed, correctly sized solids, and its failures are caught by a gate calibrated on 180+ assets.
   B builds faster (2-4 s vs 8-30 s, because it skips baking), but build time is not the bottleneck; input
   preparation and visual defects are.
8. **Replace, complement or abandon?** **Complement, narrowly.** Don't replace the factory. Two ideas from B are
   worth adopting inside the legacy lines rather than as a separate line:
   - **Keep painted pixels where a face is flat and seen square-on**, instead of re-baking: bake only what needs
     projecting. This would take B's one real win (sharpness) without its open geometry.
   - **Dimensioned panel placement** as a fallback for objects the atlas line can't shape (chairs, sofas), but
     only once it can make closed, thick parts and mask out the sheet background.
   As a stand-alone line in its v1 form (open surface patches, no holes, no thickness, background carried onto
   panels, hand-authored manifests), it should not be used for production assets.

## What would change these conclusions

- References painted to scale with true UV nets (what SHEETFIRST.md asks for) would remove B's stretch
  overrides and background fringes; that is a different artwork pipeline, not what ChatGPT has been producing.
- A B v2 with thickness, closed shells and background masking would remove its biggest geometry defects.
- Version A's oven side panel came from an earlier labelling choice (panel 26, with a dark notch); B's used the
  vented side panels (24/25). The B side looks better for that reason, not because of the pipeline.

## Reproduce

```bash
blender -b --factory-startup --python docs/benchmarks/sheetfirst_vs_legacy/prep_sheetfirst_inputs.py
blender -b --factory-startup -P tools/factory.py -- build bench_a_oven bench_a_fridge bench_a_crown bench_a_tv bench_a_armchair
# in a worktree of chatgpt/sheetfirst-panels-v1:
blender -b --factory-startup -P long-lines/tools/factory.py -- intake_sheetfirst <inputs/OBJ/B/manifest.json> --name bench_b_OBJ
blender -b --factory-startup -P long-lines/tools/factory.py -- build bench_b_oven ...
blender -b --factory-startup -P docs/benchmarks/sheetfirst_vs_legacy/bench_render.py -- OBJ A|B
python3 docs/benchmarks/sheetfirst_vs_legacy/compose_sheets.py
blender -b --factory-startup --python docs/benchmarks/sheetfirst_vs_legacy/stress_test.py
```
