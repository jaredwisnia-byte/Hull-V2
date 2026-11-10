# Automatic reference-sheet build

One structured reference image runs through local vision, the original Trusting
Dirac parts builders, baking, the existing quality gate, standalone export and
turnaround rendering. No conversational/generative LLM runs in this pipeline.
The only per-object argument is the image path; no supplied crop boxes, part
inventory, corrected OCR, dimensions or mounting coordinates are required.

## Run

Install `requirements-vision.txt` from the repository root into Blender's Python.
For example, on this Windows installation:

```powershell
& 'C:\Program Files\Blender Foundation\Blender 5.2\5.2\python\bin\python.exe' -m pip install -r requirements-vision.txt
& 'C:\Program Files\Blender Foundation\Blender 5.2\blender.exe' -b --factory-startup --python-use-system-env --python-exit-code 1 -P long-lines/tools/factory.py -- auto reference.png --output output_directory
```

The first run downloads local OCR weights and the pinned DINOv2 ONNX model.
Later inference processes images locally. `HULL_VISION_MODEL` can point to an
already downloaded model; its SHA-256 must match the checksum in
`tools/propkit/vision.py`. Keep `PYTHONHASHSEED=0` when comparing geometry gauges
across processes. Blender's UV packer can vary; export bytes need not match.

## Supported input and limits

This initial automatic assembly grammar supports captioned orthographic sheets
for a vessel appliance: one jar/cup/container, an optional collar/base/housing,
an optional lid, repeated buttons, knobs and a toggle/lever. It requires assembled
front, back, left, right and top captions and separated part drawings. Unknown
part roles, missing directions and unsupported control mounting directions flag
the input instead of silently building a guessed inventory. This is not a
general ordinary-photo-to-any-object system. Caption vocabulary supplies semantic
roles; learned vision supplies correspondence alongside shape/colour evidence.

Absolute dimensions cannot be recovered from these drawings alone. Scale uses
the existing physical button-size prior (or hand-width fallback), explicitly
recorded as an estimate. Hidden lid/collar faces use recorded geometry hypotheses.
The reconstruction remains a textured surface model; optical glass and unseen
internal machinery are not inferred. A 2K bake does not add detail absent from
a low-resolution source drawing.

## Processing

1. `sheet_blobs.py`: OCR reads captions; foreground regions supply drawing bounds.
   Perspective evidence is retained but excluded from silhouette carving.
2. `propkit/vision.py`: DINOv2 dense features and affine RANSAC match detached
   drawings to assembled views. Constrained photometric refinement locates large
   parts. Appearance/shape proposals detect compact controls and repeated rows;
   the number of buttons comes from the image.
3. `propkit/vision_order.py`: joint assignment gives distinct companion views to
   directions. Observed stacked boundaries separate vessel, support, lid and
   residual body. It writes the existing `hull_parts`, `layout: parts` work order.
4. Original parts-layout, hull, sizing and part-rule modules manufacture each
   piece. Generated physical boxes enter through `locate: vision`; existing
   ray-based seating checks enforce attachments. Surface-error budgets and
   simplification remain active. Normals refresh after simplification.
5. Original bake and QA run. QA compares the complete assembly reference folder,
   including five silhouettes; missing comparisons fail automatic orders.
   No acceptance thresholds are relaxed. Existing correction/review handling stays.
6. `export_textured` packages baked maps into standalone GLB and BLEND files
   without changing geometry. The original turnaround renderer creates the PNG.

## Outputs and status

- `result.json`: status, input SHA-256, elapsed seconds, assumptions, QA and paths.
- `model.glb`, `model.blend`: standalone baked model.
- `<asset>.png`: textured orthographic/perspective views plus a clay view.
- `intake/intake-report.json`, `detected-regions.png`, `region_*.png`: recognized
  captions, bounds, match evidence, used drawings and unresolved assignments.
- `intake/manufacture/work-order.json`, `vision-report.json`, `source/`: generated
  manifest, physical scale/pose evidence and source crops.
- Normal factory orders, assets and ledger entries are also written by the
  existing builder inside the checkout.

Exit 0 / `complete` requires successful QA and rendering. Exit 2 / `needs_review`
flags unresolved intake or failed build/QA/render. Failed manufacturing cannot
export a stale model from an earlier run. A failed QA model can still be exported
for inspection, with its failure status retained. Intake alone is available via
`python long-lines/tools/sheet_blobs.py auto reference.png output_directory`;
`ready_to_build` is not model QA approval. Legacy `list`/`crop` commands remain.

## Acceptance evidence

The vintage blender sheet was processed from the original image alone: 26
drawings, six companion groups, six detected button instances and 12 manufactured
pieces. The model has 3,652 triangles and 2048-pixel maps. All 11 attachments pass
existing seating checks. Silhouette IoU: front .941, back .930, right .949, left
.954, top .812. Normal disagreement: zero. These are minimum-standard checks,
not a claim of perfect reconstruction.

Run `tools/test_automatic_intake.py` in normal Python for synthetic CV regressions.
Run `tools/test_automatic_build.py` under Blender for orchestration guards; pass
`-- result.json` to validate an actual end-to-end artifact set as well.

Model provenance: [RapidOCR](https://github.com/RapidAI/RapidOCR) and
[DINOv2 ONNX](https://huggingface.co/onnx-community/dinov2-small), pinned at revision
`ef1fb10`. ONNX SHA-256:
`f22797eabf810a75e41de68d378541ebea372122b25c4ce3ef25ff618250c20a`.
Weights download as dependencies and are not committed. Check upstream model
and dependency licenses before redistributing bundled weights.
