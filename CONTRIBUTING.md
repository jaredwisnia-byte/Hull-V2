# Working on Hull

Read `KNOWLEDGE_FILE.md`, `long-lines/CLAUDE.md` and the factory operations guide
before adding machinery. Extend existing stations. Keep object-specific data in
orders and sizing rules, rather than creating another reconstruction pipeline.

## A reviewable change

State the defect, its reproduction, the changed behavior and its limits. Keep
numerical algorithms separate from Blender adapters, orchestration and storage.
Prefer small pure functions and descriptive names. Document units, coordinate
frames, input ownership, uncertainty and approximation budgets at boundaries.
Do not reorganize unrelated files just to meet a line-count target.

Run `python hull.py check --changed-files PATH ...` for a suggested check profile.
The complete required core suite runs on every push and pull request, including
configuration/dependency changes. Geometry, baking, library-loader and runtime
changes also need local `python hull.py qualify --blender PATH --godot PATH`.
Optional capability claims require their profile; skipped tests do not qualify it.
Source changes during a qualification must be rerun. Keep the qualification report.

For geometry changes also run `python long-lines/tools/diag/regress_assets.py
--blender PATH --output PATH` against available reference fixtures. The runner
copies inputs into a retained isolated sandbox. It never restores over the real
library or rewrites a golden baseline. A failed benchmark stays a failed benchmark.

Compare source, proposal, applied surface, exported mesh and simplified mesh.
A global silhouette score alone cannot validate a groove. Preserve failed
experiments and regression fixtures; do not lower thresholds to clear a check.
Review baseline proposals separately with reasons, fixture scope and known defects.

## Generalization gate for reconstruction features

Never fit a reconstruction feature, threshold or tool choice to one asset or
one reported defect. Do not branch on an object name to select geometry.
Object-specific measurements may live in an input order, but the inference rule
must operate from observable evidence and record uncertainty.

Before promoting a geometry feature, compare the same inputs before and after
on a mixed set: at least one planar manufactured object, one curved manufactured
object, one organic or carved object, and a negative control where the feature
must stay inactive. Include an object family not used to design the change.
Inspect source views, source-derived construction plan, clay renders, textured
renders, feature geometry, triangle counts and QA for every case. A pass on one
object, or an improved image-fit score with worse clay geometry, is a rejection.
Keep failed cases in the existing issue; do not open a new issue to relabel the
same failure or promote a prototype because its unit tests pass.

## Source-traced technical drawings

Produce construction drawings from the source views before building geometry.
Every observed line or curve in a drawing must retain its source view, source
pixel path, coordinate transform and tracing method. Display observed traces,
cross-view inferences and unknown geometry distinctly. A fitted primitive may
summarize a trace only when its deviation from that trace is measured and shown;
it must never replace or masquerade as the observation. Do not turn a circle,
shading mark or assumed object category into a protrusion, bore, cut or part
without independent cross-view support. The build must consume the recorded
construction constraints and report which ones it used or could not resolve.
Apply the mixed-object generalization gate above to both the drawing and the
resulting mesh.

Do not commit dependency folders, private run records, model weights, generated
imports or incidental library/ledger changes. Use explicit paths when staging.
Do not rewrite asset history or migrate everything to LFS as a cleanup shortcut.

Merge only after reviewing the final diff and checks. The repository owner should
require the `pure-python-contracts` check on protected production branches and
review changes to workflow, standards and baselines. CODEOWNERS requests review;
it does not itself enforce branch protection.
