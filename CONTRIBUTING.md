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

Do not commit dependency folders, private run records, model weights, generated
imports or incidental library/ledger changes. Use explicit paths when staging.
Do not rewrite asset history or migrate everything to LFS as a cleanup shortcut.

Merge only after reviewing the final diff and checks. The repository owner should
require the `pure-python-contracts` check on protected production branches and
review changes to workflow, standards and baselines. CODEOWNERS requests review;
it does not itself enforce branch protection.
