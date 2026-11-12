# Construction process selection

Hull should select a construction method for each supported region, using image
evidence and a complete-build quality comparison. Object names may suggest
candidates but must not decide geometry. The first candidate in this branch is
an elongated, jointly observed profile: a smooth fitted shaft envelope is
combined with the original field's local relief **after** depth fitting. It creates no
physical part boundary. A failed normal build may try this candidate when
the profile evidence is strong and a field preflight preserves the baseline's
solid topology. Hull compares the complete exported assets and
rolls back if quality worsens. `construction_mode: profile_trial` also permits
an isolated experiment without altering the ordinary build's initial choice.

## Early-station audit

| Station | Existing capability | Decision |
| --- | --- | --- |
| Legacy `factory.split_views` | Fixed first-row order and a border-colour blob threshold | Keep for old orders; do not use it to assign arbitrary new sheets. The image-only path already uses `sheet_blobs.automatic`. |
| Image-only `sheet_blobs.automatic` | OCR captions, section dividers, visual region matching, part graph, explicit unresolved state | Keep. Add independently scored view hypotheses when captions are absent or misread; never silently assign a view from sheet position. |
| `hull.silhouette` | One mask at a fixed colour-distance threshold, followed by component and hole rules | Keep as a mask proposal. Measure stability across thresholds before trusting a simple-shape fit; eventually retain competing masks and score their projected geometry. |
| `reconcile` / `preflight` | Size and orientation consistency checks | Keep as evidence inspection. It does not solve perspective pose, and automatic intake must not silently alter authoritative source views. |
| `profile_inference` / `construction` | Finds long tapered regions and can build a spline shaft | Reuse the region and envelope fit. Its older intensity-channel detector found no accepted grooves on the current leg, so it must not own all shaft detail. |
| `sections`, `revolve`, `hull`, signed field | Different shape representations already exist | Retain as specialist tools. Compare held-out outlines, local features, topology, folds, seams and triangle cost before accepting one over another. |

The image-only routing screen was also checked against the current leg,
blender, television, sedan, wall-phone handset, blender jar and sofa foot.
Only the leg passed the long-profile image checks. The handset had an apparent
profile but opposing side widths disagreed by 12.1%, beyond the 10% gate.
The remaining examples did not show a jointly supported elongated profile.
These seven cases check accidental routing; they do not establish universal
object recognition.

## Routing contract

1. Identify a region from more than one view. A long profile needs a sufficient
   span, a coherent shared axis and silhouettes stable under plausible mask
   thresholds. An unsupported region stays on the continuous field.
2. Fit the least complex plausible envelope. Solve local detail on the original
   field, then carry that displacement onto the candidate envelope so other
   views and neighbouring regions do not get re-solved against a changed base.
   Reject the candidate before a second export if it fragments or merges the
   baseline solid. This preflight is only a screen: the complete candidate
   still needs the stronger feature and export checks. On the current table
   leg, the proposed profile produced 306 component conflicts. The topology
   repair needed 50% detail retention, below the existing 80% minimum, so
   the profile was rejected before a second export. The ordinary local-detail
   retry then ran independently.
3. Blend geometry into one field across region boundaries. Distinct physical
   parts require independent part evidence, not just a curvature change.
4. Stop before baking if the dense candidate has more missing local features
   than the baseline. Then compare any surviving complete exported candidate
   with the baseline. No new missing
   features, topology, outline or fold failure is acceptable. Record both
   candidates and the reason for selection or rejection. The current export
   comparison also requires either fewer failures or at least 15% fewer
   triangles; missing features are matched by view and image location because
   generated probe IDs may change between builds.
5. Test the same rules on elongated and non-elongated objects. A routing rule
   that helps the table leg but wrongly converts an appliance handle, organic
   branch or camera body is not general enough for automatic release.

This is a deterministic routing stage, not a runtime LLM. Shape from shading
remains an uncertain relief estimate; a cleaner envelope cannot establish
unseen physical depth.

The hybrid approach is consistent with 2025 work on differentiable primitive
abstraction followed by image-guided mesh refinement
([JCST paper](https://jcst.ict.ac.cn/article/cstr/32374.14.s11390-025-5239-9)).
That paper motivates a candidate representation; Hull's own held-out views and
QA decide whether the candidate helps this asset.
