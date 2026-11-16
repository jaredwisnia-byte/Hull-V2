# Stranded modules: built, tested, never run by image-only builds (audit 2026-11-16)

Method: every call into `long-lines/tools` was recorded during a real image-only build of
`003_typewriter` (saved-intake harness, main at 7a99c43 plus claude/part-features). 90 propkit
modules exist; 68 ran; 22 never ran (5,471 lines). One object only: another sheet may reach a
step this build skipped, so re-run the audit (`sys.setprofile` wrapper around the harness) per object.

## Built for the image-only problem, never connected
| Module / step | Built to do | State |
|---|---|---|
| `curves.py`, `curve_views.py` | true lines/arcs/ellipses per view, statistical noise rejection; agreement across views on shared axes (the draftsman's projection lines) | never called by any build; only tests use them |
| `hull_assembly`, `parts_layout`, `locate` | build each part from its own views, then assemble | used by drawn parts sheets only |
| `blades.carve` | lower each top-view region to the height the front view shows (cut from the top) | `hull_prop(blades=False)`; no order enables it |
| `tracing_worker` | learned edge detector (MatchED-BIPED) | never called; edges come from LSD straight segments |
| `depth_inference`, `local_retry` | evidence-first depth; bounded repair of details lost in view fusion | never run |
| `sections.hook`, `revolve.voxel_hook` | round sections per height band; lathe parts | did not run on the typewriter (cause not yet checked) |

## Correction: they run at intake, but their parts are never built
`vision.compact_parts` and `part_graph` run in sheet intake (`sheet_blobs.py`), which the
saved-intake recording does not replay. On the typewriter they name the detail panels
`carriage_return_lever` and the part graph matches the side detail to the left view: depth and
height bounded, width unbounded (one view, `spatially_constrained: false`); the front detail is
rejected. `compact_parts` only builds caption roles `button` and `knob`. Every painted sheet's
work order is set to `build_scope: outer_body_only` (`vision_order.py`), so even a placed part is
never built separately.

## Wired in (2026-11-16)
- `curves` + `curve_views`: `drafting.curve_evidence` runs them on every drawing; per-view counts,
  constructions and tolerances go into `drawing.json`, overlays `curves_<view>.png` beside it.
  Evidence only; geometry unchanged.
- `tracing_backend` (MatchED-BIPED): registered with `configure_tracing.py` in the local,
  gitignored `.hull-models/`. Still `classical` by default in the build: its own note says the
  shading-probe retention test regressed with it.

## Expected not to run here
Other product lines (`facade`, `kit`, `atlas`, `extrude`, `sheetset`, `cord`), the opt-in CAD
export (`cad_mesh`, `cad_export`), drawn-sheet helpers (`human_scale`, `handbook`), maintenance
(`workspace_inventory`, `relief_preview`). `bake_normal_worker` runs in its own Blender process,
so the in-process recorder cannot see it.

## Rule
A module is not done when its tests pass. It is done when a real build of the product it was
written for calls it, and the build's report shows what it decided.
