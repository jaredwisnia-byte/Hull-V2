# Hull architecture (agreed direction, 2026-11-14)

Hull builds every asset as a set of measured **parts** made from the **technical drawing**, then
tessellates each part to the **fidelity** the user asks for. It does not build one dense voxel
surface and simplify it. The drawing is the same for every output; only the last stages change.

## Pipeline

1. **Intake** (`sheet_blobs.py`, `vision_order.py`, `sizing.py`): views, labels, scale. Unchanged.
2. **Drawing** (`drafting.py`, `drawing_cad.py`, `rounding.py`, `features.py`): views oriented and
   reconciled (opposite views mirror; a part one view omits is kept when the other two directions
   support it), lines and arcs within 1 px, circles, round axes, measured roundness per part,
   local features, sizes in mm, DXF + PNG + `drawing.json`. Identical for every fidelity.
3. **Part model** (new; grows out of `cad_model.py`): named parts, each an exact CAD solid
   (extruded profiles, lofts through measured sections, revolves) with features attached to their
   part. Painted detail inside a part stays a decal / normal-map source, never carved into a
   shared field.
4. **Fidelity profile** (new; chosen by the user): one number, the allowed surface error t (mm).
   - `engineering`: t = 0.05 mm, exact surfaces, all features modelled.
   - `game_hero`: viewing distance 0.5 m. `game_prop`: 2 m (default). `game_background`: 10 m.
   - Or `{"distance_m": d}` or `{"budget": n_triangles}` (raise t until the budget is met).
   - Game tolerance t = d x pixel angle; default 0.00097 rad (60 deg vertical FOV, 1080 lines).
     The profile takes `fov_deg` and `lines` so a known target camera replaces the default.
5. **Tessellation per part**: a round part of radius r becomes the smallest n-sided prism with
   r(1 - cos(pi/n)) <= t, i.e. n = ceil(pi / arccos(1 - t/r)). A feature that stands out from its
   part by less than t, or is narrower than 2t, is texture + normal map only. Parts are welded at
   seams. No simplification of a blob.
6. **Texture and bake** (`texturing.py`, `bake.py`): paint projected from the views onto the
   chosen surface; what the low poly drops is baked from the exact part model into the normal map.
7. **QA** (`qa.py`, `drawing_qa.py`): drawing in mm and pictorial checks on every output, at the
   profile's tolerance (rule R10; today's thresholds are still fixed percentages until Codex's
   Order 5 ties them to t); hygiene per part.
8. **Exports**: GLB per fidelity; STEP and engineering drawing from the same part model.

The voxel visual hull (`hull.py`) remains only as a **per-part fallback** for organic shapes whose
sections do not fit lines, arcs and superellipses within tolerance (sofa cushion, carved leg).

## Rules (apply to every change)

- Never select geometry from an object name or tune a rule to one example. Every rule must be
  geometric/measured and stated in the code's docstring.
- The drawing stays first and unchanged in purpose; nothing builds from raw painted outlines.
- Every step sits behind a switch; the current pipeline keeps building every object until the new
  path beats it on the same inputs.
- Gate for every step: before/after contact sheet on the drawn regression set
  (`car_sedan_tan coffee_maker_drip electronics_tv_crt electronics_tv_crt2 sofa_olive_suede
  table_leg_carved table_leg_guided wallphone_rotary`) **and** the seven image-only objects
  (`001_toaster ... 007_stand_mixer`). A change that makes any of them worse is not done.
- QA thresholds are never loosened to make something pass.
- **Same photo, same mesh (R9).** A build is a pure function of its input image, order and code
  version: two builds of the same input give byte-identical GLBs. Nothing a previous build wrote
  (learning memory, caches, `.hull-runs`) may change geometry. Reconstruction memory is `off` by
  default; `learning` is for experiments only and its reports say `reproducible: false`. A
  difference between repeat builds is a defect to fix at its cause, never a tolerance.
  **Scope:** byte identity is required for the same input, order, code *and toolchain* (Blender
  version, Python packages, operating system). A new toolchain may legitimately change bytes (PNG
  compression, floating-point rounding). Then rebuild the baselines once, compare old and new
  toolchain by measurement (geometry within the fidelity tolerance, each texture within a stated
  difference), record it, and return to byte identity on the new toolchain.
- **QA at the profile's tolerance (R10).** Allowed error follows the fidelity the user asked for,
  not fixed percentages. The drawing check passes a view when its 95th-percentile outline distance
  is within max(2t, floor), where t is the profile's tolerance and the floor is what can be
  measured: max(1 mm, two QA raster pixels, 1.5 x the sheet's millimetres per source pixel for
  that view). Overall size: within max(3t, floor). Outline overlap (IoU) is reported and kept only
  as a backstop for gross errors (fail below 0.80), because it punishes thin parts for a one-pixel
  error. A profile asking for t below the floor gets "unverifiable at this fidelity", reported,
  never a pass. Mesh-health limits (folds, components) do not depend on t.
- **No new Blender dependencies.** New code (part model, tessellation, QA, export) is plain Python
  (numpy, scipy, build123d/OpenCascade, trimesh, xatlas) and runs without Blender. Blender is being
  replaced (see below); until each piece reaches parity it stays the default behind
  `HULL_BACKEND=blender|python`.

## Replacing Blender

Blender currently provides mesh editing, simplification fallback, UV unwrapping, ray casts for QA,
paint projection and normal baking, GLB export and turnaround renders. Each moves to Python behind
`HULL_BACKEND`, in this order, each proven against Blender's output on the same inputs before it
becomes the default: inventory -> mesh core -> GLB export -> QA -> UVs, projection and baking ->
renders -> end-to-end `python` backend. Blender is then optional (renders only) and finally
removable. Motivation: every test needs a Blender process (4-6 minutes a build), a hard-coded
install, Blender's decimator and normal recalculation caused defects, and it is the only GPL
dependency.

## Migration steps (do in order)

1. Settle current work: regression run; drawing keeps openings; QA registers on the main body.
2. Fidelity profiles in the current pipeline (sets tolerance and budget only).
3. Part model from the drawing (one solid per part), output beside the current mesh, unused.
   Detailed design for steps 3-4 (curves not light, automatic parts, statistics against
   noise, rules for unseen sides): [CURVE_RECONSTRUCTION.md](CURVE_RECONSTRUCTION.md).
4. Tessellate per part + texture/bake from the part model, behind `"construction": "parts"`.
5. Detail views and the part graph (accept a part only when two or more views agree).
6. Retire the voxel path for manufactured parts; keep it as the organic fallback.

Known open items at the start: measured roundness adds folds on the hair dryer (dense 49 -> 238;
stop fixing in the voxel path, step 4 removes the cause).

## Record of runs (archive)

Each finished Codex run is filed into the run archive before anything from it is merged:
orders, report, baseline, per-attempt evidence, QA results, and every model GLB stored once
by SHA-1, indexed in a SQLite file (`hull.db`). The tool is in git
(`long-lines/tools/hull_archive.py`); the archive (evidence and GLBs) sits beside the
repository, not in it. Determinism (R9) is what keeps it small: intermediates are not kept,
because the recorded commit rebuilds them byte for byte. Filing only copies and never
overwrites. Plan, tables, procedure and phases: [ARCHIVE.md](ARCHIVE.md).

## How QA compares the result with the sheet (state on 2026-11-14)

1. **Old outline check** (`qa.py`): rays cast from the six orthographic directions give the mesh's
   silhouettes; each is stretched with the painted view's outline to one box and compared (IoU).
   Stretching hides proportion errors. Top/bottom rasters now use the third-angle frame.
2. **Against the drawing, in mm** (`drawing_qa.against_drawing`): mesh triangles projected along
   each axis at 0.5 mm per pixel, compared with the drawn profile with no rescaling. Fails if IoU <
   0.90, the 95th-percentile outline distance > 3% of the object, or an overall size is off by more
   than max(2 mm, 3%). Overlays `drawing-match-<view>.png`. Aligned at the mesh's bounding-box
   corner, which a thin outlier (a cable) can shift; Codex Order 3 registers on the main body.
3. **Against the sheet's pictorial view** (`drawing_qa.against_pictorial`), never used to build:
   - outline: the mesh rotated over camera angles from above (azimuth 15 degree steps, elevation
     5-60, then refined), fitted to the picture's outline box; best IoU must reach 0.85.
   - shading: at that pose, one light fitted to the painting from the mesh's own normals
     (brightness = n . l + c, least squares); R^2 must reach 0.25 (square vs round dryer handle:
     0.21 vs 0.31).
   Limits: assumes an orthographic picture; paint bands lower R^2; no colour/texture comparison; the
   CAD solid and the sheet's detail views are not compared yet; thresholds are provisional.

## The part model (design for steps 3-4)

The middle of the pipeline becomes a list of named parts, each an exact CAD solid, replacing the
single shared voxel field.

**Each part holds**
- shape: construction (profiles extruded and intersected / loft through measured sections /
  revolve) and its measured roundness exponent per axis;
- features attached to it: bumps (sized from the view that faces them), holes, bosses;
- attachment: which part it sits on and where (contact, seating);
- paint ownership: which pixels of which views belong to it (for projection);
- fine detail: markings, grilles, numerals kept as texture and normal-map sources, not carved.

**Where parts come from:** the drawing (abrupt section changes along an axis split parts; round
end views; measured roundness), and later the part graph that matches detail views to regions,
accepting a part only when two or more views agree.

**From parts to a mesh:** fidelity sets tolerance t; each part is tessellated to t on its own
(round surfaces: fewest sides with r(1 - cos(pi/n)) <= t; flat faces: fewest polygons; features
under t become texture and normal map); parts are welded at seams; paint is projected onto the
chosen surface and dropped detail baked from the exact parts. STEP and the engineering drawing come
from the same parts, so they cannot disagree with the mesh. QA runs per part as well as whole.

**Worked example: hair dryer as a room prop (t = 1.9 mm)**

| Part | Built as | Game mesh |
|---|---|---|
| Barrel and nozzle | Loft through superellipse sections along its axis (n = 3.5) | 12 sides |
| Handle | Loft along its height (n = 2.6) | 7 sides |
| Switch | Box feature, 5 mm wide, 4 mm proud | Modelled (4 mm > t) |
| Grille and vents | Painted detail on the barrel | Normal map |
| Cord | Swept along its curve | Few-sided tube |

At `engineering` the same parts export as exact surfaces in STEP (grille possibly as real slots);
at `game_background` (t = 9.7 mm) the barrel is about 5 sides and the switch is texture.

**Why it fixes today's defects:** no shared grid (no folds or slivers where carving fields meet),
no simplification of a blob (thin parts kept, sides chosen deliberately), one source for mesh,
STEP and drawing, and per-part QA.

## Decisions (2026-11-14)

Made by Claude at Jared's request ("do it for me"); Jared can overrule any of them.

1. **The part model is the core of Hull.** The voxel hull is kept only as the per-part fallback for
   organic shapes.
2. **Profiles:** `engineering` (t = 0.05 mm), `game_hero` (0.5 m), `game_prop` (2 m, **default**),
   `game_background` (10 m), plus `{"distance_m": d}` or `{"budget": n_triangles}`.
3. **Screen assumption:** 60 deg vertical field of view, 1080 lines (0.97 mrad per pixel) is the
   default, exposed as `fov_deg` and `lines` on the profile. Higher resolutions only make t smaller,
   so the default never produces a coarser mesh than a 1080-line screen needs.
4. **Shading of game meshes:** smooth across each exact (B-rep) face of a part; hard edges at B-rep edges whose faces meet at more than 30 degrees, at part seams and around features. Never a fixed angle between mesh facets (a 7-sided handle has 51 degrees between facets and must still read round).
5. **Voxel fold fixes are paused** until migration step 4; step 4 removes their cause.
