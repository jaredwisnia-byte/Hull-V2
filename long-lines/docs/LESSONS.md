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
