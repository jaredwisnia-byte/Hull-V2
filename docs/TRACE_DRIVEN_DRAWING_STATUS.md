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
- Source-derived technical sections, hidden lines, dimensioned part drawings,
  and a construction-consumption audit are incomplete. Current section/profile
  tools make geometric inferences from silhouettes and shading; the prebuild
  trace sheet does not yet certify their deviation from all relevant traces.
- The opening validator can mistake a painted seam for a cut. A hair-dryer
  false protrusion rejected an earlier isolated circle-to-cylinder prototype;
  do not promote that prototype or special-case the camera.

## Next acceptance gate

Derive cross-view feature correspondence from source paths and calibrated view
frames. For each proposed 3D feature, store the source path IDs, view-to-view
mapping, sampled reprojection error, and competing interpretation (relief,
paint, shadow, seam, opening). Leave unresolved evidence unresolved. Before
adopting a construction change, compare its clay render, source-view silhouette,
local feature checks, topology, and triangle count against the existing build
on the mixed-object set above. A gain on one asset does not qualify the rule.
