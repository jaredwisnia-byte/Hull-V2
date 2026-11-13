# Consumer sheet intake, 2026-11-12

Tracking: https://github.com/jaredwisnia-byte/Hull-V2/issues/5

## Baseline

Seven image-generated consumer-object sheets (toaster, cassette recorder,
typewriter, instant camera, hair dryer, alarm clock, stand mixer) were run through
`sheet_blobs.py auto` without hand-supplied crops or view assignments. None reached
`ready_to_build`: four hit the vessel-only assembly grammar, and three lacked five
assigned assembly views. The source sheets and per-case intake reports are retained
outside the repository in `C:/Users/jared/Documents/Codex/Hull-dataset-100`.

## Changes under test

- Exclude title text and lettering printed inside a drawing from part headings.
- Split a merged detection region when two independent view captions are directly
  below it, and allow a caption to touch the detected drawing boundary.
- For sheets outside the supported vessel grammar, emit a general outer-body Hull
  work order from the labelled assembly views. Keep companion part regions unresolved
  in machine-readable evidence; the generic path does not manufacture those parts.
- Flag unresolved companion parts in full-pipeline inference warnings so an outer-body
  build cannot be reported as a fully completed multipart reconstruction.

## Pilot result

After the intake changes, all seven sheets reached `ready_to_build` for the outer
body. This is an intake result, not a geometry-quality result. Full-build QA and
independent validation of companion-part placement remain separate gates. The scale
for the generic path is an explicit unmeasured three-hand-width prior. A first
end-to-end toaster trial at one hand-width generated a 91 mm-wide model; QA rejected
it for extreme local surface folds (37.4 per 1,000 triangles) and excessive texel
density (14,407 px/m). The rescaled repeat produced a 272 x 152 x 111 mm model
with 4,890 triangles and removed that texel-density failure. QA still rejected
it for 36 missing shading-depth probes. The visual render is retained at
`C:/Users/jared/Documents/Codex/Hull-dataset-100/build-check/001_toaster_rescaled/vision_001_toaster.png`.
The image-only path therefore must not report a complete multipart model from
this pilot.

## Remaining tickets

Issue #5 stays open until generic physical-part ownership and placement, correct
scale estimation, full-build QA across object families, and visual comparison against
the reference sheets are verified. The 100-sheet dataset is also incomplete; these
seven sheets are a pilot, not a training benchmark or ground truth geometry.
