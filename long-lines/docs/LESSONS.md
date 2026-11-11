# Lessons learned

Mistakes made on this project and the rule that prevents each one. Read before working;
add to it whenever something goes wrong.

## Automatic parts-sheet intake (Hull V2)
- A parts work order keeps complete reference views in its assembly subfolder.
  Pointing QA at the source root silently skipped every silhouette comparison.
  Resolve the assembly folder explicitly and fail automatic orders when any of
  the five required reference comparisons is absent.
- A failed rebuild can leave an earlier GLB on disk. Standalone export must check
  that the current build actually wrote its artifact before packaging it.
- Glass painted against a dark background can be mistaken for silhouette holes.
  Keep the vessel core filled while preserving the external handle aperture;
  inspect both clay geometry and textured turnarounds.

## Brands and content
- **AI texture sheets paint real brands** (Zenith, Mercury Montego, KitchenAid). Every sheet
  goes through `tools/prepare_sheet.py`, and a person or Claude must look at `_review.png` and
  the crops before building. Add new brand regions to the layout so repeats are automatic.
- Keep originals with real brands out of the repo; record provenance in `SOURCE.md`.
- Check period details too: pull-tab food cans, espresso machines and microwaves are not
  1975 New York tenement items.

## Blender pipeline
- Cycles bakes come out **black, silently**, on builds without OpenImageDenoise unless
  `use_denoising = False` is set before the first bake (the kit does this).
- Label coordinates must be **face-corner** attributes everywhere. Mixing point and corner
  domains makes joined parts lose their labels (the can lids came out white).
- Wrapped labels need per-face seam handling or the wrap seam smears (`core.wrap_uv`).
- `planar_uv` reads object-local coordinates, before rotation: pick axes in the part's
  own frame (the wheel faces showed tread because of this).
- Vertex colour red is used as the bevel-edge mask in game shaders; don't reuse it.

## Reading painted sheets
- Sheets put views close together: a crop can include the next view (the second car's roof
  under the first). Use the largest connected shape, and take outlines from the edge of a
  view that has nothing beyond it on the sheet.
- Never use `np.roll` for image morphology: it wraps around the edges.
- Wrecks (no glass) and loose trim pieces break outline tracing. **A car is a car:** take
  the body shape from one clean reference sheet (`CARS[...] = (desc, body_sheet)`) and only
  swap paint.
- Painted sheets have light and shadow painted in; in-game lighting darkens them further.
  Keep painted props' lighting gentle.

## Godot
- A RefCounted test runner whose coroutine awaits must be held by a variable, or it is freed
  and the await silently never returns (the smoke test hung).
- `:=` from a Variant is a parse error by default: type it explicitly.
- `Control.set_anchors_preset` does not move offsets: centre controls with anchors 0.5 and
  explicit offsets (`hud._center`).
- `HUD.close_panel()` unpauses the sim; tests that drive time must re-pause.
- Ties in raycasts go to the other body: give interactive surfaces (the window sill) a
  millimetre of margin.

## Process
- Look at a rendered image after every visual change; numbers alone hid black bakes and
  floating wheels.
- Rebuilding props: change shared parts (`propkit/parts.py`) rather than patching recipes,
  so every prop using the part improves at once.

## Tiles and surfaces (Nov 8)
- Painted organic tiles (wallpaper, wood, carpet) are made seamless by edge cross-fading;
  regular grids (checkerboards, tile) must not be blended: crop a whole number of repeats,
  measured from per-row autocorrelation (averaging rows first cancels a checkerboard).
- Wide AI strips (2172x724) usually hold three variants side by side: crop one.
- Store tiles as JPEG (quality 90): a fifth of the PNG size, no visible loss.
- Drive files land in the connected account only (jared.wisnia@gmail.com); downloads come
  back as base64 JSON saved to tool-results files: decode them there, never into context.

## Visual hull (Nov 8)
- Outlines on dark sheets: dark object parts (screens, back panels) read as background.
  Fill anything bounded along both its row and column; for boxy objects use `convex=True`;
  mark unreliable views `paint_only` so they texture without carving.
- Check each view's mask image before blaming the 3D step (the back view caused the hole).
- System scipy/skimage only work inside Blender's Python (system numpy is too new);
  run mask debugging through `blender -b -P script.py`.
- Small views (~300 px) give soft textures: ask for large views when a prop matters.

## Painted parts and critique (Nov 9)
- Hull models leave painted knobs flat: detect round features (Hough circles) and build them
  with `part_rules`. Tiny radii (<2.5% of view width) are edge noise; when circles overlap keep
  the larger, or highlights inside a knob crowd out the knob itself.
- Prefer the painting's evidence over rules: a side view shows how far parts stick out
  (`hull.side_evidence`). Rules alone made the knobs 35 mm deep where the drawing showed ~10 mm.
- The critic found both problems by numbers before anyone looked: run it every time.
- Image texture v runs bottom-up in Blender; mask rows run top-down. The hull's top view was
  painted front-to-back flipped because of this (found by looking at the turnaround, not by
  the numbers: the critic measures shape, not texture placement).
- AI sheets are inconsistent between views (the TV's side views omit the knobs): absent
  evidence is not evidence of flatness. Only a distinct bump counts.

## Factory (Nov 9)
- Calibrate the gate on known-good assets before trusting it: the first library run failed 36
  of 118, and over half were the gate's fault (chairs "have holes", wall frames "float").
  Mounting (floor/wall/ceiling/top) and solid-vs-open are part of the standard.
- Fix defects in the machine, not the asset: seating on the floor, outward normals, triangle
  budget and texture size are enforced in `bake.standardize`/`fit_texture` for every asset.
- Texture size must come from the measured UV coverage after unwrapping; estimates were
  4x off on many-island props.
- GLB bytes are not reproducible (Blender's UV packer); reproducibility is measured on the
  gate's gauges (triangles, dimensions, outline scores) via `gauge_hash`.
- When a correction fires for a category, move it into `categories.json` so the next asset
  of that kind passes first time (tv: back view paint-only).

## Multi-asset sheets: facades, part atlases, trim (Nov 8 batch 2)
- Splitting a facade atlas by connected blobs breaks buildings at their dark shopfronts.
  Atlas sheets are laid out on background gutters: a recursive gutter cut (XY-cut) is right.
- Trimming an elevation to the "longest run of bright rows" kept a sliver: dark windows look
  like background. Strip margins from the edges only, until a row is mostly drawing.
- Pixel-blob window detection fails on painted facades (light frames, curtains, fire escapes).
  Windows repeat: get the period by autocorrelation, the opening by folding the profile over
  one period, and only cut recesses when openings are clearly darker than the piers (else
  leave the facade painted: a hole cut into brick is worse than a flat painting).
- Big `median_filter` windows take minutes; a Gaussian blur gives "the wall around it" in ms.
- `core.box` places the box with an object transform: mesh coordinates are local. Apply the
  transform before classifying faces by position (the facade went onto nothing at first).
- Painted part atlases are not drawn to scale between panels: take depth from the category,
  and allow a real width in the order when the painting is stylised (side-by-side fridge).
- Painted stove knobs include their dial ring (to ~90 mm): the knob rule accepts that size but
  clamps the cylinder to a real knob (`max_real`).
- Painted moulding strips have shaded end caps: crop 3% off each end or the repeat shows a band.
- One sheet feeds many assets: keep one shared copy (`source_textures/_sheets/`), not one per
  asset (the first intake duplicated ~80 MB).
- Labelling a sheet (which numbered panel is which face) is the one person step: ~1 line per
  asset. Automating it further costs more than it saves at this volume.

## Sheet sets v2 (first test: fridge_1, Nov 8)
- A part map makes the outlines exact and tells the hull what to ignore: leave protruding
  parts out of the carve and add them as their own geometry, or a handle seen side-on
  becomes a slab across the whole front.
- Depth maps are relative. Calibrate them per asset from parts that can be measured
  side-on (handles in the side view), then clamp every part to the parts catalogue.
- Never cut recesses with traced outlines joined into one cutter: open or self-touching
  cutters wreck the EXACT boolean (the first fridge lost its front). Cut closed boxes one at
  a time and undo any cut that changes the body's size.
- Tiny "in" regions are screw heads, not 30 mm holes: the catalogue's `pit` class.
- The critic's turnaround has one light: check albedo numerically before blaming the texture.
- Never subtract protruding parts from an outline before carving: a hinge on the edge notches
  the whole object (ChatGPT's review spotted the grooves round the fridge). Take thin
  protrusions off with a morphological opening and close small notches; the shell stays whole.
- A part seen in several views is one physical part: build it once, from the view facing it.
- Check geometry with an untextured clay render: paint hides construction mistakes.
- The reproducibility KPI compares gauges for the same inputs, but a code change also changes
  outputs: record the line's code version in the ledger (to do).
- Shape alone misnames parts: on fridge_1 a full-width kick plate and grille slivers became
  seven front "feet" and the kick grille became door "seams". Placement rules in the sizing
  manual (feet at floor corners, handles at least a palm long, seams above the toe kick on
  appliances) rename them.
- **Evidence first (Jared, Nov 8): match the reference, don't add to it.** The reference decides
  whether a part exists (part map region AND depth relief or a side-view profile); the sizing
  manual only decides how big. The first door slabs came from a catalogue default with zero
  depth-map relief: a liberty. Parts without evidence stay painted and are listed as such.
- Compare like with like: a door "stands proud" only relative to visible cabinet body next to it,
  not to its own seam groove. Doors on one object are built alike (all or none).
- A morphological opening doesn't remove a tall thin protrusion (a handle seen side-on is thin
  but tall): judge the body outline row by row from neighbouring rows instead.
- `tools/match_check.py` puts the model's ray-cast front depth beside the reference depth map:
  run it on every sheet-set build; it shows liberties at a glance.

## Paint-only test: desk telephone from the 20-object sheet (Nov 8)
- Without depth/part maps and without a true side view, the kit line got a recognisable phone
  (wedge base by convention, keys from the painted keypad, handset from its side outline resting
  in the cradle, coiled cord) but the gate flagged it: the painted "front" is the sloped keypad
  face drawn square-on, not an elevation, so it can't match the model's front outline (64%).
  That is protocol rule 4 working: the views conflict and the factory says so instead of shipping.
- Faces with no painted view (sides, the flat rear top) get the nearest view stretched along
  them: visible streaks. A face needs its own painting or a padded flat fill.
- Small multi-object cells (~110 px per view) limit detail: 11 "keys" found for 9 painted.

## Second sheet set: desk telephone (Nov 8) — rules every object now gets
- No manifest? `tools/make_manifest.py` finds the five views on the part map by gutter cut and
  measures how well the painted and depth sheets line up (0.978 / 0.971 here) before trusting them.
- Big separate parts (the handset) are their own assembly: carved from their own outlines in every
  view, taken out of the body (rule 3). What is carved is not built a second time as a slab.
- Occlusion: a cord or a separate part in front of the body hides body. Inside the body's outline
  it counts as body; outside it, it is its own geometry. (Without this the cord and the handset cut
  slots through the base.)
- The body outline is judged by rows AND columns from neighbouring rows/columns: feet below the
  body don't become legs carved through it; hinges on an edge leave no notch.
- Raised parts are projected onto the body and stand out along the surface's own direction:
  keys on a sloped keypad stand up from the slope.
- Feet are boxes under the body: width from the front view, position front-to-back from the side view.
- Cords are rebuilt as a coil round a smoothed centre line matched across two views (hanging part).
- Square, full regions are keys; round ones (fill ~79%) are knobs.
- See-through holes are judged against the reference's own holes (a handset arch is real).

## Texture manufacturing (ChatGPT review of the telephone, Nov 8)
- The pipeline already unwrapped the finished mesh and baked an atlas; the faults were in choosing
  what to bake: one view per face by a noisy normal (patchwork), no visibility test, grazing views
  smeared. Fixed by blending views (facing^4 x visible x resolution) on smoothed normals.
- The worst "texture" fault was geometry: voxel staircase on slopes baked into shading lines.
  Measure before assigning blame. Sheet sets now use an exact polygonal hull (outlines extruded and
  intersected): flat faces, straight slopes, crisp bevels.
- Evidence that lands on a sizing limit is suspect: the depth map pushed keys to the 12 mm cap.
  Keys are 6-9 mm (manual fixed); clamped values are now reported as low confidence.
- Cross-view check: a part seen in a side view is only built if the front view shows a compact part
  sticking past that edge at the same height (a handset overhang doesn't count).

## Telephone rebuilt from scratch with the current process (Nov 8)
- Old phones deleted (paint-only kit test and the voxel sheet-set build); one clean run:
  make_manifest -> intake_set -> build -> gate -> critic -> match_check.
- Long separate parts (handset, bars, rails) are lofted: front view gives height per station, top
  view gives width per station, cross-section = superellipse (2.6, moulded plastic). Outline
  intersection can never make a rounded section. Test "long" in the front view only: earpiece cups
  make a handset deep, and the loft takes width per station anyway.
- The shell check must compare each height with the reference outline at that height (a phone narrows
  on purpose), and must slice with a true planar cut: a polygon mesh has no vertices mid-face, so
  vertex slicing returned nonsense (-700 mm) on the new hull.
- ChatGPT drew this phone narrower than real desk sets (154 mm vs 180-240): the factory reports it
  instead of stretching the mesh. Ask for corrected proportions in the reference if it matters.

## Looking back over the fridge and telephone work (Nov 8)
- The first object of each new family costs many rebuilds (fridge ~8, phone ~6) because it exposes
  a general weakness; each fix is a rule, and the next object of that family is one command.
- Most defects were found by eye (Jared, ChatGPT), not by the gate. Every check I then wrote was
  wrong at first on some shape (shell check on a phone, vertex slicing on polygon meshes, hole check
  without the reference, UV stretch that never fails, colour threshold too loose). Rule: test every
  new check on a known-bad case AND on a differently shaped good asset before trusting it.
- The reviews I do by eye (clay render, depth comparison, turnaround) should run inside every
  sheet-set build and feed the gate, so problems are caught before anyone looks.
- Measure before blaming: texture vs geometry (voxel staircase), lighting vs albedo, slicing method
  vs mesh. Each wrong diagnosis cost a rebuild.
- Repository weight: every rebuild commits new binaries (GLB + 3 PNG maps + previews). The repo grew
  to ~570 MB this session. Generated assets are reproducible from sources + orders: commit them only
  when an asset ships, use Git LFS for binaries, and keep previews out of git.

## Hull line: hollows from where the views' edges meet (Nov 9)
- Silhouettes can't show a hollow: a sofa's seat is hidden by the arms in the side view and by the
  back cushions in the front view, so the visual hull filled it to arm height. Jared's fix, as an
  engineer reads drawings: a top-view region (a seat cushion) whose top edge the front view shows as
  a horizontal line across the region's width is cut down to that line, where the two "blades" meet.
  `propkit/blades.py`, order option `"hull": {"blades": true}`. Guards that made it safe: no view's
  outline may change; a region on the outer left/right edge keeps the side view's height (an arm);
  every top-view pixel belongs to its nearest region (otherwise painted lines between cushions stay
  as walls and the seat becomes trays).
- Tried first and dropped: a global search matching every edge found in the paintings. Painted
  edges are too noisy and the views disagree by centimetres, so it carved holes at random. One clear
  rule beat an optimiser.
- The hull kept only the biggest shape in each view, so legs behind a dark gap were lost and the
  view's height scale shrank with them. Small shapes just beside the body are now kept (the TV's
  left-view match went 0.85 -> 0.94).
- Paintings are not drawn to scale: `"hull": {"width_m": ...}` stretches the views to the real width
  (the sofa came out 2.56 m wide without it).

## Parts sheets: hull_parts line (Nov 9)
- A sheet with the whole object plus each part on its own (seat cushion, back cushion, arm, leg) is
  built part by part: each part a soft hull from its own larger views, placed by measuring the whole
  object's views (`propkit/hull_assembly.py`, line `hull_parts`). The order only names which folder is
  which kind of part.
- What placed the parts reliably: the front view's top outline (flat end stretches = arms), the painted
  seams above the seat (cushion count and widths), the parts' own view proportions (thickness), the
  blade rule (seat height), shapes under the body (feet). What did not: top-view region segmentation on
  soft painted outlines (cushions merged with arms) and template matching (painted fabric matches
  anywhere; preferring large fits overshoots).
- The frame must keep only what is under and behind the parts: strips between part spaces show as lumps,
  and removing the back panel leaves cushions floating.
- Feet sunk 1.5 cm into the body above them are attached by construction.
- Don't fill holes before removing a drawn ground line: the gap between legs closes into a "hole".

### Recipe: a new parts sheet in two commands (read this first next time)
```bash
blender -b --factory-startup -P tools/split_parts_sheet.py -- SHEET.png NAME \
  --rows "assembly:front,right,back,left,top" "seat:front,right,back,left,top" \
         "back:front,right,back,left,top" "side:front,outer,back,top,bottom" "foot:front,right,top" \
  --size W D H --category sofa [--guide EDGE_GUIDE.png --guide-rows "assembly:..." "seat:front,side,top" ...]
blender -b --factory-startup -P tools/factory.py -- build NAME
```
Row names are the part kinds `hull_parts` understands (assembly, side, seat, back, foot). Check the printed
`HULLASM boxes` line before looking at renders: 4 feet, 2 sides, N back + N seat boxes. If the counts are
wrong the measurement is wrong; fix that, not the meshes. Experiments go under an `exp_` name and the
library, ledger and REPORT are restored afterwards (git checkout + delete the exp_ folders).

### What cost time on the sofa (Nov 9) and how to avoid it
- Drive images: `download_file_content` output is too big for the context; it is saved to a tool-results
  file: decode the base64 `content` from that JSON with python. Images pasted while a turn is running are
  NOT saved to disk; ask for a Drive upload.
- Never edit views in place inside assets/source_textures during experiments (a bad ground-line filter
  destroyed the copies twice). Keep originals in the scratchpad; re-copy.
- Painted feet on a part's own views must be trimmed where rows stop being ~full width (85%), not at a
  loose 60%: a band of leg was left on the arm and the separate foot clipped beside it.
- Feet: ignore scraps under the body (width < 40% of the biggest). One splitter run found 10 "feet".
- Sheets draw a long part's top view turned sideways (the arm). Rotate it when it only fits the part's
  footprint turned 90 degrees, and rotate its edge guide with it. Unrotated, it banded and distorted the arm.
- Banding: per-face "nearest view" painting stretches paint on slanted faces. hull_parts paints every
  part with texturing.project (facing^4 x visibility, padded crops) and the frame last with the parts
  occluding it.
- Edge guides (propkit/edge_guide.py): classify by hue on saturated bright pixels only (the painting is
  never that saturated); register each guide view to its painted view by the filled cyan outline
  (bridge gaps first) and refuse fits under 0.85; in hull_parts red lines are structural (they split the
  parts) and are not carved again, only creases and rounding go onto the meshes. The hull's smoothing keeps
  about a third of a pressed crease.

### Gaps between parts (Nov 9): why, and the guard that stops them shipping
- Causes found: (1) to kill lumps I removed the frame 3 cm past each arm box, leaving a 3 cm channel; (2) each
  part is a rounded hull inside its box, so where two boxes only touch, the rounded surfaces leave
  15-30 mm crevices (back cushions stood 57-62 mm clear of the frame); (3) the frame was cut slightly
  larger than the parts.
- Fix (propkit/hull_assembly.py): contacts are found from the boxes; on every touching face the built
  surface is measured (median of the surface facing that way, away from rounded edges) and stretched to
  the neighbour's plane plus OVERLAP (1.5 cm) so neighbours interpenetrate; parts resting on the frame
  are fitted to the frame's real surface (ray cast), not its box; the frame is cut smaller than the parts.
- Guard: after every build the gap check samples each contact face (and every part on the frame) and the
  build FAILS if the 90th-percentile gap exceeds 4 mm. Proven both ways: with fitting disabled
  (HULLASM_NOFIT=1) it flags 8-12 mm gaps; with the fix all 24 contact faces measure 0 mm.
- Blender: after moving objects, call view_layer.update() before reading matrix_world, or every
  measurement uses stale positions (the check briefly reported 581 mm "gaps").

## Appliances from a parts sheet: the "attached" layout (coffee machine, Nov 9)
- A body (housing) with parts hung on it or standing in it doesn't fit the sofa rules. The order says
  `"layout": "attached", "body": "<folder>", "attached": [<folders>], "skip": {folder: why}`. A row can
  hold several parts: `--rows "assembly:front,right;carafe:front,top"` (views left to right).
- Parts are found in the whole-object front/side views by colour (histogram of the part's own views
  against the body's), largest component, 2-98 percentile box. A part's bottom edge is reliable; its top
  is trusted only if the views agree within 3% of the height (a dark carafe merges with the dark filter
  holder above it), otherwise its own proportions decide.
- The body's own drawing can conflict with the assembly (a solid arm where the basket hangs): the body
  hull is hollowed by the parts' exact shapes, so the assembled drawing wins.
- **Gaps again, the same mistake in a new form**: the first seat check measured from the part's BOX and
  only in the direction it snapped (back, against the column), so a carafe 9 mm above the base passed.
  Now: measure from the part's real vertices facing each way; gravity first (body under a part = it
  stands on it), then hanging, then mounted; and a seated part needs 40% of its facing surface within
  4 mm (a few sunk vertices are not contact). Proven both ways: HULLASM_NOGRAVITY=1 (the old snap) fails
  with "touching 0.05"; the fixed build touches 60% underneath, 0 mm. Feet are now checked too.
- Any check that passes must be shown to fail on the broken case before trusting it.

## Round parts are lathe shapes (Nov 9)
- Intersecting front and side outlines makes every horizontal slice a rectangle, so a carafe came out
  with flat sides and shoulders. Jared's rule: look at the top view; if the main body is round, it is a
  vase/lathe shape. `propkit/revolve.py`, on by default in hull_prop: the top view's thin appendages
  (handle, spout: pieces that stick out more than 0.6x the width where they join) are set aside, the rest
  must match its fitted ellipse (IoU >= 0.96, axis-aligned); then each slice is an ellipse with the radius
  from the axis to the NEARER edge in the front and side outlines (a handle drawn joined to the body only
  widens its own side). Appendages keep their hull; where the body narrows, a wedge in the handle's
  direction keeps the handle joined. Nothing ever goes outside the plain hull.
- Calibration (top views): circle/ellipse/carafe/lid 0.99+; square 0.83, squircle 0.90, chamfered housing
  0.89, sofa parts 0.89-0.91, TVs 0.90. An opening alone shaves a box's corners and made the housing look
  round (0.95): put shallow wide slivers back before testing. Pad tight-cropped masks before a distance
  transform (the basket's mask touched the crop edge and the transform found no background).

## Car from a views sheet in ~15 minutes (sedan, Nov 9): the fast path
- Sheet: Drive "exteriors/vehicles/Classic Sedan Parts and Views Sheet.png" (four orthographic views,
  a top view, perspectives, then loose panels/wheels/lights). Only the orthographic views are needed;
  the loose parts are already painted on the body views.
- Steps that worked first time:
  1. Crop each band you need at FULL sheet width (a narrow crop cut the fourth view in half), then
     `split_parts_sheet.py` with one row per band; keep only the v_*.png files, delete its order.
  2. Side views: the hull's right view has the FRONT ON THE LEFT, its left view the front on the right.
     Decide which end is the front from the drawing (hood longer than trunk; headlights), not from the
     sheet order: this sheet's second side view was already a correct left view, and "fixing" it by
     mirroring was wrong. Top view: turn it so the front is at the bottom.
  3. Check proportions agree before building: front W/H, side L/H and top W/L must give the same
     object (here 1.45, 3.45, 0.43: consistent). Then fix ONE real dimension (width 1.95 m for a 70s
     mid-size) and let the views give the rest. Never stretch a view: wheels go oval.
  4. Order: line `hull`, `"hull": {"width_m": ..., "res": 220, "paint": "project", "blur": 1.6,
     "smooth_iters": 10}`, class `vehicle`.
- `"paint": "project"` (blended views, as hull_parts) is the default to use for new hull orders: the
  old per-face nearest-view paint streaks every slanted face (windscreens, hoods).
- Big gently sloped bodies need `blur` ~1.6 and more smoothing: a 4.6 m object at 220 voxels has 2 cm
  steps, and each riser faces a view and takes a stripe of its paint (grille colours across the hood).
  The streaks were geometry, not paint.
- Wheels need nothing special: the side view's circle times the front view's corner blocks is a cylinder.

## Geometry audit (Nov 9): ridges were pixel staircases; how to diagnose next time
- Diagnose before fixing: `tools/diag/render_modes.py NAME OUT` (textured, clay, wire, albedo, normals,
  facets, depth with identical cameras) and `tools/diag/metrics.py GLB VIEWS` (silhouette IoU, ridge
  energy, folds/1k). A defect in clay/normals but not albedo is geometry; in albedo but not clay is paint.
- Rule out stages by rendering the intermediate: the dense mesh before decimation had the hood ridges,
  so decimation was not the cause (it was suspected first).
- Measure the field, don't guess: reading the surface height from the reconstruction field along the hood
  showed 1-pixel (12 mm) steps -> the side view's outline staircase.
- What did NOT remove pixel staircases: blurring the distance 1 px (treads survive), Douglas-Peucker
  (puts vertices on the stair corners), rasterising a fitted curve 4x finer (quarter-pixel stairs),
  taking the sign from that raster (the zero crossing snaps to it). What did: smooth the contour along
  its length between real corners, then measure the exact distance to the curve with its own sign.
- Carving on voxels + continuous field: never use a removed sliver's distance (noise where it is a voxel
  thin; 1,691 folds on the carafe). Use the carved solid's own distance near the carve.
- Metrics can pass a broken mesh: the first fitted build passed silhouette and ridge checks while the
  sofa and coffee machine were full of folds; only renders showed it. Folds/1k now catches it. Exported
  GLBs split vertices at UV seams: weld before measuring adjacency.
- Tests: `tools/test_hull_geometry.py` (9 s) and `tools/diag/regress_assets.py` (5 min, car + coffee +
  sofa fixture against factory/geometry_baseline.json). Run both after touching propkit/hull.py.

## Wall phone (Nov 9): parts painted like the body, found by subtraction
- Drive "appliances/wallphone.png": whole phone in 6 views + body shell, handset, dial, hooks, caps, cord.
  Order: layout `attached`, body `body`, attached `[handset]`, `body_width_m` 0.14 (the one real size;
  the rest from the drawing), `mount` `wall`. ~45 s per build.
- Everything is one harvest gold, so colour can't find the handset (colour overlap 0.80 vs 0.12-0.21 for
  the coffee machine's parts). `SAME_PAINT` switches to subtraction: the body's own outline is fitted
  into each whole-object view (FFT correlation over scale; placements fully inside tie, so the body's
  edges must also land on the whole outline's edges) and what it doesn't explain is the part.
- A part's edge pressed against the fitted body is hidden in that view (the cups in front of the body's
  edge): every box edge comes from a view where it is visible, the bottom is the highest visible bottom
  (a cord hanging below only adds), hidden extents from the part's own view proportions.
- Seating: a C-shaped handset touches with its cups; the touching share is now measured over the near
  layer (facing surface within 10 mm of the closest approach). The floating-carafe negative test still
  fails (touching 0.08). Parts can also seat sideways (left/right), after down and up.
- Top views drawn with the front face showing are not plans: carving with one set the phone's face back
  18 mm everywhere except where its hooks were drawn (two ribs down the face). A top view now carves only
  if its proportions agree with the front/side views within 15% and it matched the whole-object top
  clearly; otherwise it only paints. Found by measuring the front surface depth across the width.
- Background seen through a hole (the gap inside the handset's loop) was filled into the outline and
  painted black onto the body. split_parts_sheet now writes h_<view>.png for background-coloured filled
  holes; painting fills them from the object's colours (carving still treats them as solid).
- Godot's .import sidecars sit beside every PNG once the editor has imported a folder: filter listings on
  the extension (a g_*.png.import broke the sofa build; the asset regression caught it).
- Wall props: `"mount": "wall"` puts the back on the wall plane y = 0 (fronts face -Y) like the hand-built
  wall props.

## Parts sheets are manufactured, not moulded (wall phone v2, Nov 9)
- Jared: "you aren't manufacturing the parts separately and then assembling them like the photo shows;
  that's why each part has a view. You're doing a full mould." Layout `parts` (propkit/parts_layout.py):
  every part on the sheet is built from its own views and painted from them, then placed and seated.
  The order is the construction plan, one entry per part, each with how it is located and what it
  attaches to (face, and "at" for an end). One part can be used twice (the cap: earpiece + mouthpiece).
- How to locate, from most to least reliable on these sheets: residual (sticks out of the body's outline),
  protrusion (drawn as part of the parent's own outline, like cradle hooks on the shell), attach by rule
  (back plate on the back, caps at the handset's two ends), match (a big distinctive part lying on the
  body: masked NCC, holes excluded, blur scaled with size; found the dial face), concentric (centred on
  the parent; size from the sheet's drawing scale: low confidence), leftover (what no part explains:
  the cord, swept as a tube along its centreline when it is long and thin).
- What did NOT work for locating: plain NCC (tiny scales win by chance), edges NCC, radial edge profiles
  (locked onto the dial's centre label), dark-spot rings (numbers count as spots). Check a locator by
  drawing its result on the photo before trusting a score.
- Round FRONT views make a lathe about the front-to-back axis (dial, caps); round TOP views about the
  vertical (carafe). Background seen through a part's own view (h_ mask) is an opening along that view:
  cut through (hook frame, finger holes).
- The body is painted from the photo with the parts occluding it: through the finger wheel you see the
  number card the photo shows, not the bare shell's drawn hole.
- Thin plates (5-8 mm) decimated into a 6000-triangle budget fold at their rims (folds/1k 25-49 on the
  dial and hooks): a size-class budget is shared by all parts; the regression baseline records it.

## Wall phone rebuilt from scratch with the parts process: 36 minutes, of which the build was ~2.5 (Nov 9)
- Timed from the Drive file to a verified render: download + new blob tool + listing 0:44; part views
  cropped and the plan written 1:22; first build shipped 2:23 (factory 61 s); renders 4:28 showed dark
  streaks on the handset, caps and cord; diagnosis and fixes until 36:23. Final factory build 35 s.
- tools/sheet_blobs.py: `list` numbers every drawing on a sheet (labels and rules left out) and writes an
  overlay; `crop` takes a JSON spec {part: {view: number}} and writes v_/h_ files. No hand-measured
  boxes. Keep the merge distance small (3 px): neighbouring views can sit 5 px apart.
- The streaks: one invalid part mesh (the hook frame: a thin plate with holes, decimated hard) made the
  glTF exporter misalign its arrays, so every part written AFTER it got garbled normals. Found by
  bisecting: renders (albedo clean, clay streaked) -> geometry before bake clean -> raw GLB normals bad
  -> per-part exports clean -> exporter warning "Mesh ... is not valid". bake.finish now runs
  mesh.validate() on every part before joining, and qa checks the written GLB's normals against its
  triangle winding (fails above 1%). Things that were NOT it (tried, reverted): decimating after paint,
  colour attributes in the export, stale normal caches, normal recalculation on the joined mesh.
- Parts layout: the triangle budget is shared by each part's dense triangle count (its detail), with a
  floor of 300, and each part is decimated BEFORE it is painted. Sharing by area starved the finger wheel
  (206 triangles for eleven holes) and it shattered.
- Read the turnaround before reporting: a build that ships and passes the gap checks can still look wrong.

## The reference handbook ("golden disc"), cords, and screen-error budgets (Nov 9)
- (Superseded the same day; see "Human scale" below.) The first handbook held product sizes looked up on
  the web, each with a source. Jared rejected it: a handset of any make is sized to a head, so nothing
  needs looking up.
- Cords (propkit/cord.py): built straight first (a tube, or for a coiled cord a helix with the handbook's
  coil diameter and pitch), then curled along the path the photo shows, then swept as a tube of the
  wire's thickness. The same three steps make lamp flex, hoses, springs and rope; only the numbers change.
  Coloured from the photo's coil pixels (not the dark gaps between them).
- Triangle budgets the way studios set them (factory/standards.json "screen_error_budget"): a part may be
  simplified until its surface moves 1 px at the kind's near viewing distance (fixture 0.6 m: 0.78 mm),
  measured both ways at the 99th percentile; the size class's budget stays a ceiling. The phone went from
  5700 to 3650 triangles with every part within tolerance. Godot 4 makes LODs on import.
- Low-poly meshes broke projection painting: view weights were per vertex from the smoothed normal, so a
  big back face spanned by box-corner vertices took the front photo (a mirrored dial on the back).
  texturing.project now weighs corners by their own face where the face turns >30 degrees from the vertex
  normal; dense smooth meshes are unchanged (the coffee machine's paint is identical).
- A part on its parent's back face is turned 180 degrees so its drawn front faces out (as side parts are
  turned 90), and it sits behind the parent's box (the box is the bare shell), not inside it.
- Restore point: factory/RESTORE_POINTS.md.

## Human scale: the golden record (Nov 9)
- Sizes are never looked up. factory/human_scale.json is one table of the adult body (5th/50th/95th
  percentile: ear to mouth, fingertip, grip, knee height, seat depth, shoulder breadth, sitting height ...).
  The reference handbook says, per object type, how the object meets the body ("contacts": a handset spans
  ear to mouth, a finger goes into a dial hole, an earpiece covers the ear, a seat is at knee height) and
  what its parts are finished in. It holds no product sizes (tools/test_human_scale.py enforces it).
- The drawing gives every proportion. propkit/human_scale.py turns each contact measured in the drawing into
  the range of scales it allows (body range x fit range), picks the largest group of contacts whose ranges
  overlap (ties: the group with the first-listed contact), and takes the geometric mean of their typical
  scales inside that overlap. A contact outside the group means the drawing is out of proportion there; the
  build report says which and by how much. Drawing units cancel out: pixels or "body widths" give the same
  metres.
- parts_layout now locates every part first (in drawing units, body width = 1), measures the contacts,
  solves the scale, then builds. An order that gives body_width_m still builds at that size (fixtures do).
- The phone: handset 195 mm and earpiece 57 mm agree (spread 1.08), body 150 mm. The finger holes
  are drawn at about half fingertip size (off by 2.04) and are outvoted, not obeyed. A painted parts sheet
  is not drawn to one scale: the cap is drawn wider than the handset. Size a part from where it sits in
  the assembly (a cap = its handset's depth), never by transferring the sheet's drawing scale between parts.
- Measure what a person touches. On a mesh the seat is the up-facing level open to the sky with the most
  area; the biggest flat level of the sofa was the platform hidden under the cushions (320 mm vs 478 mm).
- Cord thickness: the drawn width, if it falls in the body's range for a cord (a finger's thickness);
  otherwise the typical value, not the edge of the range. The phone's drawn cord measured 34 mm, which is
  merged loops, not one cord: 12.5 mm coil, 4.1 mm wire.
- tools/diag/scale_audit.py checks built props the same way: car x0.99, sofa x0.97 (both already
  people-sized; nothing changed).

## Carved table leg: silhouettes get the form, not the carving (Nov 9)
- Drive furniture/leg.png: four elevations, a top view, two close-ups (detail references, not views).
  The elevations agree with each other (front/back 1.45x wider than the sides) but the top view is drawn
  square: the elevations win (they share one scale), the top is stretched to them.
- The hull line can now take its size from human scale too (factory.py human_scale_height): an order with
  `"handbook"` and no `height_m`. Table leg: the top sits at a seated person's elbows (1.5-1.72 knee
  heights) -> 690 mm. One contact only, so the report states the assumption (dining/writing table).
- Result: outline exact (IoU 0.92-1.0: taper, bead band, bun foot, block), but the clay render shows no
  fluting and no leaf relief: those lie inside the outline and are only painted. This is the relief problem:
  it needs the 2.5D relief step (height over the surface from annotated regions), not more silhouettes.
- Relief from the painting (propkit/relief.py, opt-in: an order's `"hull": {"relief": true}`). Darkness in a
  painting is either occlusion (creases, grooves: depth) or a surface turned from the light (slope).
  Cavity (darker than the neighbourhood) finds the creases; a watershed of the cavity splits the view into
  regions (neighbours across a weak line merged); a region counts as carved only if creases surround it and
  a dome or dish explains its shading; raised or sunk by two votes (its shading against the dome's slopes
  under one light shared by all views, and which side of its edge the shadow falls); creases become
  V-grooves. The dense relief is baked into the normal map (bake.finish bakes "<name>__high" onto the
  simplified mesh): at 25k triangles a 0.7 m leg has ~5 mm triangles, too coarse for 3-5 mm carving.
- Inverting a painting does not reveal depth: it gets grooves right (occlusion) and bumps wrong (the lit
  side of a bead becomes "deep"). Integrating the shading along the light gave mush (painted light is not
  consistent enough).
- Table leg result: beads come out raised and real; leaf outlines read as carved lines; flute tops sink.
  But the leaves are lumpy rather than cleanly modelled, and most of the flutes' length is lost (their
  side creases are too weak on the lit side to bound them). Shading check: 0.16-0.18 correlation with the
  painting (all-raised: about 0; grooves only: about 0). A companion relief sheet (regions by colour) would
  replace the guessing in steps 1-3 and keep steps 4-5.

## Removable construction guides (Nov 9)
- Drive furniture/updatedleg.png: the leg with cyan guides and a legend (surface curvature, side profile,
  cross-section rings = "maintain round/oval", centre line), plus a bottom view. propkit/guides.py reads
  them and paints them out: `clean` moves guide pixels to g_<view>.png and fills them from the
  surrounding paint. Guide colour = much bluer than red; warm paint never leans blue, so faint strokes and
  the anti-aliased fringe go too (a strict colour test alone left pale traces).
- Cross-section rings: horizontal guide strokes across at least 30% of the object's width. One drawn
  ellipse shows as two arcs; arcs close together are one ring. The round band is the widest band at least
  two views agree on (one stray stroke cannot widen it; a side view that draws no low ring cannot shorten
  it). The hull's slices in that band become the ellipse inscribed in each slice's own extent.
- Leg: square block and carved top as before; shaft and foot now round (cross-sections show it); no guide
  on the model. The sheet's labels put the LEFT side second: read the labels, never assume an order.

## Cross-sections inferred from the painting, no guide lines (Nov 9)
- propkit/sections.py: at every height the silhouettes give the half width and half depth; the section is
  a superellipse |x/a|^n + |y/b|^n = 1 (n 2 ellipse, 4-6 rounded box, large: box), so one number per height
  band is unknown. Analysis by synthesis: each candidate n predicts the brightness across the width under
  some light; the best n that beats the box by a margin, in several views, wins. Opt-in: hull
  `"sections": true`; HULL_SECTIONS=1 turns it on everywhere for A/B tests. Overlays and JSON go to
  docs/inference/<name>/.
- What decides, in order: (1) the widest part near an end is what that end view draws: its section is the
  end view's shape, and with no end view there is no claim; (2) carved bands (creases running every way,
  not just along or around the axis) shade like curvature, so only the end view counts; (3) otherwise the
  shading test.
- Graded against the guided sheet's rings (the answer key): 0.91 overlap on the guided sheet's own views
  with the guides painted out and unused; 0.71 on the first sheet (no bottom view, so the foot stays
  square: no evidence). The front-lit painting made the carved capital shade exactly like a cylinder:
  without the carving and end-view rules it came out round.
- On by default it is NOT safe yet (five-object test): coffee maker worse (its housing's painterly
  gradients pass as curvature), sofa and phone slightly ridgier, car unchanged. First run, cushions became
  ellipses and the gap check failed the sofa (13-39 mm gaps): touching faces must stay flat.
- Follow-up (same day): flat things must stay flat. Two rules fixed every false rounding in the
  five-object test: (a) a second witness for shading: a shading-decided run must also have front width
  and side depth swelling or tapering together (a turned or moulded outline); a straight-sided box stays
  a box; (b) a run touching the object's top or bottom is what that end view draws: the end view decides.
  With them on for every object the asset regression passes (car, coffee, sofa, phone unchanged) and the
  leg still matches the guided rings at 0.90: sections are now on by default.
- The foot's dents were the relief step, not the sections: compact leaves judged "sunk". Carved recesses
  are channels, so only regions at least 3x longer than wide may sink; compact ones rise or stay flat.
- Builds were not reproducible run to run: Python's per-run string hashing changes set iteration order
  (part joins, decimation), so metrics wobbled (coffee folds 0.35-1.05, IoU 0.912-0.915) with no code
  change. regress_assets.py pins PYTHONHASHSEED=0. The factory itself still varies; worth fixing at source.

## Second TV from a rich reference sheet (Nov 9)
- The sheet had views, a "main assembly (no screen)", the CRT drawn alone, dimensions and section drawings.
  A plain hull from the views came out right in size and paint but flat-fronted: no screen recess, no
  glass. Built from parts instead: the cabinet from its no-screen views, the CRT set into the opening.
- New, general, in the parts layout: (1) a body spec's "recess": openings drawn in the body's own front
  view (background through it) are recessed RECESS_SHARE (12%) of its depth from one plane per opening;
  only openings of 2%+ of the front (knob holes stay painted); nearly convex openings take their convex
  outline. (2) locate "inset": the part goes into its parent's largest opening, 4% oversize so its rim
  hides, face 3% of the depth behind the front; held by the opening, not gravity-seated. Matching the CRT's
  painting into the photo had locked onto the wrong spot at 1/6 scale: the opening is the evidence.
  (3) a body filling 90%+ of the front both ways is the object's envelope: as deep as the object (the
  no-screen side views were drawn thin, 133 mm vs 280). (4) "sheet_dims_mm": the sheet's printed size wins
  over drawn proportions (side views implied 190 mm deep; printed 280).
- The wavy dark line inside the screen recess is the rim's shadow on the glass (light from upper left),
  not geometry: two "fixes" to the recess changed nothing before that was clear. Check the light first.

## Reconcile: making a contradictory sheet agree (Nov 9)
- propkit/reconcile.py, opt-in per hull order ("reconcile": true; report in docs/inference/<name>/).
  Measures every view's proportions on the object's core (feet, knobs, cables left out), decides the size
  (printed dimensions first, else the largest agreeing group), stretches disagreeing views to it, flips a
  side view drawn mirrored (it matches the top view's depth profile only when flipped: 0.81 vs 0.15 on the
  second TV sheet), makes top/bottom views paint-only when their proportions disagree, and crops one-sided
  protrusions: knobs seen in one side view only were stretched by the hull into bars across the whole
  front. Compare each view's band past its own core, not positions: cores differ in width.
- On that sheet depth was three-way contradictory (sides 0.58 x height, print 0.78, top ~1.1): the print
  is also the middle value.
- False holes: the hole finder marks painted areas near the sheet's background colour (black bezel,
  control panel plastic) as see-through, and paint_views repainted them from neighbours: that smeared the
  first new TV's frame ("jagged"). A see-through hole must also show from the opposite view (mirrored);
  with no opposite view the old behaviour stays (hull_assembly.confirmed_holes).
## Continuous reconstruction and detail checks (Nov 11)

- The active experiment solves continuous height/gradient fields from shading.
  Circle detection and fixed dome/channel templates were rejected and removed.
  Brightness is not height: material colour, illumination and cast shadows can
  imitate relief. A successful image fit alone does not prove metric geometry.
- Do not use validation probes to manufacture local point dents. Validate the
  continuous solution independently. Unmet dense-fit constraints stay QA failures
  but must not lock the simplifier at source-grid density.
- Protect thin cores and check solid connectivity when combining view corrections:
  independent recesses can cut through the same support from opposite sides.
- A computational curvature region is not a physical component. Independent caps
  create visible joints; share one implicit surface unless physical separation has evidence.
- Cell-centred signed fields need metric ghost cells. Arbitrary positive padding
  moves the zero crossing and can flatten shallow crowns at the sampling box.
- Checking a bead only at its centre admits pyramids. Check several angular and
  radial crown/rim contrasts on the exported mesh, without textures or normal maps.
- Keep small features with local contrast bounds and sampling uncertainty, rather
  than demanding micrometre absolute positions across an entire dense source grid.
- Blender decimation weights of exactly zero lock edges. Soft protection must
  remain nonzero after inversion; its influence also needs physical scale.
- Preserve native physical IDs through export. Matching tiny triangle centroids
  is fragile when exporter triangulation or normal splits change.
- QA feature frames must include floor/wall seating translations. Check each part
  against its own geometry so another assembled part cannot intercept its rays.
- Withhold validation/test intensities before building any image pyramid. A coarse
  initialization can otherwise leak the very pixels used to judge the final fit.
- Unknown lighting/material makes inferred groove depth conditional. Keep its QA
  evidence, but do not freeze dense meshes to unsupported sub-voxel depth targets.
- Kernel-valid STEP faces are not watertight CAD solids. Read back the exchange
  file and verify units/trim holes; sewing and assembly frames need separate checks.
- A class-independent identity graph does not automatically replace a role-based
  manufacturing grammar. Record which downstream stages actually consume it.
- Trace internal boundaries before relief fitting, but keep segmentation separate
  from depth truth. Painted facets and shadows can form closed regions too.
- Boundary extraction must use training-only intensities to preserve holdout
  isolation. Export integer masks and declare pixel frames; contour coordinates
  need the padding offset removed in pixel-centre convention.
- Weak-edge union can bypass a strong crease through a third region. Protect
  strong adjacency during merging rather than trusting pairwise weak edges alone.
- Original relief already contained weak-crease merging. Share that machinery;
  do not describe a missing call in the active path as absence from the codebase.
- Equal occupied voxel signs do not guarantee equal interpolated surfaces.
  Check zero-crossing drift before adopting sampled Boolean recomposition.
- Reserve separate local-acceptance pixels so regional hypothesis selection
  cannot consume the final test pixels used to judge the full surface.
