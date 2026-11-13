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
- Export QA now consumes the drawing's measured elevation crossings. At each
  retained source height it compares the source outer-contour width/height with
  the exported mesh's orthographic width/height. The report keeps each source
  trace ID and raster row; persistent disagreements or an isolated error over
  three times the resolution allowance enter stage review. Views
  without a verified pixel map and views held out of geometry are not compared.
  This checks the outer envelope, not carving depth or hidden section shape.
  The current check applies to the single-body automatic Hull line. Multipart
  assets need per-part source ownership before an assembly-sheet width can be
  compared meaningfully with one exported part.
- On four archived single-body exports, the carved leg had 0/19 out-of-budget
  height samples in each elevation, the toaster had 2/19 in front, the camera
  had 6/19 in back, and the car had 11/19 on the left plus isolated severe
  front/back misses. The camera's previous back silhouette IoU was 0.975 and
  the car's left IoU was 0.996, showing that a high global score can hide local
  width or aspect errors. These trials audited archived meshes; they did not
  rebuild them with the current engine or validate internal relief.
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
  complete construction-consumption audit are incomplete. Current section/profile
  tools make geometric inferences from silhouettes and shading; the width audit
  only covers sampled outer envelopes, not all relevant internal traces.
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
