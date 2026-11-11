# Automatic depth and engineering evidence

The image-only `factory.py -- auto IMAGE --output DIRECTORY` path enables this
without per-image depth values. Existing orders are unchanged unless they enable
`automatic_depth`. No runtime LLM or external image-to-3D service is involved.

## Component thickness

`propkit/depth_inference.py` measures occupied spans in a companion side profile,
using its shared height axis to estimate physical thickness. Median spans prevent
thin mounting pins from dominating the estimate. Opposite profiles must agree
within 20%; conflicting or absent evidence uses an explicitly uncertain physical
prior. Clear profile evidence is not silently clamped to that prior: disagreements
are recorded and flagged. Size remains an estimate because absolute scale comes
from the existing sizing rules.

The generated parts order carries `depth_inference` evidence for each control:
source, profile observations, confidence, prior range and review status. These
depths feed actual geometry and the existing seating checks. Any depth warning
keeps the final automatic result at `needs_review`, even if coarse mesh QA passes.

## Surface relief

The existing `relief.py` segmentation, light estimation and displacement remain
the builders. A new selector compares their relief map, a broader smooth candidate
and flat paint using a positive lighting gain and explained shading variance.
Ambiguous/weak results remain flat. Separate front-mounted controls are excluded
from body relief; image edges and uncertain silhouette borders are excluded too.
Displacement is bounded to 2% of the smaller horizontal body dimension. Existing
surface-error simplification, final painting and triangle budgets still apply.

This is conservative shading-based inference, not measured depth or a learned
universal depth map. The relief candidate already contains raised/recessed regions
from the original module. The new selector does not override that module's
compact-region recess restrictions. This path keeps selected relief in geometry;
it does not create a partial high-resolution bake source for the joined assembly.

## Engineering outputs

`propkit/engineering.py` writes `engineering.json`: one node per part, inferred
boxes before seating, construction actually used, depth evidence, attachment
relationships and seating results. Positive dimensions and attachment graph
integrity are validated. Unobserved wall thickness, interiors and manufacturing
tolerances stay explicitly unknown; `production_ready` is false.

`technical-views.png` contains front/right/top silhouettes at a common scale and
three horizontal intersections with the finished exported mesh. These sections
describe the reconstruction, not the real object's unseen interior. They do not
add independent reconstruction evidence. There is no hidden-line elimination,
manufacturing CAD export, joint camera optimizer or general CSG search yet.

## Verification

`tools/test_depth_engineering.py` runs in normal Python; its additional signed
mesh displacement/cap test requires Blender. Nine tests under Blender cover
mounting pins, profile conflicts, prior conflicts, missing evidence, raised /
recessed / flat hypotheses, ambiguity, invalid constraints and actual plane/mesh
intersections. Existing intake, orchestration, geometry and Godot suites also pass.

The image-only blender trial produced 3,650 triangles, zero normal disagreement
and passed the existing mesh gate. Profile estimates were approximately 6–7 mm
for buttons and 18 mm for the knob. The lever disagreed with the available
button-derived prior and was correctly flagged. All body shading hypotheses were
too weak: no extra relief was added. A repeated run reproduced the geometry
signature. The known contradictory handle drawings and texture ghosting remain
unresolved by this change; the coarse legacy silhouette gate remains limited.
