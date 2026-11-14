# Repository maintenance audit — 2026-11-11

Scope: Hull V2 and its existing `feature/automatic-sheet-intake` review branch.
Original Claude/Dirac sources, production branches and historical experiments
are preserved. Cleanup concerns operational boundaries and discoverability;
it does not claim new reconstruction accuracy.

## Findings and countermeasures

| Finding | Countermeasure |
| --- | --- |
| Root introduction described an unrelated application | Hull front page; the unrelated application was removed |
| Floating action tags and unpinned Python dependencies | Verified full action commit IDs; qualified core dependency pins |
| Path-filtered checks skipped changes to other configuration | Required core workflow on every push/PR |
| Different local and CI Python versions | Explicit Python 3.13 profile and native capability declarations |
| Candidate exports entered the library before QA | Isolated attempts, sealed receipts, immutable selected releases |
| Regression runner restored over production state and deleted failures | Retained isolated sandbox; observed baseline proposals only |
| Tests scattered across workflows | One check register and a common local/CI entry point |
| No clear review/recovery handoff | Contribution guide, owners, templates, runbooks and rollback |
| Asset-heavy repository (~720 MiB reported by GitHub) | Code-only reproducible package; inventory large tracked files; no history rewrite |

## Hosted audit and settings still requiring action

The public GitHub API audit found 14 branches, all reporting `protected: false`,
and an empty ruleset list. The repository reports 737,585 KiB and no license.
These are dated observations, not server settings changed by this work.

Files cannot enforce GitHub branch protection. Review required checks, review
requirements, stale approval dismissal, force-push/deletion restrictions, secret
scanning and private vulnerability reporting in repository settings. Avoid a
`pull_request_target` workflow that executes untrusted PR code. CODEOWNERS is a
routing hint until hosted review rules enforce it. No server-side enforcement is
claimed by this change. No releases, tags, branches or assets are deleted.

Before selecting a license, confirm ownership and third-party/image rights with
the owner; do not insert an arbitrary permissive license. Consider LFS or an
external artifact store for future large generated assets after compatibility,
backup and migration review. This change does not rewrite existing history.

## Continuing work

- [x] Audit repository layout, workflows and local publication boundary.
- [x] Prepare docs, check register, pinned CI, reviewed dependency update proposals.
- [x] Add qualified publication, integrity verification and guarded rollback.
- [ ] Owner verification of hosted branch/security settings and license choice.
- [ ] Broader independent object benchmark corpus and physically calibrated depth.
- [ ] Clean-install qualification for optional OCR, neural and CAD profiles.

## Sources and rationale

The design applies bounded containment and visible abnormalities from
[Toyota TPS](https://global.toyota/en/company/vision-and-philosophy/production-system/),
small reviewable improvements from [Google engineering practices](https://google.github.io/eng-practices/review/reviewer/),
and least privilege plus pinned actions from [GitHub secure use](https://docs.github.com/en/actions/reference/security/secure-use).
These are adaptations to this codebase, not claims that Hull implements a
manufacturer's complete system or has reached a statistical capability level.
The earlier factory study covered GE/FLIGHT DECK, Ford, Mitsubishi and Seeed's
validation practices; none justifies adding another runtime management hierarchy.

The [full factory research record](research/FACTORY_PRACTICES.md) preserves the
company-specific sources, dates and limits behind these recommendations.

## Follow-up archive audit — 2026-11-12

The unrelated web application and the Godot game were removed from this
repository on 2026-11-13; their history remains in Git. DESCRIPTION.md explains the current software. Hosted About metadata is separate:
the connector has no repository-settings mutation and the browser is signed out.
No claim is made that hosted About/default-branch content changed.

Dynamic reconstruction modules, sizing tools and fixtures remain active. The
old proportional budget policy is deprecated but retained for explicit older
orders; unused-looking imports alone do not justify deleting dynamic engines.

## Branch and documentation cleanup — 2026-11-14

Goal: one obvious place for current code (`main`) and for the directives and
architecture, with nothing lost. Codex was running the architecture orders
(`CODEX_ORDERS.md`) at the time and reads `AGENTS.md`, `CONTRIBUTING.md`,
`long-lines/docs/ARCHITECTURE.md` + `architecture.json`, `long-lines/factory/DRAWING.md`
and `long-lines/docs/LESSONS.md` from the main checkout at the start of every order, so
those files were not moved or edited; that part of the plan waits for the run to finish.

### Done

1. **Gate before moving `main`.** Codex Order 1 regression check passed (no drawn-set
   asset worse; wall phone top-view IoU 0.705 -> 0.816 from the third-angle frame fix).
   The tested commit and the new `main` differ only in two architecture documents.
2. **Archive tags first.** The old `main` (2026-11-09, still carrying game files) is
   `archive/main-2026-11-09`. Every branch with commits found nowhere else got an
   `archive/<branch>` tag, each checked on GitHub against its branch tip before
   deletion (16 tags):
   `archive/main-2026-11-09`, `archive/main-before-trusting-dirac`,
   `archive/experiment/orthographic-component-reconstruction`,
   `archive/feature/hull-v2-component-pipeline`, `archive/claude/factory-v1-assembly`,
   `archive/chatgpt/factory-v1-package-contract`, `archive/chatgpt/sheetfirst-panels-v1`,
   `archive/chatgpt/sheetfirst-toaster-assembly-test`, and
   `archive/codex/{godot-cold-import, maintenance-handoff, trace-frame-mapping,
   workspace-root-file-inventory, retention-manifest, cad-qualification,
   local-depth-transfer-audit, workspace-inventory}-20261113`.
3. **README "Read first" index** linking the directives, the architecture (human and
   machine-readable), LESSONS, the factory manual, the drawing guide and status.
   `docs/SYSTEM_ARCHITECTURE.md` (2026-11-13 proposal) marked superseded; content kept.
4. **`main` fast-forwarded** to `claude/object-aware-sizing` (no force push).
5. **31 remote branches deleted**: 16 already fully contained in `main`, 15 archived
   above. Remaining: `main`, `claude/object-aware-sizing` (working branch),
   `codex/read-only-memory-inventory-20261114` (new that day, possibly a live job; left).

To restore an archived branch: `git push origin refs/tags/archive/<name>^{commit}:refs/heads/<name>`.

### Waiting for the Codex run to finish (after Order 10)

Steps 1-3 (except the Codex orders, which live outside the repo) are prepared on
branch `claude/docs-layout`, to merge into `main` once the run ends.

1. Move `long-lines/docs/ARCHITECTURE.md` and `architecture.json` to root `docs/`,
   leaving one-line pointers at the old paths; update the README links.
2. Point `AGENTS.md`'s current priority at the architecture and its migration steps.
3. Update paths in the Codex orders and in `architecture.json` (`human_doc`, `branch`).
4. Review Codex's `codex/architecture` work, merge it into `main` after its gates, then
   delete the branch (tag it first if anything is not merged).
5. Decide `codex/read-only-memory-inventory-20261114`: merge, archive as a tag, or delete.

### Keeping it tidy

- `main` is the current, tested code; README "Read first" is the entry point.
- One branch per piece of work, merged into `main` after its gate, then deleted.
- A branch that will not be merged is kept as an `archive/...` tag, never as a branch.
- Superseded documents get a banner pointing at their replacement instead of being
  silently left to disagree.
