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
