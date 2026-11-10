# Automatic sheet-intake experiment

Extends the existing `tools/sheet_blobs.py` splitter. The original `list` and
`crop` commands remain supported. This is a detection and correspondence trial,
not an autonomous model-generation claim.

```
python -m pip install -r requirements-vision.txt
python long-lines/tools/sheet_blobs.py auto reference.png output_directory
```

Input is one image. No crop boxes, view indices, part inventory, or manually
corrected OCR result is supplied. RapidOCR reads captions locally; foreground
segmentation finds drawings, including low-saturation shapes. Captions assign
assembled view directions and part groups. SIFT/affine RANSAC proposes visual
correspondences from detached drawings to labelled assembled views. Low evidence,
ambiguous alternatives, and duplicate part/view assignments remain unresolved.
An affine correspondence is not a complete 3D attachment transform.

Outputs:

- `detected-regions.png`: green accepted view assignments, orange unresolved or
  perspective drawings, with automatically read part names.
- `region_*.png`: automatically detected crops.
- `intake-report.json`: OCR, region bounds, match evidence and unresolved IDs.
- `sheet-spec.partial.json`: only accepted assignments, in the existing crop
  specification format. Do not treat a partial spec as a complete assembly plan.

Exit code 2 means manual review would be required; an unattended build must stop.
No assembly manifest or model is produced by this experimental command. Exit 0
only means region/view assignments are resolved, not that model QA has passed.

Part names currently come from captions. Identifying unlabeled semantic part
types, obtaining absolute scale, full 3D pose, contacts and robust repeated-part
assignment remain future work. No generative or conversational LLM is used at
runtime. OCR model files may download during initial setup; images are processed
locally. Dependencies and model licensing must be reviewed before redistribution.

The blender trial detected 26 drawings and read all six part headings plus six
assembly direction captions. Nineteen unlabelled part views remained unresolved:
feature correspondence was too weak/ambiguous. No hand corrections were made and
no model was generated. This is a failed end-to-end automation acceptance test,
with useful region detection progress.

Tests: `python long-lines/tools/test_automatic_intake.py`.
