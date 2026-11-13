# Hull factory operations

This is the operating contract. `checks.json` is the single test register;
`standards.json` owns existing asset thresholds. Existing `correction_review`,
`stage_review`, `qa`, `BuildMemory` and the source inventory retain their jobs.
The factory roles below are responsibilities, not a hierarchy of runtime LLMs.
The current task queue is the [Hull V2 GitHub issues](https://github.com/jaredwisnia-byte/Hull-V2/issues).
The twice-daily inspection and handoff routine is in
[`docs/MAINTENANCE_STEWARD.md`](../../docs/MAINTENANCE_STEWARD.md).
`ledger.jsonl`, `REPORT.md` and sealed run receipts record production evidence;
they do not assign the next development task.

| Responsibility | Existing machinery / new boundary |
| --- | --- |
| Operator | Intake and work orders; software performs reconstruction |
| Foreman | Correction review bounds each codified repair; retries are limited |
| Supervisor | Stage review carries uncertainty and unresolved failures forward |
| Inspector | Export QA checks geometry, normals, ownership and local evidence |
| Auditor | Warehouse rechecks artifact identity and publication eligibility |
| Maintenance | `hull.py doctor`, `check`, `qualify`, `audit` and regression fixtures |

## Standard work and containment

1. Receive inputs; preserve originals and assumptions. Record units and view frames.
2. Build under a fresh run ID. Each retry has its own attempt folder and working reference copy. Legacy
   guide cleanup cannot overwrite the archived raw copy or user inputs. Never bake
   a speculative result over the selected library version.
3. Measure the exported artifact. Keep proposals and rejections, including traces,
   height maps, stage reports, logs and work orders. A rejection is evidence for
   another bounded experiment, not a reason to flatten a surface silently.
4. Seal the candidate with QA, input/source hashes and payload hashes. The storage
   auditor checks required file containers and triangle counts independently of
   the QA disposition. It does **not** prove the reconstruction physically correct.
5. Only a passing, non-uncertain candidate can publish. `HULL_RELEASE_POLICY=hold`
   keeps qualified experiments outside the library. Normal builds preserve the
   previous automatic publication policy, now through this gate.
6. Copy into an immutable version directory; verify the copy; atomically replace
   the manifest pointer under an exclusive writer lock. Retain previous versions.

## Repair protocol

Contain the affected run, identify the first station that diverged, and compare
its input/output at recorded scale. State one hypothesis and one countermeasure;
measure against an unchanged fixture and a representative second object class.
Check both targeted improvement and protected properties: silhouette, local
relief, topology, texture ownership, triangle/error budget and elapsed time.
Keep losses as well as gains. Add a regression for the observed escape. Never
change a baseline, score definition or acceptance limit in the same undocumented
step as the repair it is supposed to judge. The existing memory records evidence;
it is not permission to accept previously failed output.

A useful incident record contains run ID, symptom, first failing station, likely
cause versus confirmed cause, countermeasure, test evidence, remaining risk and
next action. Record it with `python hull.py incident RECEIPT --hypothesis TEXT
--outcome TEXT --next-action TEXT`; it writes a new record without altering QA.

## Recovery

`python hull.py verify-release NAME` checks the selected payload hashes. Legacy
assets are reported as unqualified; the tool does not pretend to certify them.
`python hull.py rollback RECEIPT --expected-release RUN_ID` restores that
publication's saved previous pointer only if a newer release has not intervened.
Versions and evidence are retained. A legacy previous version is explicitly
unqualified. The first publication can be rolled back by removing its pointer.

If a process dies while publishing, inspect `publication.json`, the manifest and
payload hashes. The manifest is the commit boundary: a prepared journal alone
never proves publication. Repeating promotion is idempotent and can repair the
receipt after a completed pointer swap. If a writer lock survives a crash, first
confirm there is no active publisher, back up the lock and journal, then remove
only that stale lock. No tool silently clears another writer's lock.

A copy failure can leave an unselected `_pending_` directory. Retain it for
inspection; it is not a published version. No automatic garbage collection or
recursive deletion of experimental learning records is installed.

## Maintenance cadence

| Trigger | Work |
| --- | --- |
| Setup / toolchain change | Doctor: pinned imports, Python and required native tool versions |
| Every change | Syntax, repository policy and relevant registered tests; required CI core checks on all changes |
| Geometry / export / loader change | Blender contracts, Godot unit/smoke and isolated representative asset regression |
| Release / dependency or model upgrade | Full claimed capability qualification, benchmark comparison and rollback rehearsal |
| Weekly during development | Review recurring defects, failed/skipped checks, slow runs, storage growth and stale instructions |
| Monthly initially | Restore a known environment and a selected release; validate hashes and representative output |

The maintenance steward inspects at 03:00 and 15:00 America/Toronto. These
scheduled shifts supplement the change-triggered checks above; the weekly row
remains the deeper trend and recovery review.

Weekly CI checks are prepared in the workflow; GitHub schedules run on the default
branch once merged. Local/native recovery rehearsals remain operator tasks. These
cadences are starting policies, not claims of measured Six Sigma capability.
Do not automatically upgrade production dependencies or repeat every expensive
asset build after a documentation change.

## Qualification limits

A report names its selected capabilities; it never implies untested optional
features passed. CI qualifies core contracts, not Blender, Godot, OCR, CAD or
arbitrary-object depth. Current reference fixtures include known defects; a
baseline means a measured comparison, not a golden quality approval. Photo
brightness and a good-looking height map remain ambiguous about shape, lighting
and material. No administrative layer resolves that ambiguity by itself.

## Measured parts budgets

Both the current parts layout engine and older dictionary/attached assemblers
use shared measured surface-error reduction by default, before projection.
The limit remains fixed even if the model exceeds the triangle ceiling. Final
baking preserves a bounded result and leaves excess triangles for QA to flag.
The gauge is a bidirectional sampled 99th-percentile distance, not an exact
maximum or universal feature-recognition proof. Explicit budget: share remains
a compatibility option. Compare exported silhouettes and local features as well.

