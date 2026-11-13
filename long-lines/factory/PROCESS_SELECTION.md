# Construction process selection

Hull selects an envelope method from image evidence before construction. The
continuous signed-distance field is the base. A round end can select a lathe;
supported curved bands can select fitted sections; otherwise the field remains
unconstrained by a primitive. A separate local profile candidate may replace
one elongated span **after** depth fitting. It creates no physical part boundary.
The candidate still needs a field preflight and complete-build comparison before
adoption. `construction_mode: profile_trial` permits an isolated experiment.
No method is chosen from an object name.
An explicit construction setting in a work order still takes precedence and is
recorded beside the measured method.
The build record stores this base choice as `construction_methods`; its separate
`process_plan` records the optional local profile trial and any rollback.

## Early-station audit

| Station | Existing capability | Decision |
| --- | --- | --- |
| Legacy `factory.split_views` | Fixed first-row order and a border-colour blob threshold | Keep for old orders; do not use it to assign arbitrary new sheets. The image-only path already uses `sheet_blobs.automatic`. |
| Image-only `sheet_blobs.automatic` | OCR captions, section dividers, visual region matching, part graph, explicit unresolved state | Keep. Add independently scored view hypotheses when captions are absent or misread; never silently assign a view from sheet position. |
| `hull.silhouette` | One mask at a fixed colour-distance threshold, followed by component and hole rules | Keep as a mask proposal. Measure stability across thresholds before trusting a simple-shape fit; eventually retain competing masks and score their projected geometry. |
| `reconcile` / `preflight` | Size and orientation consistency checks | Keep as evidence inspection. It does not solve perspective pose, and automatic intake must not silently alter authoritative source views. |
| `profile_inference` / `construction` | Finds long tapered regions and can build a spline shaft | Reuse the region and envelope fit. It no longer rejects a whole image merely because its height-to-width ratio is below 2.5; the local span and cross-view evidence decide candidacy. Its older intensity-channel detector found no accepted grooves on the current leg, so it must not own all shaft detail. |
| `sections`, `revolve`, `hull`, signed field | Different shape representations already exist | Retain as specialist tools. Compare held-out outlines, local features, topology, folds, seams and triangle cost before accepting one over another. |

An image-only screen of 43 currently available front-and-side view sets found
29 continuous-field routes, 7 round-body lathe routes, 7 fitted-section routes,
and 5 local profile candidates (three leg sets, one coffee-maker handle and one
blender toggle). Before removing the whole-image aspect gate, only the three leg
sets were profile candidates. The profile count is **not** the count of assets
Hull can construct. All 43 had a base route. This corpus includes multiple
parts of the same assets and is not an independent generalization benchmark.
`tools/diag/screen_processes.py` records the full per-case evidence so this
screen can be rerun without tuning filenames or object categories.
The retained car, coffee-maker, sofa and wall-phone build regression produced
the same triangle counts, silhouette scores and fold rates before and after
this routing change. The car passes that regression; the other three retain
their pre-existing failures. Matching those metrics checks for new damage; it
does not turn the failed assets into qualified models.
The prebuild method record currently applies to the `hull` line with automatic
depth. Other Hull and assembly orders still use the existing automatic lathe
and sectional checks inside the builder; they have not been migrated to this
prebuild record. This change does not establish semantic part decomposition or
metric reconstruction from arbitrary photos.

## Routing contract

1. Choose the base envelope from the supplied views. A round end or front
   outline can support a lathe; corroborated bands can support sections; all
   other shapes keep the signed-distance field. These tools are already in
   Hull; the method planner records which one will run and reuses any sectional
   analysis in the actual build. Missing or conflicting evidence falls back to
   the field and is recorded.
2. Identify a region from more than one view. A long profile needs a sufficient
   span, a coherent shared axis and silhouettes stable under plausible mask
   thresholds. An unsupported region stays on the continuous field.
3. Fit the least complex plausible envelope. Solve local detail on the original
   field, then carry that displacement onto the candidate envelope so other
   views and neighbouring regions do not get re-solved against a changed base.
   Reject the candidate before a second export if it fragments or merges the
   baseline solid. This preflight is only a screen: the complete candidate
   still needs the stronger feature and export checks. On the current table
   leg, the proposed profile produced 306 component conflicts. The topology
   repair needed 50% detail retention, below the existing 80% minimum, so
   the profile was rejected before a second export. The ordinary local-detail
   retry then ran independently.
4. Blend geometry into one field across region boundaries. Distinct physical
   parts require independent part evidence, not just a curvature change.
5. Stop before baking if the dense candidate has more missing local features
   than the baseline. Then compare any surviving complete exported candidate
   with the baseline. No new missing
   features, topology, outline or fold failure is acceptable. Record both
   candidates and the reason for selection or rejection. The current export
   comparison also requires either fewer failures or at least 15% fewer
   triangles; missing features are matched by view and image location because
   generated probe IDs may change between builds.
6. Test the same rules on elongated and non-elongated objects. A routing rule
   that helps the table leg but wrongly converts an appliance handle, organic
   branch or camera body is not general enough for automatic release.

This is a deterministic routing stage, not a runtime LLM. It applies to Hull's
supported orthographic views; a single arbitrary photograph cannot determine
unseen geometry or absolute depth. Shape from shading remains an uncertain
relief estimate; a cleaner envelope cannot establish physical depth.

The hybrid approach is consistent with 2025 work on differentiable primitive
abstraction followed by image-guided mesh refinement
([JCST paper](https://jcst.ict.ac.cn/article/cstr/32374.14.s11390-025-5239-9)).
That paper motivates a candidate representation; Hull's own held-out views and
QA decide whether the candidate helps this asset.
