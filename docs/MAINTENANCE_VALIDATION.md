# Maintenance validation — 2026-11-11

This qualifies the selected software contracts, not arbitrary reconstruction
accuracy. Code/configuration identity stayed unchanged during the final run.

- 39 registered checks ran across core, Blender and Godot; all passed, no skips.
- 158 pure unit cases and 18 Blender unit cases passed, alongside standalone
  guide/section/preflight/cutaway/reduction and known-shape geometry contracts.
- Godot: 39 unit checks and 45 smoke checks passed.
- Syntax and static source/configuration inventory parsing passed.
- Native storage fixture used a real cube bake/export/QA, checked selected-version
  loading, preserved original/prepared references, injected a station failure and
  restored the previous manifest while retaining the version.
- Storage tests injected copy failure, writer contention, input/payload changes,
  failed/uncertain QA, interrupted receipt completion and an intervening release.
  Idempotent publication, two retained versions and guarded rollback passed.
- Package tests verified committed bytes, excluded images/staged-only files and
  repeatable archive hashes. Optional CAD/OCR/neural profiles are not certified.

## Retained asset batch

The isolated batch rebuilt four existing fixtures without changing the production
library, ledger, report or reviewed `geometry_baseline.json`.

| Fixture | Comparison / disposition |
| --- | --- |
| Car | Pass; IoU .9734, 38,000 triangles, .079 folds/1k |
| Sofa | Pass after working-reference isolation; IoU .9236, 38,000 triangles, .211 folds/1k |
| Coffee maker | Fail comparison: 1.580 folds/1k versus .351 baseline + .5 allowance |
| Wall phone | Fail build QA: about 3% normal disagreement and 72% top-outline match |

The first sofa run exposed legacy guide cleanup mutating its inputs. The input
identity audit blocked that publication. Fresh raw/per-attempt reference copies
fixed the boundary; a second isolated sofa run passed with identical geometry
metrics. Both observations are retained. Coffee/wall-phone defects remain visible;
no geometry thresholds or baselines were weakened to make this maintenance pass.
Independent rebuilds using the pre-maintenance commit reproduced the coffee
metrics exactly and reproduced the wall-phone QA failures. These are inherited
geometry issues, not newly introduced by the storage/maintenance changes.
A passing candidate audit is distinct from passing a benchmark comparison.
The final renderer was also executed against the isolated sofa library and the
result inspected; labels correctly show missing ledger evidence as not recorded
instead of borrowing the latest build record for a different release.
The earlier carved-leg result still has the recorded 13 source-depth failures and
uncalibrated inverse-shading depths; this work does not claim to resolve them.

## Hosted repository audit

Public metadata reported 14 unprotected branches, no rulesets, a size of 737,585 KiB,
and no project license. Repository files prepare review routing, checks and runbooks;
they do not activate hosted branch/security settings. The original branches and
history remain in place. Weekly CI and the legacy collector change are proposed
on the review branch, not activated on the unchanged default branch.
