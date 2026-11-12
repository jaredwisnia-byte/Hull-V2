# Correction supervision

Hull already had a deterministic **end-of-build** stage review. That review
reported damage but did not supervise every correction before it was applied.
`propkit.correction_review` adds a shared pre-application contract: the triggering
problem must measurably improve, and every declared preservation budget must pass.
Missing, non-finite or out-of-budget evidence rejects the candidate. A software
check is not an LLM, semantic understanding, or physical-depth certification.

## Current coverage

- **Field connectivity.** Keep the dominant overlapping remnant of every original
  physical component, including originally tiny components. Only detached extra
  fragments of at most eight field cells may be removed automatically, and their
  total must be at most 0.1% of the original solid. Distinct original components
  must remain distinct. Larger splits/merges cannot be disguised as speck removal.
  Global backoff must retain at least 80% of the proposed relief; a 50% or total
  attenuation is rejected instead of silently flattening the whole asset.
  Newly enclosed air pockets of the same grid-scale size receive the symmetric
  check: fill only new pockets, preserve original cavities and open grooves, and
  cap filled volume at 0.1% too. This prevents invisible one-cell air bubbles from
  becoming disconnected inner mesh shells. Large cavities are not silently filled.
- **Mesh reduction.** Every disposable candidate is checked for sampled surface
  error in both directions and all existing protected contrast constraints. A
  failed coarse mesh may retry with local protection around its failed features.
  Those constraints preserve existing dense triangles; they do not sculpt new
  points or choose object-specific shapes. Failed viewing-ray hits supply extra
  witnesses when a coarse face occludes a groove. Retries stay at the coarse level
  while they make progress, then try a less aggressive level, within six attempts.
  Rejected candidates are discarded.
  The original passing search result remains the fallback.
- **Automatic-depth retry assumptions.** A failed outline/opening gauge no longer
  authorizes dropping a carving view or filling all holes. That semantic change
  requires independent evidence. Unsupported retries are blocked and reported.
- **Reporting.** Before/after measurements, safeguard ranges, failure locations,
  decisions and reasons are retained in topology/reduction reports. A blocked
  correction reaches the factory result and end-of-build stage review.
  Independent diagnostics also report depth-bound saturation and proposal-to-field
  transfer gain; these are representation checks, not physical-depth measurements.

The numbers above are explicit numerical-preservation policies, not recovered
physical dimensions. Eight cells corresponds to a grid-scale fragment, not a
universal minimum part size. Original tiny parts are protected by component
ownership. Surface and contrast tolerances retain the existing screen/error
budgets; a more attractive preview cannot override them.

## Verified failure that motivated this

The recorded leg's full-strength target had one main solid of 19,236,666 cells
and 25 detached fragments containing only 28 cells in total, plus four newly
enclosed one-cell air pockets. The old component
count check halved relief across the entire object. Local fragment removal keeps
full-strength detail and one solid. This is a representation repair, not newly
inferred carving depth. Controlled fixed-input and full-build results belong in
the knowledge file; different probe populations must not be compared directly.

## Limits and further coverage

This is the beginning of an in-process supervisor, not a claim that every stage
has equivalent contracts. Reference fitting, camera calibration, view recognition,
texture decisions and legacy recipe retries still need their own appropriate
measurements and transaction boundaries. The end reviewer does not inspect render
pixels or infer hidden construction. An unresolved major correction is flagged;
it must not be silently "fixed" by weakening QA or inventing geometry.

Research background: [quadric surface simplification](https://www.cs.cmu.edu/~garland/quadrics/)
supports allocating detail according to geometric approximation error. The 2026
[Dual Contouring of Signed Distance Data](https://arxiv.org/abs/2604.00157) is a
potential future extraction method; it has **not** been implemented here and would
still require topology, silhouette and local-feature validation.
