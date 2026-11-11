# Hull knowledge file

Last audited: 2026-11-10. Read this before proposing a new reconstruction module.
Update it when verified behaviour, inputs, call paths or test results change.

## Purpose and evidence level

The priority is reusable software that accepts supported inputs and executes without
an LLM operating it. An assistant may help develop the software; it must not silently
supply per-object masks, crops, placements, dimensions or scripts and call that an
autonomous run. Find existing machinery before implementing another version.

This file combines a full tracked-text inventory, Python AST inspection, source
reads of the principal engines/dispatchers, and previously observed trials.
It is not a claim that every algorithm or asset was executed or proven correct.
Binary textures/GLBs were counted, not exhaustively visually audited.

The accompanying [machine-readable inventory](long-lines/docs/CODEBASE_INVENTORY.json)
records 391 source/configuration/documentation files, all 82 tracked Python files,
36 Godot scripts, module descriptions, definitions/line numbers, imports, static
calls, JSON shapes, documentation headings and content hashes. All Python files
parsed successfully; JSON parsing found no errors. Static calls are not a resolved
runtime call graph. Inventory counts describe the pre-knowledge-file snapshot;
the new knowledge documents themselves are additional files.

## Current implementation update (2026-11-10)

The implemented cleanup is documented in
[IMPLEMENTATION_PLAN.md](long-lines/factory/IMPLEMENTATION_PLAN.md).
New shared modules are pipeline.py (orchestration/failure reports), preflight.py
(non-destructive reconciliation proposals), simplification.py (shared adaptive
reduction and normal refresh), sectioning.py (arbitrary plane contours and
hole-aware hatching) and cutaway.py (non-destructive clipped surface export).
Single-body automatic-depth projected builds now simplify before painting.
Local relief regions replace the failed whole-view selector; dense single-body
relief is retained for normal baking. Automatic-depth QA uses unfiltered outlines,
144-pixel width and available bottom references. Legacy route defaults remain.
The restricted intake grammar, camera/shape optimizer and automatic construction
region decomposition remain unresolved as listed in the plan.

The updated leg trial has 1,302 triangles, zero normal disagreement, and 58 locally
accepted candidate regions. The stricter raw top-view test rejects the blender
reference despite its former filtered pass. These are limited acceptance cases,
not universal reconstruction quality guarantees.

Regenerate the inventory with:
python long-lines/tools/audit_inventory.py
It parses source without importing builders and excludes its generated JSON output.

## Repository identity and boundaries

- This repository contains **two products**: root Midnight Watch (static web app and
  RSS/push collector), and Long Lines (Godot game plus the Blender asset factory).
  Hull is the reconstruction/factory toolchain inside Long Lines, not a standalone
  root Python package.
- User-designated original is jaredwisnia-byte/claude, branch
  claude/trusting-dirac-bxfmv6, commit
  9d8df082dfbef7d5a508be3578d78d7c488561ab. Keep it untouched.
- Current development is Hull-V2, feature/automatic-sheet-intake. Local and GitHub
  commit histories differ because commits were published through the connector.
  Do not force-reset or overwrite either history merely to reconcile their IDs.
- Audited local source HEAD before this documentation: b54cc377f4e85e107fedc03952507684cdfdc95b.
  Latest previously published GitHub source head: 159256b09675d6219a93e1a2f2fb3633a4d9e9e1.
- The user abandoned another Factory V1/branch direction. Preserve the chosen Dirac
  ancestry. The word “factory” still appears throughout canonical Dirac code/docs;
  a filename containing factory is not by itself proof it is the abandoned code.
- Other remote branches were not exhaustively audited. Historical benchmark scripts
  are not active production dispatchers.
- Follow root CLAUDE.md, long-lines/CLAUDE.md, factory/README.md, VALIDATION.md,
  SIZING.md and docs/LESSONS.md. Historical STATUS/REPORT pass counts are dated
  records, not current quality certification.

## High-level data flow and entry points

tools/factory.py: intake, intake_sheet, intake_set, build, qa, report, and optional
auto. Work orders live in factory/orders; generated assets and library.json in
assets/props; measurements append to factory/ledger.jsonl.

tools/line.py: multi-order station runner: crop/intake, guide cleaning, build/gate,
render, report/contact sheet. Locked orders render without rebuilding.
It launches Blender workers and relies on a discoverable blender executable.

tools/build_props.py: recipe library build/bake/export.
tools/prepare_sheet.py: layout-based crops, separate from automatic recognition.
tools/split_parts_sheet.py: conventional parts-sheet splitting and order writing.
tools/sheet_blobs.py list/crop: detection plus supplied specification.
Its auto command adds local OCR/correspondence for a restricted input grammar.
tools/make_manifest.py: helps assemble a v2 sheet-set manifest from supplied
paint/depth/part sheets, object type and dimensions; checks alignment. It does not
invent those aligned maps or recover arbitrary real dimensions.

Do not replace one entry point with an ad hoc assistant-written model generator.

## All production routes and required inputs

| Route | Engine | Required evidence/configuration |
| --- | --- | --- |
| hull | propkit/hull.py | Prepared orthographic views and size/handbook; optional sections, guides, relief, blades, reconciliation |
| hull_parts, default furniture | propkit/hull_assembly.py | Named part views; furniture assembly semantics supplied by order |
| hull_parts, attached | hull_assembly.build_attached | Body/attached specifications and assembly views |
| hull_parts, layout parts | propkit/parts_layout.py | Explicit/handbook-derived part plan, own views, attachment/location rules |
| sheetset | propkit/sheetset.py | Manifest, aligned painted/depth/part maps, dimensions; optional section filename does not mean section image is consumed |
| kit | propkit/kit.py | Component specification, sheet crops and sizing/handbook evidence |
| atlas | propkit/atlas.py | Detected flat panels plus order-specified panel roles and physical scale |
| extrude | propkit/extrude.py | Trim strip/profile or frame image and size; section extrusion, openings |
| facade | propkit/facade.py | Elevation/crops; storey inference or supplied facts, thickness assumptions |
| car / can | props/cars_painted.py, goods_painted.py | Known body/label families and prepared textures |
| recipe | tools/props/*.py registry | Code recipes, shared kit and materials |
| surface | tools/make_tiles.py | Tiling image/spec; surface registration, not general 3D reconstruction |

A capable builder that requires a manifest is not automatic manifest generation.
The v2 automatic workflow currently handles labelled vessel-appliance sheets,
not arbitrary input photos, furniture or every component vocabulary.

## Existing reconstruction capability: reuse map

All paths here are under long-lines/tools/propkit unless stated otherwise.

- hull.py: silhouette extraction, smoothed outline fitting with corner preservation,
  signed-distance visual hull/marching cubes; optional binary field; circular feature
  detection and side-depth evidence; polygon_hull via extruded/intersected outlines;
  loft_from_views already exists. Do not assume all shapes require voxel meshing.
- revolve.py: end-view roundness tests and lathe construction. A lathe assumption
  is evidence-dependent, not a universal model for containers or carving.
- sections.py: width/depth by height band, superellipse candidates, shading/end-view/
  carving evidence and inferred curved runs; voxel hook and diagnostic overlays.
  Sections analysis is not automatically manufacturing separate pieces.
- blades.py: painted-boundary/region carving for hollows invisible in silhouettes.
- relief.py: cavity maps, watershed regions, slope/shading regression, shared light,
  raised/sunk/flat votes, channels, crease grooves, bounded dense displacement and
  optional high mesh for normal baking. It already attempts local relief reasoning.
- guides.py: detects removable coloured strokes, paints them out, extracts ring
  bands and constrains rounded sections. This uses annotations supplied in images.
- edge_guide.py: coloured edge classification, registration, skeletons and mesh
  crease/rounding guidance. It is distinct from unannotated curve recognition.
- hull_assembly.py: default/attached assembly, colour and silhouette subtraction,
  template fitting, holes confirmation, matching, orientation and gap helpers.
- parts_layout.py: root/part views; residual, protrusion, match, concentric, attach,
  inset and leftover placement; recess/opening logic; repeated holes/contact scale;
  centreline and tube sweep; seating/contact checks; adaptive simplification.
- sheetset.py: **important existing engine previously underused**. Part-map ownership,
  parent-carve exclusion of protrusions, occlusion bridging instead of false holes,
  region class/position logic, side_profile_mm, depth-map calibration, physical
  catalogue checks, some separate panels/assemblies and long-thin lofts, cords and
  continuity checks. Needs aligned supplied maps. The section image is not an
  implemented inverse-section constraint simply because the protocol allows one.
- kit.py: evidence/function/convention provenance with components and material rules.
  It is another reusable engine with a specific supplied specification.
- locate.py: masked normalized cross-correlation/template location.
- cord.py: resampled paths, local frames, helices and curved tube construction.
- extrude.py: reads drawn profiles for moulding extrusion, trim and frame openings.
- atlas.py: foreground panel detection; slabs and projected panel textures, knobs.
- facade.py: sheet splitting, storey/period/window lattice inference, recesses and
  nearest exterior surface selection. Not a universal skyscraper assembly engine.
- core.py: mesh primitives, lathe, tube, rods, bevels, UV helpers, soft furnishings.
- parts.py: wheels, sheet boxes, rolled rims, repeated rails.
- sizing.py / human_scale.py / handbook.py / part_rules.py: physical facts, derived
  formulas, contact-scale consensus, envelopes, placement and protrusion priors.
  Priors are estimates, never observations supplied by a photo.
- mats.py: wood, metals, chrome, brass, iron, paint, fabric, glass, paper, cardboard,
  image and painted materials with weathering. Glass material exists; automatic
  transparent-glass reconstruction/material inference is not thereby implemented.
- labels.py: procedural print/packaging/newspaper/book/record/painting graphics.
  These generate artwork; they do not recover original missing texture details.

## Recent V2 additions: exact scope

vision.py uses pinned local DINOv2 ONNX correspondence plus shape/colour candidates.
sheet_blobs.py uses RapidOCR labels and regions. vision_order.py generates one
native parts order for a restricted vessel/base/lid/front-control grammar.

These are local inference tools, not runtime conversational LLM calls. Semantic
roles still depend on caption vocabulary. Hidden-face mappings include hypotheses;
absolute scale uses physical priors. It is not general camera-pose recovery.

depth_inference.py adds robust side-profile spans and explicit prior/conflict
provenance, plus conservative shading-candidate selection around existing relief.
It overlaps sheetset.side_profile_mm conceptually; reconcile their contracts before
deleting or replacing either. The original whole-view score failed the carved-leg case and is now replaced by per-region evaluation.
Do not present abstention as proof there are no grooves.

engineering.py records identity, inferred boxes before seating, attachment/positive
dimension checks and unknown internals. It generates common-scale silhouettes, labelled hatched plane sections and a clipped inspection GLB.
It is reporting, not an optimizing engineering constraint solver.
Arbitrary section planes and hole-aware hatching are now implemented in sectioning.py. A separately clipped, uncapped surface cutaway is exported. Full hidden-line elimination, solid CAD/CSG reconstruction and manufacturing certification remain unimplemented.

## Actual station gaps and ordering hazards

- factory.run_line returns from hull_parts before hull-only reconciliation,
  guide and relief configuration. Selected relief was later connected explicitly
  for automatic parts; that is not universal station parity.
- Single-body automatic-depth/projected or budget=screen builds now call the shared adaptive simplifier. Legacy defaults still use size ceilings, including medium 25,000 -> 23,750.
- sections can improve a voxel solid without generating economical profile topology.
- parts layout simplifies before projection to avoid painted triangles collapsing.
  The single-body route can still encounter later joined-mesh budget reduction.
- bake.finish joins parts. Separate manufactured pieces are not guaranteed to remain
  separate named/hinged GLB nodes after export.
- Texturing already considers facing, source resolution and BVH visibility.
  Weights are evaluated at vertices/corners, then interpolated; no general explicit
  source-pixel part ownership/photometric outlier/seam optimizer is present.
- Bake already creates final UVs, padding, albedo/normal/ORM maps; “apply texture last”
  is not an entirely missing feature.
- Source view resolution bounds authentic detail. Upscaling an atlas is not recovery
  of unreadable lettering, scratches or geometry.
- Ordinary library GLBs use placeholder materials plus separate maps.
  open_in_blender.py reconnects maps; export_textured packages standalone GLB/BLEND.
  A grey placeholder import is not evidence that textures were never baked.

## Standards, schemas and source-of-truth data

factory/standards.json: axes/origin, size classes, triangle ceilings, screen-error
budget, mounting, QA thresholds, retries. factory/sizing_manual.json: dimensions,
formula facts and reasons. parts_catalog.json is generated from sizing_manual.
factory/human_scale.json and reference_handbook.json: body contacts, object assembly
and human-scale assumptions. categories.json: intake route/category defaults.
factory/REFERENCE_SPEC.md: supported sheet protocols and generation prompts.
factory/VALIDATION.md: evidence/physical plausibility rules and explicit incomplete
automation table. factory/TRIM_QA.md covers source-aware trim validation.
factory/fixtures, orders and sheets_*.json: executable examples and supplied specs.
tools/layouts and tile_specs: fixed protocols/configuration, not arbitrary recognition.
Geometry baselines, REPORT and ledger are measurement history, not proof all
current or previously generated assets are acceptable.

## Diagnostics and tests that must not be overlooked

- critique.py: multiview/depth/protrusion/floor complaints and rendered critique.
- match_check.py: ray-cast front depth against a supplied reference depth map.
- diag/render_modes.py: clay, wire, albedo, normals, face-normal facets, depth and
  textured modes. Use these to distinguish paint artifacts from geometry.
- diag/metrics.py: source-resolution silhouette and fold/ridge measurements.
  Its model-bound framing is not a calibrated camera/shape fit.
- diag/regress_assets.py: car/coffee/sofa/wallphone rebuilds with baselines; restores
  library/ledger/report and removes experiment outputs. Read before running it.
- diag/scale_audit.py: human-scale inspection; diag/sheet.py comparison sheets.
- test_sections, test_guides, test_hull_geometry: synthetic geometry/guide regressions.
- test_sizing, test_human_scale: physical-rule consistency.
- test_automatic_intake, test_automatic_build, test_depth_engineering: recent CV,
  orchestration, actual export acceptance and inference/section guards.
- tests/test_trim_checks.py: Blender-independent trim checks; trim-qa workflow
  installs dependencies, syntax-checks selected files and runs these tests.
  It is not CI coverage of all reconstruction routes.
- Godot tests/run_tests.gd, smoke_test.gd and screenshots.gd cover the game.
  Passing game tests cannot prove image reconstruction is correct.
- docs/benchmarks/sheetfirst_vs_legacy contains preparers, renders and stress tests.
  Its prepared inputs are benchmark assistance, not production auto-intake.
  Do not silently promote those scripts or a historical alternate pipeline.

## Known quality limitations, backed by observed trials

Existing QA includes geometry/export integrity, normal disagreement, floor contact,
UV density/stretch, holes, silhouette overlap and trim-source checks. The legacy generic
silhouette gate uses coarse 72-pixel-width masks, independent reference fitting,
small-excess-component removal and five directions. Automatic-depth orders now
also enforce raw unfiltered overlap, use 144-pixel masks and compare available bottom views.
A global “pass” can coexist with missing grooves or a malformed handle.

Blender reference trial:
- 26 detected drawings; 12 manufactured pieces including six detected buttons.
- Initial automated build 3,652 triangles; depth-inference revision 3,650.
- Source front/back/side handle locations conflict; one jar part contains the handle.
  Two separately added handles were not established. Geometry plus projected ghost
  imagery remain possible contributors; exact causal isolation is incomplete.
- Profile estimates around 6–7 mm buttons and 18 mm knob; lever ~9 mm conflicted
  with its button-derived prior and correctly retained needs_review.
- New shading selector chose flat on all body elevations; no extra relief.
- Jar companion views roughly 120–163 pixels wide: 2K maps do not add evidence.

Guided leg trial:
- updatedleg.png exactly matched the pre-existing guided-leg source SHA-256:
  cbf43d027eb18dca261e84e9c8c7a6450cebb89c78c4ad3a413719509baf4981.
- Existing view specification, guide removal and human sizing were reused, without
  new hand-entered crop coordinates. This was not generic image-only intake.
- New selector build: 114 seconds, 23,750 triangles, rounded shaft recovered.
- All relief hypotheses rejected; clay showed flatter carving than original relief.
  This is failed ornament-depth acceptance despite high silhouette scores.
- Target height ~690 mm is a human-scale estimate, not a measured dimension.

Original Dirac checkout was verified clean during prior trials. Preserve approved
assets and original sources. Do not “fix” uncertainty by silently discarding
contradictory observations, changing thresholds for one image or treating a
generated section as independent evidence.

## Root web application and Godot game boundaries

Root README/package.json/app.js/config.js/sw.js/index.html/style.css and
scripts/collect.mjs belong to Midnight Watch. The collector uses RSS parsing and
Web Push dependencies. .github/workflows/collect.yml is its scheduled collector.
Do not change its configuration, publishing or notifications to improve Hull.

long-lines/project.godot launches scenes/main.tscn and autoloads Data/Game.
scripts/core manages configuration/state; scripts/sim covers clock, climate,
air, needs, inventory, radio, cold chain and fridge systems.
scripts/world handles apartment construction, player/interactions and prop
behaviour. PropFactory places library props, swaps model visuals and applies
condition/snow/frost. It is in prop_factory.gd, not a separate prop_library.gd file.
scripts/world/props contains gameplay nodes for doors, containers, fixtures,
radio/phone, stove, sink/tub, windows and decorative/interactable items.
scripts/ui/hud.gd is game UI, not a reconstruction UI.
data/*.json defines the apartment, objects, documents, events, tuning and surfaces.
shaders include baked-prop state effects. Imported visual assets do not imply
matching reconstruction code ran or succeeded.

## Runtime, reproducibility and working safely

Blender Python is required for bpy/bmesh/mathutils modules. Pure sizing, map or
image utilities may run in normal Python; do not import every module to inventory
it because several scripts execute scenes/builds at import time.
Geometry needs NumPy/SciPy/scikit-image/Pillow. Optional vision additionally needs
RapidOCR, ONNX Runtime and OpenCV; pinned dependencies are in requirements-vision.txt.
DINOv2 model URL/revision/checksum are pinned in vision.py; HULL_VISION_MODEL
can select an existing matching file. OCR may download weights initially.
Model files and dependency installs are local runtime prerequisites, not source.

Use PYTHONHASHSEED=0 for comparative builds. Blender UV packing can vary, so byte
identity is not the reproducibility criterion. Use geometry/appearance gauges.
HULL_FIELD and HULL_SECTIONS are diagnostic feature switches; record them.

Local checkout for current work:
C:/Users/jared/Documents/Codex/2026-11-09/can/work/Hull-V2-trusting-dirac.
Untouched original:
C:/Users/jared/Documents/Codex/2026-11-09/can/work/hull-source.
Blender installed at C:/Program Files/Blender Foundation/Blender 5.2/blender.exe.
Temporary dependency directories currently live under can/work; these are session
setup, not a portable installer. Some old scripts assume Linux paths/fonts or a
blender command on PATH; inspect their worker environment before running.

Builds mutate assets/props, source_textures, orders, library.json, ledger and REPORT.
Godot imports can alter many .import files. Generated trial assets and odd-named
untracked directories exist locally; do not delete/move them as incidental cleanup.
Stage explicit intended source/documentation paths, never a blanket git add.
Shell Git HTTPS previously failed Windows credential acquisition; connector pushes
worked. Do not ask the user to repeat the old authentication setup without evidence
that it is necessary.

## Next-work rules and maintenance

Before implementation: identify the existing function, required input contract,
actual dispatcher, overlapping implementation and a meaningful acceptance test.
Prefer adapters/shared stations over another complete pipeline.
First improve ownership/consistency, shared adaptive reduction and honest gates.
Then local curve/groove fitting and camera/shape estimation. Section drawings can
be a deterministic inspection station with arbitrary planes and nested-loop handling.
No joint inverse-CAD solver or general camera optimizer currently exists.

Mark knowledge as SOURCE-VERIFIED, OBSERVED RUN or PROPOSED in new entries.
Update this file and the inventory when code contracts change. The original 391/82/36 counts above are the initial audit snapshot; use the regenerated inventory metadata for current counts. Historical successes
and failures must retain their actual input assistance and limitations.
This file records knowledge; it does not authorize destructive operations, broad
rewrites or changes to the untouched original repository.
