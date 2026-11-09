# Lessons learned

Mistakes made on this project and the rule that prevents each one. Read before working;
add to it whenever something goes wrong.

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
