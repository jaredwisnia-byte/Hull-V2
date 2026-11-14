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
   - Game tolerance t = d x 0.00097 rad (60 deg vertical FOV, 1080 lines; to be confirmed by Jared).
5. **Tessellation per part**: a round part of radius r becomes the smallest n-sided prism with
   r(1 - cos(pi/n)) <= t, i.e. n = ceil(pi / arccos(1 - t/r)). A feature that stands out from its
   part by less than t, or is narrower than 2t, is texture + normal map only. Parts are welded at
   seams. No simplification of a blob.
6. **Texture and bake** (`texturing.py`, `bake.py`): paint projected from the views onto the
   chosen surface; what the low poly drops is baked from the exact part model into the normal map.
7. **QA** (`qa.py`, `drawing_qa.py`): drawing in mm and pictorial checks on every output, at the
   profile's tolerance; hygiene per part.
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

## Migration steps (do in order)

1. Settle current work: regression run; drawing keeps openings; QA registers on the main body.
2. Fidelity profiles in the current pipeline (sets tolerance and budget only).
3. Part model from the drawing (one solid per part), output beside the current mesh, unused.
4. Tessellate per part + texture/bake from the part model, behind `"construction": "parts"`.
5. Detail views and the part graph (accept a part only when two or more views agree).
6. Retire the voxel path for manufactured parts; keep it as the organic fallback.

Known open items at the start: measured roundness adds folds on the hair dryer (dense 49 -> 238;
stop fixing in the voxel path, step 4 removes the cause).
