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
- The prebuild sheet displays overall source-mask dimensions and three sampled
  contour widths alongside its orthographic paths. These dimensions are in
  source pixels and retain outer-trace IDs in JSON; physical dimensions remain
  unknown without a calibrated scale. The sheet is still an observational
  drawing, not a manufacturing drawing with verified hidden geometry.
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
  The check now applies to automatic single-body and multipart Hull lines,
  comparing the assembly source outline with the full assembled export. This
  does not validate individual part profiles or their internal features.
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
- Automatic multipart intake now traces exact original-sheet crops for the
  assembly and each assigned companion group before construction. Each path
  retains its crop offset into the original sheet. A 26-crop blender diagnostic
  verified every crop against the supplied image pixel for pixel. The same
  prebuild process produced assembly drawings for a toaster, instant camera,
  and hair dryer. A reused crop assigned to two directions is reported as one
  observation, not two independent measurements. Supplied part-view orders
  also receive prebuild trace sheets.
- For `layout: parts`, a second prebuild drawing records the prepared views
  actually supplied to construction. Its compiled silhouette masks now feed
  body and companion `hull_prop` calls. The builder checks both input-image
  and compiled-mask hashes and reports the consumed build trace IDs for each
  part. It will fail if an input changes after tracing. If the prepared image
  differs from the original sheet crop without a verified pixel map, stage
  review explicitly holds that view; the prepared trace cannot claim to be
  original-source evidence. Other multipart layouts still record drawings but
  do not yet consume their compiled masks.
- The automatic-depth path now saves its training-only internal boundary
  packet in the prebuild drawing record after the final valid shading region
  is known and before meshing. The relief solver consumes that exact packet,
  with input, mask, and packet checksums. An image overlay shows persistent
  achromatic boundaries, colour-ambiguous boundaries, and weak fine candidates.
  This applies to single-body automatic Hull and to parts-layout body and
  companions. Boundaries affect curvature regularization and region selection;
  they do not by themselves assert a groove, raised part, bore, or depth sign.
- A controlled automatic toaster build using the saved trace had the same
  geometry signature, 5,926 triangles, 32 shading-depth QA failures, boundary
  counts, and held-out shading gains as an otherwise identical run that traced
  inside the solver. The handoff preserved behavior; those depth failures
  remain open.
- A real blender rebuild retained its prior geometry signature and 3,652
  triangles after this handoff. Mixed rotary-phone and CRT-television builds
  consumed prebuild masks for seven and two part groups respectively; their
  geometry signatures also remained unchanged. Both still failed pre-existing
  mesh QA (phone: normals and front/top outline; TV: normals). These trials
  verify the handoff and regression behavior, not finished asset quality.
- An archived multipart blender export was audited against the source assembly
  drawing: front 2/19, right 9/19, left 11/19, and back 17/19 sampled widths
  exceeded the source-resolution allowance; six back samples were severe.
  The export also failed its existing top-outline check (78% agreement). This
  is a diagnostic of an existing export, not proof the current build improved
  the blender.

## Still open

- Internal source path IDs are observations, not verified physical construction
  constraints. Compiled boundary arrays guide shading regularization. There is no
  validated universal association of fragments into physical parts or of
  corresponding features across views. The camera lens therefore is not yet
  guaranteed to become a correct cylindrical assembly.
- Multipart construction now consumes compiled outer masks from the prepared
  drawing on the `parts` layout and uses the inferred part plan. The shading
  solver also consumes saved internal boundary arrays. It does not yet turn
  source path IDs into verified physical features, cutting volumes, or
  dimensioned hidden sections. Some prepared views have altered pixels or
  unverified direction labels; their source relationship remains explicitly
  unresolved.
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
