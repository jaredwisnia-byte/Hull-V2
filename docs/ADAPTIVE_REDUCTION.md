# Adaptive parts reduction and deprecation audit — 2026-11-12

Existing screen-error reduction now governs parts_layout and the retained older
assembly dispatchers. Fixed tolerances replace automatic tolerance escalation.
The final baker respects bounded_surface_error and leaves ceiling conflicts for
QA, rather than forcing another 95%-of-ceiling decimation.

These are fresh software builds of existing fixtures, with unchanged reference
images and no manual geometry edits. Global pixel allowances are experiment
configuration, not per-object masks, crops or placement instructions.

## Exploratory sofa comparison

| Pixel allowance | Triangles | Mean silhouette IoU | Fold edges/1k | Benchmark |
| --- | ---: | ---: | ---: | --- |
| Previous build | 38,000 | .9236 | .211 | Pass |
| 0.5 | 13,628 | 0.9239 | 1.247 | Fail: fold rate |
| 1 | 6,644 | 0.9245 | 2.709 | Fail: fold rate |
| 2 | 3,358 | 0.9242 | 2.382 | Fail: fold rate |

The shared error gauge is bidirectional sampled 99th-percentile surface distance;
it is not a guaranteed maximum distance or independent semantic-feature proof.
The existing fold benchmark remains unchanged. Normalizing by triangle count
inflates rates as a model gets lighter, but the 0.5/1-pixel candidates also contain
more folded edges in absolute terms, so this cannot be dismissed as normalization.
These observations are retained; no new golden baseline or model approval was made.

Earlier invalid experiments are also retained: a missed legacy dispatcher left
38,000 triangles unchanged; parallel workers collided through shared tempfile
names; changed vertex-density sampling caused contact-check failures. Worker
TMP/TEMP/TMPDIR are now isolated. Dense contact witnesses are retained before
reduction and checked against both the resulting part and its neighbor. A native
regression deliberately detaches a foot to ensure this cannot hide missing support.

## Archive audit

The unrelated root web application and collector move to deprecated/midnight-watch.
An active-runtime/workflow reference search found no Hull/Godot consumers. Its
workflow is outside .github/workflows and cannot execute on this branch. Historical
commits and original model assets remain intact. Main/default-branch cleanup takes
effect only after review and merge; this work does not silently merge feature code.

The proportional share option remains in code as deprecated compatibility behavior.
Dynamically dispatched reconstruction engines, sizing tools, fixtures and optional
backends were retained. Static non-use alone does not prove safe removal.
DESCRIPTION.md and the Hull README describe the actual software. Hosted About
metadata could not be changed: no connector setter is exposed and the available
browser is signed out. This does not prevent pushing the source cleanup.

## Final verification

All 39 registered core/Blender/Godot check groups passed with unchanged source
and no skips. The contact regression and bounded final-bake tests pass. A fresh
1-pixel build using the final two-sided contact check exports 6,644 triangles,
IoU .9245, zero open edges and zero degenerate triangles. Its contact checks pass.
Its fold benchmark still fails at 2.709/1k (about 18 folded edges versus 8 before).
The run remains held outside the selected model library. No benchmark limits
or golden baselines were changed.

Cross-object qualification of the new default beyond the sofa remains necessary;
passing software contracts does not certify every retained assembler output.
