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

## Follow-up: openings and companion evidence, 2026-11-13

The original wall-phone parts route detects repeated holes in the dial's
`h_front.png`, cuts them in `parts_layout.build_part`, and tests their diameter
against human-scale contacts. That mechanism was not used by the generic
outer-body route. The generic route now carries source openings into its
visual hull only when opposed views agree. Its quality check measures how
much of each supported opening the exported mesh blocks. A cassette trial
blocked 6.5%/6.6% of its front/back handle opening; a mixer trial blocked
2.0%/2.6% of its left/right gap. Both exports remain `needs_review` because
local depth probes still fail.

Companion labels split across OCR lines or set beside a `DETAIL:` heading now
name candidate regions without an object-specific vocabulary. In the seven
sheet intake rerun, every sheet had named companion candidates, but none had
a part with independently supported placement in three dimensions. The part
graph records each unresolved candidate. Lowering its match threshold from
0.25 to 0.08 creates false cross-view associations, including a cassette
handle matched to the bottom view, so the acceptance threshold was retained.

Projected textures now export an indexed source-view map, a colour preview,
and the source-confidence map. The screen-space mesh budget accepts an
explicit `--view-distance` value in metres for `factory.py auto`; the default
remains the category's configured near distance. These are diagnostics and
budget controls, not new evidence for hidden geometry.

## Local depth transfer audit, 2026-11-13

Saved first-attempt diagnostics for the cassette and toaster were sampled at
the exact source-derived three-point probes that failed on the dense mesh.
The accepted image-space height retained the target sign and at least half
its contrast at 14/15 cassette and 28/29 toaster probes classified as
source-supported. Those same 42 probes fell below half contrast, or reversed
sign, in the final shared field before mesh reduction. This local evidence
locates most observed loss in view fusion or the following field repair; a
global least-squares transfer score did not expose it. It does not establish
that every source shading feature is physical depth. The mixer fallback did
not save a final shared-height chart, so it cannot support this comparison.

The probe review now records accepted, shared-field and dense contrasts at
the same model-space anchors, plus the first stage where a loss is measured.
These measurements diagnose the failure; they do not relax the geometry QA
gate or change the construction field. The next candidate change should be
tested against these local gauges and final mesh/outline/fold checks on more
than one object family.

### View-fusion checkpoint

A controlled toaster rerun saved the field immediately after view fusion,
after construction reconstruction, and after component preservation. At 28
of 29 failed source-supported probes, the first half-contrast or sign loss
was already present immediately after view fusion. The later field stages
kept nearly the same sampled contrast. One probe retained sufficient field
contrast and failed at the dense-mesh measurement. These are first measured
losses against source-derived targets, not verified physical-depth errors.

Increasing only the field resolution from 110 to 160 did not resolve the
failure: 31 of 31 source-supported failed probes first lost contrast at view
fusion, missing-depth probes rose from 36 to 38, and triangles rose from
5,026 to 6,782 against a 6,000 budget. The resolution experiment was not
adopted. Diagnostic NPZ files and probe review now expose the intermediate
field contrasts and preserve the older broad classification when prior run
archives lack these checkpoints. The remaining fix must address transfer
between views while preserving source support, silhouettes, folds, and the
triangle budget across multiple object families.

A second control run split the transfer into image resampling, the local
thickness safety cap, and view fusion. All 29 source-supported failed probes
had the same sampled and capped local contrast. At 28, the first half-contrast
or sign failure occurred at view fusion; one retained field contrast and
failed at the mesh/probe measurement. Across the 29, the median signed
fused-to-capped contrast ratio was 0.032 and 13 ratios reversed sign. This
rules out the safety cap as the immediate cause in this control, without
establishing that the source-derived depth estimate is physically correct.
Future diagnostic reports keep these checkpoints separate, and older reports
without them say only `pre_fusion_or_fusion`.
The control build remained quarantined with the same 36 depth failures,
5,026 triangles, and 4.974 extreme folds per 1,000 triangles as the prior
run, confirming the new checkpoints did not change that build's geometry.

An opt-in `HULL_TRACE_FUSION=1` diagnostic now applies each accepted view
to the coarse field on its own and records sparse per-view weights and
field shifts at source-derived probes. This separates single-view field
transfer from multi-view combination without changing the final field. On
the toaster, all 29 source-supported failed probes retained sufficient
contrast in the one-view field; 28 first lost it in the combined field.
On a separate cassette control, all 15 retained it in the one-view field;
14 first lost it in the combined field. The cassette's traced final QA
was unchanged at 16 failures and 5,574 triangles. The toaster's nearest
voxel trace found a competing view at one or more anchors on 26 of 29
failed probes, but a continuous cassette trace found that pattern on only
2 of 15. Simple strongest-view selection therefore lacks cross-object
support. These are diagnostic projections against source-derived targets;
the correct physical depth remains uncertain.

A held, object-independent amplitude-weighted fusion trial improved final
missing-depth counts on both controls: toaster 36 to 30, cassette 16 to 12.
The toaster mesh rose from 5,026 to 6,104 triangles and exceeded its 6,000
limit; the cassette rose from 5,574 to 5,878 triangles and still failed QA.
Neither was released. The trial rule was removed, leaving the original
weighted fusion unchanged. A subsequent candidate must solve the remaining
view conflicts and mesh cost before promotion.

## Provisional surface contact, 2026-11-13

A two-resolution correspondence audit tested all 17 captioned detail regions
against the six assembly views on each seven-sheet pilot (102 pairs). Doubling
the DINOv2 source/target resolution from 224/448 to 448/896 found one extra
above-threshold match, but the unchanged part graph still produced no
three-axis placement on any sheet. More keypoints alone cannot establish
physical ownership or the missing depth coordinate.

The intake graph now records a *contact hypothesis* for a single-view match
when a perpendicular assembly silhouette supplies an outer-envelope witness.
For a front/back or left/right mount, it uses the opposed horizontal views at
the matched height; top/bottom silhouettes span all heights and can capture
unrelated protrusions. Each hypothesis includes the proposed mount face,
position, outward normal, witness spread, and an explicit unverified-depth
warning. It does not count as a spatially constrained part, authorize
manufacture, or change `needs_review`.

On the saved pilot, baseline correspondence yields three provisional contacts:
the cassette door, cassette folding handle, and typewriter carriage lever.
A fresh cassette image-only intake records two of them in its normal report
while retaining the `outer_body_only` build scope. The other four sheets still
lack a supported correspondence. The remaining task is to validate part
identity and protrusion against independent views, estimate the actual mount
and depth, manufacture each part once, then run complete artifact QA.

## Fusion crossing audit, 2026-11-13

The opt-in fusion trace now stores a short depth profile around each
source-derived probe anchor: original field, every one-view field, and the
combined field. This is diagnostic data only and does not alter geometry.
An initial analysis incorrectly chose the nearest zero crossing without
checking which side of the surface faced the camera. That sometimes selected
the rear/exit face and falsely suggested relief survived. A corrected
single-attempt cassette analysis selected only camera-facing entry crossings
and compared the first visible root along the same ray. Of 18 failed probes,
17 had a measurable visible-root contrast; 17 of those lost at least half
their source-view contrast or reversed sign. Ten had valid local entry
crossings for all three fields, and nine lost at least half contrast locally.
The other eight had no camera-facing entry *inside the sampled baseline
window* because their original surface touched the field boundary; this does
not establish that they had no physical surface. The result supports
attenuation at fusion, rather than a hidden surviving local groove, on this
control. It still does not establish physically correct source depths.

The earlier full held rerun reproduced the prior cassette outcome exactly:
16 missing depth probes, 5,574 triangles, and 3.588 extreme folds per 1,000
triangles. The new single-attempt diagnostic deliberately disabled automatic
retry and therefore retained the first candidate: 18 missing depth probes,
5,572 triangles, and 3.59 extreme folds per 1,000 triangles.
Its full build also exposed a Blender-on-Windows file I/O limit: a 261-character
diagnostic preview filename failed while shorter files in the same directory
saved. Long diagnostic image paths now use Windows extended-path I/O for save
and copy; ordinary paths remain in manifests. This was verified inside Blender
with a 268-character path. It fixes the build interruption, not the depth QA.
