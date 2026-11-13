# Hull factory: working notes for Claude

Read the root `AGENTS.md` first (current priority and how to judge a change). This file is
the factory's handoff between sessions.

## The product
- Jared's directive: industrialize asset production. The factory is the product.
- Input: painted reference sheets (1970s New York objects, hand-painted survival-game style:
  chunky, bevelled, painted wear). Output: textured, correctly sized props in
  `assets/props/` as engine-neutral GLBs.
- Jared approved the TV prop (`docs/props/`) as "exactly what I wanted": that is the
  fidelity bar for every prop.
- Jared does not want to spend money: no paid image-to-3D services.
- Real brands, trademarks and real people's words are never used; invent period names.

## The factory (start here for any new asset)
`factory/README.md` is the manual: work orders, production lines, the quality gate at a
**minimum acceptable standard** (one automatic correction, then flag, never polish),
standards (`factory/standards.json`, `categories.json`), the input spec
(`factory/REFERENCE_SPEC.md`), the ledger and KPIs (`factory/REPORT.md`).
`blender -b --factory-startup -P long-lines/tools/factory.py -- intake|intake_sheet|build|qa|report ...`
**The assembly line:** `python long-lines/tools/line.py --drawn` (or order names) runs each order through
intake (views cut from its sheet, guide lines removed) -> build + quality gate -> final renders
(`docs/renders/NAME.png`, contact sheet `docs/renders/line.png`, run log `docs/renders/LINE.md`).
Orders marked `"locked"` (approved assets, e.g. the TV) are rendered, never rebuilt.
Lines: hull (multiview sheets), hull_parts (parts sheets), sheetset, atlas (appliance part
atlases), extrude (trim sheets: mouldings and casings), facade (building elevations), car,
can, surface, recipe. Sheets that hold many assets get a sheet spec (`factory/sheets_*.json`,
label panels with `tools/label_panels.py`) and go through `intake_sheet`.

## Doctrine: interchangeable parts
Build once, reuse everywhere.
- **Props** are Blender recipes in `tools/props/*.py` built with the shared kit
  `tools/propkit/`. `tools/build_props.py` builds, bakes and exports them to
  `assets/props/<name>/` and records each one in `assets/props/library.json`.
- **Shared parts**: `tools/propkit/parts.py` (wheel, sheet_box, rolled_rim, rails). Check here
  before modelling anything a second time. Change shared parts rather than patching recipes.

## Reuse first
- Painted sheets: `tools/prepare_sheet.py IMAGE LAYOUT NAME` with layouts in `tools/layouts/`
  (car_v1, range_v1, wallpaper_v1). A new sheet with a known layout needs no new code: cars
  are one line in `CARS` (`tools/props/cars_painted.py`), cans one line in `goods_painted.py`.
- Surfaces: `tools/make_tiles.py tools/tile_specs/<batch>.json` turns painted images into
  seamless tiles in `assets/surfaces/` and registers them in `data/surfaces.json`. Recipes use
  them through `mats.painted(name)`; the facade line uses the `ext_*` walls.
- Visual hull: `tools/propkit/hull.py` builds a textured prop from orthographic painted views
  (front/right/left/back/top). Views live in `assets/source_textures/<folder>/v_<view>.png`.
- What a hull can build: anything that shows in some view's outline (a camera's bellows
  pleats, a TV's bezel step). What it cannot: detail that exists only as painted shading
  inside the outline (carving); that belongs in the texture and normal map.
- **Critique every prop** with `tools/critique.py` (turnaround + automatic checks) and
  follow `docs/CRITIQUE.md`. Part knowledge (how far knobs stick out, etc.) lives in
  `tools/propkit/part_rules.py`.
- **Sizes come from `factory/sizing_manual.json`** (read `factory/SIZING.md`): facts, part
  formulas, placement rules, object envelopes. Fix a wrong size there, not in code.
- **Read `docs/LESSONS.md`** before starting; add to it when something goes wrong.

## How to work here
- Jared has Blender 5.2 on his own Windows PC. To inspect a library prop with its textures:
  `blender --python long-lines/tools/open_in_blender.py -- <name>` (library GLBs carry placeholder
  materials; the maps are separate PNGs).
- Setup: Python 3.13 with `requirements-core.txt`; `python hull.py doctor`, then
  `python hull.py check` (see the root README). In a cloud container without a Blender
  download, `pip install bpy==5.2.3` provides the same Blender as a Python module.
- Look at every visual change in a rendered turnaround before calling it done.
- Commit and push after each step (branch named in the session prompt).

## Status and next steps
See `docs/STATUS.md`.
