# Trace-driven technical drawings: current milestone

## Goal

Before building geometry, Hull should produce an engineering drawing from the
actual supplied views. Observed outlines and internal boundaries must be
traceable to source pixels. Cross-view correspondence, sections, parts, depth,
and dimensions must be marked as inferences with measured support and explicit
unknowns. The resulting construction decisions must refer back to the drawing.

## Implemented and verified

- The automatic-depth factory path creates `technical-traces.png` and
  `technical-traces.json` before geometry. `drawing_traces.py` records source
  view, pixel path, tracing method, and sheet transform for every displayed
  silhouette and internal boundary. It does not substitute circles or other
  primitives for those observations.
- Opposing source masks can propose an opening cut. The drawing records the
  exact source contour and opposite-view witness. The same mask goes to the
  base hull. A stage-review finding holds release because opposing painted
  views alone do not prove a physical through-hole.
- The drawing measures 19 horizontal contour crossings in each supplied
  elevation and pairs front/side envelope widths by relative height. Each
  measurement retains the exact source contour segments. It explicitly leaves
  the intervening 3D section shape unknown. A nine-object mixed trial checked
  684 section rows against their original masks; the maximum measured outline
  difference was 0.5 source pixel.
- The core and Blender check profile passed 44 checks after this change, and
  the camera/cassette prebuild integration check passed. These checks do not
  certify physical geometry or the unresolved internal feature interpretations.
- The sheet now distinguishes a preflight view conflict from actual build use.
  The seven consumer pilot orders each have at least one view that preflight
  proposed for paint only while the builder still uses it for geometry. Stage
  review flags this contradiction. Source-aspect residuals for 0/180 versus
  90/270 degree end-view axes are saved as diagnostic hypotheses, not applied
  rotations; aspect cannot resolve flips or camera pose.
- When reconciliation changes a build view, the sheet traces the original
  supplied image and stores the altered construction image separately. Its
  build-input contour IDs cannot masquerade as source contour IDs. Stage review
  holds the result until a source-to-build pixel mapping exists. Hull now records
  each reconciliation operation. A lossless horizontal flip receives a mapping
  only after the processed pixels exactly match the flipped source; opening
  candidate coordinates can then be mapped back. A CRT television's right view
  was both flipped and partly erased. Its raw trace stayed intact, but the
  altered build trace remains unresolved because erasure can create new edges.
- Prebuild integration was checked on an instant camera and cassette recorder.
  A mixed diagnostic trial also included toaster, typewriter, hair dryer, alarm
  clock, stand mixer, a carved leg, and another camera view set. The trial
  exposed a questionable leg seam accepted as an opening candidate; that case
  is retained as a negative control.

## Still open

- Internal traces are observations, not construction constraints. There is no
  validated universal association of fragments into physical parts or of
  corresponding features across views. The camera lens therefore is not yet
  guaranteed to become a correct cylindrical assembly.
- True cross-section shapes, hidden lines, dimensioned part drawings, and a
  construction-consumption audit are incomplete. Current section/profile
  tools make geometric inferences from silhouettes and shading; the prebuild
  trace sheet does not yet certify their deviation from all relevant traces.
- The opening validator can mistake a painted seam for a cut. A hair-dryer
  false protrusion rejected an earlier isolated circle-to-cylinder prototype;
  do not promote that prototype or special-case the camera.
- View reconciliation is diagnostic in the automatic-image path. Its proposed
  paint-only list is not currently applied to construction. Some proposals
  may be explained by a rotated view or a core-mask measurement, so the next
  correction must compare the source frame, full silhouette, and resulting
  mesh on the mixed set before adopting a view transformation or exclusion.
- Reconciled build-input paths with erased or otherwise modified pixels still
  lack a complete original-source correspondence. They remain construction
  evidence with an explicit provenance gap, and release review holds them.

## Next acceptance gate

Derive cross-view feature correspondence from source paths and calibrated view
frames. For each proposed 3D feature, store the source path IDs, view-to-view
mapping, sampled reprojection error, and competing interpretation (relief,
paint, shadow, seam, opening). Leave unresolved evidence unresolved. Before
adopting a construction change, compare its clay render, source-view silhouette,
local feature checks, topology, and triangle count against the existing build
on the mixed-object set above. A gain on one asset does not qualify the rule.
