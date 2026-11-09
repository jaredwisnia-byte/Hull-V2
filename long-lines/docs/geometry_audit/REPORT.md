# Geometry reconstruction audit (Nov 9)

Subject: `car_sedan_tan`, with the coffee machine (`coffee_maker_drip`) and the sofa parts sheet
(`fixture_sofa_parts`) as controls. The project never uses real brands, so the car keeps its
invented name.

Tools added for this audit, reusable on any prop:
- `tools/diag/render_modes.py`: the same cameras in seven modes (textured, clay, wireframe, albedo,
  shading normals, true face normals, depth).
- `tools/diag/metrics.py`: silhouette IoU against the reference views, ridge energy, folds per 1000
  faces, open edges, degenerate triangles.

## 1. Root causes

Each cause is classified as Geometry, UV projection, Texture, Normals/shading, Material,
Reconstruction input, or a combination.

### Circled area: rear door, rear quarter window, beltline

Three separate things are visible there.

1. **Vertical grooves down the doors.** Class: *Geometry, from reconstruction input*.
   - Cause: the top view is 134 px across 1.94 m, so 1 px is 1.45 cm. The body side, drawn as a
     gentle curve, is a staircase of 5-6-5-6 px steps, and each step became a full-height groove.
   - Fixed. Evidence: clay renders in `5_car_before_after.jpg`, rear-quarter row.
2. **A flat ledge where the cabin meets the body.** Class: *Geometry (method limit)*.
   - Cause: the visual hull can only narrow the cabin where the front and back outlines narrow, so the
     tumblehome becomes a horizontal step running the length of the cabin.
   - Still there. It is now crisp instead of lumpy.
3. **The dark band along the beltline.** Class: *UV projection*.
   - Cause: projection blends views by how squarely they face each surface. The rounded ledge faces up
     and out at about 45°, so the side view weighs as much as the top view. The side view sees the
     ledge edge-on, where it shows the black window seal, and that one line is stretched over the
     ledge's whole width.
   - The band appears in the albedo render but not in the clay render. Still there.

### A. Horizontal ridges on the hood, trunk, roof and windows

Class: *Geometry*, caused by *reconstruction input quantisation* and meshing on on/off voxels.
Projection amplifies it.

Evidence:
- The ridges appear in the clay, shading-normal and true-normal renders (`2_diag_car_hood_side.jpg`).
  They are not in the albedo, so they are not a texture.
- **The dense mesh before decimation already has them** (`3_decimation_ruled_out.jpg`). That rules
  out decimation and vertex normals.
- Reading the surface height straight from the reconstruction field along the hood found 27 steps of
  up to 11.2 mm. One side-view pixel is 12 mm.
- The side view's hood edge is a staircase, falling 1 px every 10-15 px.
- Hull meshing sampled each outline as on/off pixels into on/off voxels. Every flat tread became a
  terrace. Every riser faces the front view, so projection paints a stripe of grille colour on it,
  which is why the earlier car showed coloured streaks.
- Smoothing afterwards only shortens a terrace; it can't remove a 15 px tread.

Hypotheses tested and rejected on the way (recorded so nobody tries them again):
- **Smoothing the outline's distance by 1 px:** rounds the steps, keeps the treads.
- **Douglas-Peucker polyline fit:** it puts vertices on the staircase corners, so treads survive
  exactly.
- **Rasterising the fitted curve 4× finer:** leaves a quarter-pixel staircase.
- **Taking the inside/outside sign from that raster:** snaps the zero crossing back onto the raster.

### B. Correct proportions, planar bodywork

Class: *Geometry (method limit)*.
- A visual hull is the intersection of the outlines extruded straight through the object. So every
  horizontal slice is the intersection of axis-aligned extrusions: a rectangle clipped by the top
  outline.
- Nothing estimates curvature between views: crown on the hood or roof, tumblehome, the round of a
  fender.
- The one exception is `propkit/revolve.py`. When the top view is round, it replaces the slices with
  ellipses.
- **Not fixed here.** The plan below (P3) generalises revolve into fitted superellipse slices.

### C. Windshields like slats; distorted door seams

- **Slats:** the same terraces as A on the sloped glass, each riser catching projected paint. Class:
  *Geometry + projection*. Fixed with A.
- **Door seams:** the seams are painted (*Texture*). They looked distorted because the vertical
  grooves from the circled area run through them (*Geometry*). Fixed.
- The engine tells apart:
  - a part boundary, a crease and a rounded edge, **only** when an edge guide is supplied
    (`propkit/edge_guide.py`);
  - painted lines from geometry automatically, **only** in the sense that painted lines never carve:
    only outlines do.

  There is no automatic material-boundary detection.

### D. Wheel arches and circular features

- **Arches:** these are only the side view's outline. Nothing is cut and no curve is fitted.
- **Wheels:** the side view's circle intersected with the front view's corner blocks gives a cylinder.
  Wheel and arch are one solid, so there is no wheel well.
- **The same method handles:**
  - any opening that shows in an outline, such as the coffee housing's C-shape;
  - round parts, through the lathe step.
- **It cannot handle:** blind holes, recesses or handles seen face-on. Silhouettes can't show them.
  That needs a cut operation driven by a part map or an edge guide (plan P5).

### E. Glass, paint, metal and rubber look alike

Class: *Material*.
- Every hull asset gets one albedo and an ORM map with uniform roughness (the order's `rough`, 0.55
  on the car) and zero metallic.
- Nothing classifies glass, chrome or rubber.
- Plan P2: a general per-texel material classification from the painted colour, written into the ORM.

## 2. What was implemented: the fitted-outline signed-distance hull

`propkit/hull.py`, now the default for every hull build (`HULL_FIELD=binary` restores the original):

1. Each view's outline is traced to a sub-pixel contour.
2. The contour is smoothed along its length with sigma 4 px, holding real corners fixed: points where
   it turns more than 40° within ±4 px. A 12 px staircase is attenuated about tenfold, and a box
   corner stays a corner.
3. Each view's signed distance in metres is measured exactly to that curve:
   - a KD-tree over points every 0.2 px along the curve;
   - near the curve, the distance along the nearest point's normal;
   - the sign from the curve itself, so no raster staircase gets back in.
4. The hull field is the maximum over all views.
5. Carving steps (blades, lathe, the parts' cavities) still run on voxels, so their decisions don't
   change. Near what they removed, the surface follows the carved solid's own smoothed distance. Using
   the removed sliver's distance crinkled the surface (1,691 folds on the carafe).
6. Marching cubes runs on the continuous field.

No object-specific code. Car, coffee machine and sofa all go through the same function.

## 3. Results

Same references, same orders, same cameras. The before builds use `HULL_FIELD=binary`.

| Asset | Ridge energy (deg) | Silhouette IoU (mean of views) | Folds per 1000 faces |
|---|---|---|---|
| Car | 6.75 → **5.14** (−24%) | 0.963 → **0.973** | 0 → 0.03 |
| Coffee machine | 4.87 → **2.88** (−41%) | 0.914 → 0.915 | 1.05 → 1.23 (6 → 7 folds) |
| Sofa | 5.58 → **4.70** (−16%) | 0.926 → 0.924 (−0.0025) | 1.92 → **0.42** |

- **Car:** clean hood and roof in the normals render, no door grooves, crisp shoulder. Its order's
  special `blur`/`smooth_iters` settings are no longer needed: default settings score 0.973 IoU.
- **Coffee machine:** the housing stays boxy and crisp, the stepped ridges on top are gone, and the
  carafe is still detected as round and built round.
- **Sofa:** the cushions keep their shape and the back cushions lose their ridges. One possible loss:
  the inset line on the front of the arms is fainter.
- **Gap checks:** all pass. The sofa's worst contact moved from 0.6 mm to 2.5 mm, under the 4 mm
  limit.

Synthetic suite (`tools/test_hull_geometry.py`, 9 s):

| Case | Result |
|---|---|
| Box | volume/bbox 1.00 |
| Slope drawn at low resolution | normal spread 4.18° binary → 1.29° fitted |
| Round-topped vase | built round, slice radius spread 0.9% |
| C-shaped housing | keeps its cavity |

There were no folds in any case.

**Timings per build** (now in every ledger entry as `stage_seconds`):

| Asset | Geometry + paint | Bake + export | QA | Total |
|---|---|---|---|---|
| Car | 45 s | 27 s | 1.4 s | 73 s |
| Coffee machine | 26 s | 23 s | 0.7 s | 49 s |
| Sofa (5 part kinds, 13 parts) | 148 s | 39 s | 1.5 s | 188 s |

The hull field itself takes a few seconds per part. Fitted vs binary costs +2 to +9 s per asset.
Baking is the biggest fixed cost.

## 4. Regression tests

- **`tools/test_hull_geometry.py`** (Blender, 9 s): the synthetic cases above.
- **`tools/diag/regress_assets.py`** (about 5 min):
  - rebuilds car, coffee machine and sofa fixture from their orders;
  - fails on a silhouette drop over 0.005, more than 0.5 extra folds per 1000 faces, or 0.3° more
    ridge energy than `factory/geometry_baseline.json`;
  - restores the library and ledger afterwards.
- The audit itself showed why mesh-health measures are needed. The first version of the fix passed
  silhouette and ridge measures while the coffee machine and sofa were full of folds; only the
  renders caught it. Folds per 1000 faces now catches it automatically.

## 5. Prioritised plan for general operations

| # | Operation | What it fixes | Status |
|---|---|---|---|
| P1 | Fitted-outline SDF hull (feature-preserving at the source) | terraces, grooves, slats (A, C) | **done** |
| P2 | Projection weighted by texel stretch; a view never paints a face it sees edge-on. Material classes from painted colour (glass, chrome, rubber, paint) into roughness/metallic | beltline band, leftover paint streaks (circled area, E) | next: cheap, texture-only |
| P3 | Superellipse slices: generalise the lathe to slices `\|x/a\|^n + \|y/b\|^n ≤ 1`, with n fitted per component from the top/side views' corner rounding (n=2 ellipse, large n box) | planar bodywork, rounded boxes (B) | design below |
| P4 | Declarative construction plan + planner (below) | choosing operations without code | design below |
| P5 | Cuts from part maps / edge guides (recesses, blind holes, wheel wells) | D | needs input data |
| P6 | Sweeps along a medial axis (handles, pipes, trim) | handles built as slabs | later |

### P4: a construction plan instead of code

The pieces already exist as operations:
- `hull_prop` (hull);
- `revolve` (lathe);
- `hull_assembly` (placing, seating and gap-checking parts);
- `edge_guide` (creases and rounding);
- `blades` (hollows).

The proposal:
- Write the plan as data, one entry per component:
  `{"component": "carafe", "op": "lathe", "params": {...}, "confidence": 0.99, "alternatives": ["hull"]}`.
- An executor dispatches on `op`, so adding an operation never touches the executor.
- The planner picks operations from measured shape descriptors, never object names:

| Measured descriptor | Operation |
|---|---|
| top-view ellipse IoU ≥ 0.96 (box 0.83, squircle 0.90, measured) | lathe |
| bounding-box fill ratio and corner sharpness | box / rounded box / superellipse |
| thickness ÷ extent in one view | thin panel |
| constant width along a skeleton | sweep |
| holes in an outline | through cavity |
| colour edges inside an outline with no outline change | paint only |

- When two operations are plausible, both are built and the one with the better silhouette IoU against
  the references wins (`metrics.py` already measures it). This is cheap analysis-by-synthesis; it
  needs no general optimiser, which wouldn't fit a one-minute budget.

## 6. Remaining limits

- **Not yet rebuilt:** the library GLBs are the untouched baselines. Rebuilding them with the new
  default is one command each. The new builds pass QA (triangle budget, size) and the gap checks, but
  they have not been re-checked in Godot, so they are not claimed game-ready.
- **Cabin ledge and beltline band:** both remain (P2, P3).
- **Faint grain on the hood:** a little remains in the textured render. In the clay render the hood is
  clean, so it is paint, not geometry.
- **Sofa:** silhouette IoU down 0.0025, and the arm's inset line is fainter.
- **Coffee machine fold count:** varies run to run (0.35 to 1.23 per 1000 faces). Decimation isn't
  deterministic.
- **The overall answer:** silhouette-driven reconstruction is now clean. Shape that no outline shows
  (crown, recesses, sweeps) still needs P3 to P6 before ordinary assets need no new modelling code.
