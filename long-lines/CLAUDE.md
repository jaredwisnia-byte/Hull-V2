# Long Lines: working notes for Claude

Read this first. It is the handoff between sessions.

## The project
- Story-driven survival game: lower Manhattan after a comet strike, Oct 31 1975.
- Design doc (owner: Jared): Claude Docs artifact https://claude.ai/artifact/AVAcC1buutbPDkVeQBtNZK
  ("Long Lines: Game Design Document"). Read it with the Claude Docs connector.
- Art direction: The Long Dark style (chunky, bevelled, painted wear, warm lights against
  teal shadows) applied to 1970s New York tenement interiors. Jared approved the TV prop
  (`docs/props/`) as "exactly what I wanted": that is the fidelity bar for every prop.
- Current milestone: the apartment vertical slice (Nick's flat, 4A Sullivan St).

## Doctrine: interchangeable parts
Build once, reuse everywhere. Do not hand-code one-off geometry in game code.
- **Props** are Blender recipes in `tools/props/*.py` built with the shared kit
  `tools/propkit/`. `tools/build_props.py` builds, bakes and exports them to
  `assets/props/<name>/` and records each one in `assets/props/library.json`.
- **Godot loads props by name**: `PropLibrary` / `PropFactory` (`scripts/world/`).
  A scene places a library prop with `{"type": "lib", "prop": "<name>", "kind": ...}`
  in its layout JSON. Kinds: static, fixture, carry, container, readable.
- **Rooms and walls** come from data (`data/apartment.json`) through
  `ApartmentBuilder`. New buildings should reuse the builder with new JSON.
- **Simulation** lives in pure classes (`scripts/sim/`), tuned by `data/*.json`.
- Real brands, trademarks and real people's words are never used; invent period names.

## Reuse first
- Shared parts: `tools/propkit/parts.py` (wheel, sheet_box, rolled_rim, rails). Check here
  before modelling anything a second time.
- Painted sheets: `tools/prepare_sheet.py IMAGE LAYOUT NAME` with layouts in `tools/layouts/`
  (car_v1, range_v1, wallpaper_v1). A new sheet with a known layout needs no new code: cars
  are one line in `CARS` (`tools/props/cars_painted.py`), cans one line in `goods_painted.py`.
- Wall materials: any tiling image becomes a wall finish via a palette entry with pattern 13
  in `scripts/world/geo.gd`; the shader layers grime, cracks, peeling and stains on top.
- **Read `docs/LESSONS.md`** before starting; add to it when something goes wrong.

## How to work here
- Godot binary: download Godot 4.4.1 (Linux x86_64) from GitHub releases into the
  scratchpad. First run on a checkout: `godot --headless --path long-lines --import`.
- Tests: `godot --headless --path long-lines --script res://tests/run_tests.gd`
  and `godot --headless --path long-lines -- --smoke`. Both must pass before pushing.
- Screenshots (needs Vulkan): `apt-get install mesa-vulkan-drivers`, then
  `xvfb-run -a -s "-screen 0 1280x720x24" godot --path long-lines -- --shots=DIR [--only=PREFIX]`.
- Blender: `apt-get install blender python3-numpy` (4.0 works). Cycles bakes come out
  black unless denoising is off; the kit handles it.
  Build props: `blender -b --factory-startup -P long-lines/tools/build_props.py -- <names|all>`.
  Contact sheet of built props: `tools/contact_sheet.py` (same invocation style).
- Look at every visual change in a rendered screenshot before calling it done.
- Commit and push after each step (branch named in the session prompt).

## Status and next steps
See `docs/STATUS.md`.
