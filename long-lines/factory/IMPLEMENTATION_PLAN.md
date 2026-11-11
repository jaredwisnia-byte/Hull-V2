# Hull audit implementation and acceptance plan

This is a working status document. Implemented stages below are exercised in code;
the research backlog is not presented as completed inverse-CAD functionality.
The original Claude/Dirac checkout is unchanged. All runtime decisions are software
operations; no conversational LLM supplies per-object corrections.

## Implemented: shared stages and readable code

- `propkit/pipeline.py` owns image-only intake/build/export/render orchestration,
  freshness checks, persistent failure reports and review status. Factory's public
  entry point remains compatible. Unexpected station errors write a traceback and
  result instead of leaving a stale successful output looking current.
- `propkit/preflight.py` reuses existing view reconciliation for diagnostics on
  the automatic parts path. Suggested flips/resizing/view rejection are proposals,
  never silently applied to source evidence. Conflicts retain `needs_review`.
- `propkit/simplification.py` holds the existing screen-space tolerance and
  bidirectional sampled surface-error simplifier. Parts-layout compatibility imports
  remain; single-body projected hulls opt in through `automatic_depth` or
  `budget: screen`. Reduction now precedes projection on that path.
- Fixed the simplifier's reported-error calculation: retain the selected trial's
  measured error instead of measuring the final mesh against itself. Refresh split
  normals after topology changes, reusing one helper in both affected paths.
- Expanded dense statements, spacing and long expressions in the active entry points
  and recent vision/depth/engineering modules. AST comparisons verify that vision
  and vision-order formatting did not change their semantics. Import-order-sensitive
  Blender entry points retain explicit path initialization.

## Implemented: local depth decisions and honest validation

The original relief engine already segments physical candidate regions. Those
regions now reach the depth selector directly. Each region's observed shading is
tested against relief/flat hypotheses at the existing acceptance threshold.
Unrelated wood paint elsewhere no longer vetoes a local feature. Source masks
still exclude separately manufactured controls and uncertain silhouette borders.

Selected relief remains bounded to 2% of the smaller horizontal dimension. On
single-body builds the dense relief copy is retained for the existing high-to-low
normal bake, preserving details below the low-poly surface tolerance. Parts builds
do not supply a partial body-only bake source for the whole joined assembly.
These are shading hypotheses, not measured groove depths or guaranteed recovery.

Automatic-depth QA now records unfiltered silhouette overlap, uses a 144-pixel
width rather than the legacy 72, and includes bottom references when supplied.
The raw outline can fail even when the older protrusion-filtered score passes.
Existing thresholds are unchanged. Camera framing is still derived from model
bounds; this is stronger detection, not calibrated camera/geometry validation.

## Implemented: section and cutaway inspection

`propkit/sectioning.py` defines arbitrary finite plane origins/normals, computes
mesh intersections, joins closed degree-two contour components and reports open
or branched components. Even/odd filling preserves nested voids. Hatching marks
cut material; open contours are not silently filled.

Engineering export supplies A-A/B-B transverse sections and a C-C longitudinal
section at a common scale, with plane indicators/directions on parent views.
An order can override one to three planes through:

```json
{"engineering":{"sections":[
  {"label":"A-A","origin_m":[0,0,0.3],"normal":[0,0,1]}
]}}
```

`propkit/cutaway.py` exports a separately clipped `surface-cutaway.glb` using
Blender's existing mesh operations. It restores scene selection and never edits
the main geometry. Its cut boundaries are intentionally open: blindly capping
them could fill a real hollow component. Hatched 2D sections and a clipped surface
are diagnostics of reconstructed geometry, not certified solid CAD or discoveries
of unseen interiors. Offset/half/broken-out drafting conventions and full hidden-line
elimination are not implemented.

## Observed acceptance results

Guided leg: existing source SHA/preset reused, no new supplied crop coordinates.
The previous new-selector build had 23,750 triangles and rejected every relief
region. The cleaned path has 1,302 triangles, zero normal disagreement, and sampled
surface error 1.292 mm against its 1.297 mm screen-space tolerance. It selects
14/50 front, 19/43 right, 12/41 back and 13/40 left candidate regions. Raw silhouette
overlap is approximately .953-.972 on elevations, .962 top and .809 bottom.
The low bottom score remains a limitation, not evidence of perfect geometry.

Blender: the image-only workflow still builds about 3,650 triangles but now flags
inconsistent reference proportions and the lever prior conflict. Raw top overlap
around .787 fails the unchanged .8 threshold, whereas the old filtered metric
passed. This is correct rejection of a previously over-permissive acceptance case,
not a claim that duplicated handle appearance has been fixed.

Tests exercised locally: 11 depth/engineering tests under Blender; 5 section
topology tests; sphere simplification bound/reduction; non-destructive cutaway
half-space export; non-destructive preflight conflict reporting; 3 orchestration
guards; 9 intake tests; existing hull geometry, guide, section, sizing/human-scale
and 8 trim checks; Godot 39 unit and 45 smoke checks. New CI runs syntax and
pure-Python section/depth/sizing contracts. Blender integration still needs a
Blender-equipped runner; it is not falsely counted as hosted CI coverage.

## Profile-family implementation (2026-11-11)

The next production path is integrated in `factory.run_line` for automatic-depth
projected hull orders. It selects elongated profiles from masks, fits camera roll
and shared nonlinear curvature, traces longitudinal channels, and compares bounded
shape/light/material fits against flat and painted-stripe alternatives. Construction
bands are independently cut from the original hull; the shaft uses a spline loft
with channel vertices. Other geometry continues through the original engines.

The finished leg has eight construction identities, seven channels and 3,308
triangles. Ray probes through the exported mesh verify all seven recesses at three
stations. Inward hits and normal disagreement are zero. This passes geometric QA,
while uncertain depth evidence is separately reported. The rendering still shows
limited ornamental geometry; source paint is substantially richer than the capital
and foot meshes. Do not call the object fully reconstructed from its silhouette.

The held-out blender image ran through the full image-only pipeline in 72.7 s,
without runtime LLM preparation. It retains 3,650 triangles, no inward-facing hits
and no normal disagreement, and correctly remains `needs_review`: raw top-view
overlap is .787, below the unchanged .8 threshold. This is a regression/abstention
case, not a claim that its handle semantics or assembly are fully corrected.

Physical IDs survive join/bake/export and return as separate standalone nodes.
Final UV texels use rasterized source visibility and owner labels rather than
interpolated vertex visibility. Per-source overlap correction is shared across
triangles, bounded, and rejects incompatible paint. Unsupported pixels fill only
from the same owner's evidence, with confidence/unresolved counts. Invisible
details are not synthesized or represented as observed texture.

The new pure-Python and Blender contracts exercise known curved/rolled axes,
source reprojection, paint ambiguity, duplicate observation merging, raster
occlusion, colour-space handling, seam correction, duplicate geometry rejection,
oriented internal caps, actual GLB part round trips and local missing-depth checks.
Existing hull/guide/section/sizing/orchestration checks and Godot 39 unit/45 smoke
checks pass locally. Hosted CI includes the pure-Python profile contracts; actual
Blender integration requires the local Blender runtime.

## Remaining generalization and exit criteria

1. **Ownership and part recognition:** adapt existing sheetset part ownership to
   arbitrary automatic inputs, with one physical identity across observations. The
   new geometry ownership and rounded-shaft feature matcher are not a general
   image semantic segmenter. Distinguish genuine two-handle objects. Do not merge
   sheetset and isolated-profile depth estimators without reconciling their different
   coordinate/evidence contracts.
2. **Region construction:** use existing section/revolve/loft/sweep engines to fit
   meaningful construction regions beyond the integrated elongated profile family.
   Its bands/shaft now manufacture independently, but semantic names and ornamental
   subpart decomposition remain unresolved. Hold out unrelated object families.
3. **Joint camera/shape fitting:** fit roll, projection and landmark correspondence
   with bounded numerical optimization; separate genuine bends from camera tilt.
   Test known camera perturbations, curved shafts and contradictory drawings.
   The integrated, tested roll/shared-bend fit applies only to nominal orthographic
   profiles. Perspective pose, unknown view direction and absolute linear tilt
   remain unresolved; a planar warp is not general 3D rectification.
4. **Appearance ownership:** integrated per-texel validity/occlusion, disagreement
   rejection and bounded seam correction still depend on correct physical placement
   and image semantics. Validate unrelated families and incorrect semantic masks.
   Larger atlases or synthesized pixels do not create authentic source evidence.
5. **Feature validation:** add local contours, groove depth/sign, attachment frames,
   apertures and small-feature checks beyond the new exported shaft-depth probes,
   existing attachment gaps and persistent physical IDs.

These research-dependent stages require independent fixtures and acceptance gates.
Preserve the original and approved assets; do not lower thresholds to make one
picture pass. Update KNOWLEDGE_FILE and regenerate the static inventory after changes.
