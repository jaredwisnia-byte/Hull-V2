# Hull maintenance steward

## Purpose and boundary

The steward runs at 03:00 and 15:00 America/Toronto each day. It coordinates
existing Hull checks and reusable specialist subagents. The subagents are
transient workers with assigned routines, not eleven permanently running
processes. At most three specialists work alongside the steward in one shift.
No shift rebuilds the asset library just to measure its health.

The November 13 storage and code review at
`C:/Users/jared/Documents/Codex/Hull-maintenance-validation/HULL_STORAGE_CODE_REVIEW_2026-11-13.md`
is the initial local baseline.

## Operating rules

- Detect an abnormal condition, contain its effects and preserve evidence.
  A warning permits safe diagnostics to continue; a failed integrity or quality
  gate blocks publication of the affected candidate. This adapts Toyota's
  [jidoka and Andon](https://global.toyota/en/company/vision-and-philosophy/production-system/)
  to Hull's release boundary.
- Use standardized inputs, measurements and handoffs. Change one cause at a
  time, compare with a stable baseline and retain the before/after evidence.
  Follow [ASQ DMAIC](https://asq.org/quality-resources/dmaic) as a problem-solving
  sequence, not as a claim that Hull has measured Six Sigma capability.
- Separate routine inspection from specialist repair, following
  [JIPM's TPM model](https://www.jipm.or.jp/business/tpm/). The steward collects
  facts; a specialist takes a bounded investigation when evidence warrants it.
- Alert on new, actionable symptoms and regressions. Record expected versus
  actual behavior, first failing station, reproducible inputs and the affected
  release before choosing a repair. Follow [Google SRE monitoring](https://sre.google/sre-book/monitoring-distributed-systems/)
  and [troubleshooting](https://sre.google/sre-book/effective-troubleshooting/).
- Every material defect has one owner, severity, tracked action and verified
  closure. Avoid duplicate tickets and routine success notifications. A code
  change must improve overall code health, with suitable tests and readable
  design, per [Google's review standard](https://google.github.io/eng-practices/review/reviewer/standard.html).

## Shift routines

### 03:00 — inspection and containment

The steward reads the last report and starts up to three existing specialists:

1. `hull_inventory_audit`: measure accessible logical bytes and free disk space;
   classify growth; check SQLite and checkpoint references read-only. Compare
   the exact access-denied path set with the prior inventory. Never instantiate
   `BuildMemory` for this audit, because its constructor and load path write.
2. `quality_warehouse_learning`: inspect only newly selected or changed releases
   and sealed receipts. Verify identity, hashes, containers, quality disposition
   and selected manifest pointer. A matching hash does not establish correct
   geometry. Never promote, roll back or clear a publisher lock during inspection.
3. `agent_inventory`, only when schedules, test registration or CI changed:
   compare test files with `checks.json`, the default-branch workflow and local
   automation settings. Report coverage gaps rather than calling skipped work a
   pass.

Run `hull.py audit` and `doctor`. Run cheap, relevant contracts only when source,
configuration or dependency identity changed. Record unavailable capabilities.
Quarantine an affected release candidate only through existing gates; do not
rewrite a stored receipt. Write immutable evidence under
`C:/Users/jared/Documents/Codex/Hull-maintenance-validation/steward/storage-audit/<UTC-run-id>/`.
Do not overwrite earlier evidence.

Initial operational triggers are **provisional policies**: critical disk space
below the greater of 10 GiB or 5%; warning below the greater of 25 GiB or 10%;
warning for unexplained Hull-owned growth over 1 GiB or 10% in twelve hours;
review above 5 GiB. Any failed SQLite quick check, confirmed missing referenced
checkpoint, digest mismatch or changed qualified payload is an integrity failure.
Unreferenced checkpoints are reported, never collected automatically. Record
database, WAL and SHM sizes; do not run `VACUUM` or a checkpoint. A partial scan
or newly inaccessible path yields degraded coverage, not a clean pass.

### 15:00 — foreman review and controlled improvement

Review new failures and changes since 03:00. Sort actionable defects by user
impact, recurrence and affected releases. For one selected issue, identify the
first failing station, state one hypothesis and test one countermeasure against
the failing asset and a different object family. Keep the old result and a
regression test. Do not change an acceptance threshold with the repair it is
supposed to judge.

Call `geometry_validation` only for a **new finalized build**, identified by
run ID and source, work-order, toolchain and artifact hashes. Do not infer a
new build from modification time alone. Skip active runs and unchanged assets.
Inspect recorded QA, full-view silhouettes and openings, local features,
owner/attachment counts, texture-source evidence, mesh folds and triangle
error. Use existing textured and clay views; create close-ups only for a new
defect or missing evidence. Do not rebuild, qualify or promote to perform a
review. Escalate specialized defects to `hull_mesh_pipeline_research`,
`hull_curves_research` or `engineering_inference` only when that class of
evidence is present.

Review source changes with relevant tests. A small reversible fix may be made
on an isolated `codex/` branch with a focused regression and a reviewable diff.
Do not merge, publish, rewrite history, reset unrelated work or delete data.
If a release is affected by a failing gate, preserve evidence and hold that
publication. Continue safe diagnostic work.

## Longer-cycle routines and specialist roster

| Specialist | Trigger | Output |
| --- | --- | --- |
| `hull_inventory_audit` | Every 03:00; 15:00 delta if material growth | Storage and SQLite evidence, coverage and changed findings |
| `quality_warehouse_learning` | Changed release/receipt; weekly recovery review | Publication integrity and release-gap report |
| `geometry_validation` | New finalized model | Exported-asset geometry and appearance QA review |
| `agent_inventory` | Workflow/test/agent changes; weekly | Missing coverage and schedule drift |
| `hull_mesh_pipeline_research` | New mesh or triangle regression | Matched-asset root-cause experiment |
| `hull_curves_research` | New groove/curvature failure | Local feature evidence and countermeasure test |
| `engineering_inference` | Camera, part or depth ambiguity | Competing hypotheses and validation plan |
| `factory_floor_practices` | Monthly process review | Standard-work improvement proposal |
| `operating_practices_report` | Weekly defect review | Recurrence Pareto, owners and overdue actions |
| `factory_standards` | Quarterly primary-source check | Changes to relevant factory practice |
| `software_standards` | Quarterly primary-source check | Changes to code, CI and incident practice |

Weekly: run full supported core and native contracts in a controlled runtime;
review recurring defects, skipped checks, storage trends and one recovery
scenario. Monthly: verify a selected immutable release from a clean environment
and rehearse guarded rollback in a disposable library. Broader tests run less
often than fast change-triggered checks, in line with
[Apple's test cadence](https://developer.apple.com/xcode-cloud/).

GitHub scheduled workflows are an additional signal, not the sole clock:
they run from the default branch and may be delayed or dropped under load
([GitHub documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)).

## Escalation and release gap

Hull already has candidate QA, immutable warehouse versions and rollback
guards. The current automatic promotion path does **not** bind a passing,
matching capability qualification to the candidate. Until that code gap is
resolved, the steward reports it and keeps uncertain experiments under the
existing hold policy; it does not claim that artifact integrity proves a
physically correct model. Incidents should gain owner, severity, status,
affected versions, reproducer and verified closure evidence. Follow
[Google's postmortem practice](https://sre.google/workbook/postmortem-culture/)
for escaped or recurring defects.

