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
