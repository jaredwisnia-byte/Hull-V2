# Structural tracing and provisional fine curves

Hull can use the published **MatchED BIPED (CVPR 2026)** edge model for structural
image boundaries. A separate Kovesi phase-congruency layer retains fine candidate
curves. Neither layer directly assigns depth, creates physical parts, or proves a
groove. Green/orange still indicate colour-change evidence, not acceptance or
geometry confidence; cyan indicates provisional phase evidence.

## Existing pipeline, new boundary evidence

`feature_regions.trace` can select the registered local backend automatically
when explicitly requested with `HULL_TRACE_BACKEND=auto` or `matched`. The
structural layer feeds the existing watershed/grouping and relief-fitting pipeline.
Recognized boundaries receive protection from weak-boundary merging. Phase
candidates do **not** split regions: they weakly relax curvature regularization in
`joint_shading`, with the existing numerical fitting and validation still active.

Connected skeleton paths are exported separately as `structural_paths` and
`provisional_fine_paths`. Cubic B-splines are used only when sampled bidirectional
deviation is at most 0.75 analysis pixels and endpoint error at most 0.01 pixels.
Otherwise the connected polyline remains. No straight bridges are invented across
disconnected fragments. These are **2D evidence curves**, not recovered 3D CAD
edges or a continuous mathematical error certificate.

The model receives the existing foreground mask and foreground colours supplied
by the fitting path (whose reserved pixels are already removed),
converted from linear RGB back to byte sRGB. The outside-mask area is neutral black,
not the nearest-filled image used by numerical fitting. This prevents background
colour extension from creating artificial stripes. No asset-specific groove mask,
object vocabulary, placement instruction or LLM call is used by this tracer.

## One-time local setup

Third-party source, weights, dependencies and trace cache are kept in gitignored
`.hull-models/`. They are deliberately not distributed in Hull's repository.

Official project/paper: https://cvpr26-matched.github.io/

Official source: https://github.com/Bedrettin-Cetinkaya/MatchED

Verified source revision: `cf12ad80d0a9f7088964741226a15a0475d37a2d`.
Use the official published checkpoint archive linked by that repository and its
`pidinet/biped/checkpoint_013.pth` member. The expected SHA-256 is
`bb2e6074cc35e04549c2924dc0e3aecb934b52788e319f4596b04dfa9963bbba`.
The BSDS checkpoint is a different model and is not interchangeable.

Create a dedicated Python environment and install CPU PyTorch, NumPy, SciPy,
scikit-image, Pillow and phasepack. Then run:

```text
python long-lines/tools/configure_tracing.py --python PATH_TO_ENV_PYTHON --source PATH_TO_OFFICIAL_MATCHED --checkpoint PATH_TO_BIPED_CHECKPOINT
```

For a directory-based dependency installation, repeat `--python-path DIRECTORY`
as required. Setup verifies six official source files and the checkpoint before
copying them locally. The configuration records package versions and metadata
checksums. Reconstruction verifies registered artifacts and the worker's observed
versions. The published constructor's hard-coded CUDA allocation is intercepted
only during CPU construction; model layers, weights, normalization and forward
operations are unchanged. Hull's own adaptation is visible in `tracing_worker.py`.

The tested local worker uses Python 3.13.13, Torch 2.15.0+cpu, NumPy 2.5.4,
SciPy 1.18.1, scikit-image 0.26.0 and phasepack 1.5. Phase congruency is a classical
algorithm, not a new 2026 model. The Blender process never imports PyTorch; it calls
an isolated local CPU worker. No model download, network request or LLM service is
performed during reconstruction.

## Selection, failure and reuse

The default remains `HULL_TRACE_BACKEND=classical`: the end-to-end trial below
does not justify replacing the existing production path. Explicit `auto` uses a
configured model; a missing
registry explicitly reports classical fallback with `reason=model_not_configured`.
`matched` requires the model and fails if setup is missing. `classical` explicitly
selects the original tracer, useful for controlled comparisons and old contracts.
`HULL_TRACE_CONFIG` selects another registry. Invalid registered artifacts and
worker errors fail visibly rather than silently changing the algorithm.

The exact byte input, foreground mask, versions, artifacts and worker/adapter code
identify cached tracing outputs. Cache receipts include packet checksums; damaged
packets are recomputed. Reconstruction memory also includes the tracing identity
and relevant solver source. Cached edges cannot silently reuse old relief fits
after a model or solver change.

Diagnostics retain structural scores, phase scores, both masks, connected paths,
backend identity and cache provenance. The legacy export path remains readable.

## End-to-end promotion gate

The fixed synthetic tracing experiment favored MatchED BIPED, and the production
worker detected the weak horizontal-curve control while returning no blank-image
structure. A paint-only control returned two structural pixels but 2,976 fine
candidate pixels: the latter must remain provisional.

The fresh leg build completed without per-object assistant edits, using the existing
sheet preset rather than demonstrating fresh automatic view recognition. It has
20,964 triangles and one connected component. Its own source-depth checks fail
109/206 probes. A controlled check using **the previous run's same 200 probes**,
with each export's recorded manufacturing translation, reproduces the previous
97 failures and finds 111 failures on the new model. The previous model had 18,064
triangles. The new front's final reserved-pixel appearance gain is -6.619%, flagged
for review; source-derived depths remain uncalibrated. A cleaner 2D trace has not
yet improved 3D fidelity. Do not promote this backend by silently changing defaults
or weakening geometry checks. The structural/region-fitting/mesh handoff needs
further controlled work. Better edge-detection metrics alone are insufficient.

## Scope of the CAD drawings

`propkit.engineering.export` already exports `technical-views.png`: common-scale
front/right/top silhouettes, labelled hatched mesh sections and cutting-plane
markers. `engineering.json` records measured envelopes and unresolved production
information; `surface-cutaway.glb` is an uncapped inspection mesh. The image build
pipeline calls this exporter after reconstruction when automatic depth is enabled.

These drawings inspect the **finished mesh**. They do not independently infer
hidden construction from photographs, draw a general hidden-line/dimensioned
production drawing, or establish unknown wall thickness. Optional STEP output is
trimmed spline surface charts, not a certified closed manufacturing solid. The
new tracing curves do not change those limitations.
