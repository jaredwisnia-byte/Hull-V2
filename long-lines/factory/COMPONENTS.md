# Hull V2 component production line

Use a manifest when a shell, knob, handle, door or lens needs separate depth evidence. Existing `hull`, `hull_parts`, `sheetset` and other work orders remain supported.

## Commands and outputs

Pass commands after Blender's `--` delimiter to `long-lines/tools/hull.py`:

```
validate MANIFEST
build MANIFEST --output DIR [--work-dir DIR] [--no-blend]
render MODEL.glb --output IMAGE.png [--mode textured|clay|wireframe]
```

Validation also runs under ordinary Python without Blender imports. Builds write `DIR/NAME/NAME.glb`, a packed `.blend` unless disabled, albedo/normal/ORM PNGs, and `build-report.json`. The GLB includes baked materials rather than placeholders. Set `PYTHONPATH` and launch Blender with `--python-use-system-env` when dependencies are installed outside Blender. `HULL_WORK_DIR` selects a scratch root; by default the operating system's temporary directory is used.

Standard factory orders accept `"line": "components"`, with `views_folder` containing `manifest.json` or an explicit `manifest` path. The order and manifest names must match. Ledger, standards and quality gate remain in the factory; named components are restored before that gate.

## Minimal manifest

```json
{
  "name": "housing",
  "reference": "views.png",
  "texture": 1024,
  "triangle_limit": 1200,
  "pad_paint": true,
  "parts": [{
    "name": "body",
    "method": "polygon",
    "dimensions": [0.15, 0.05, 0.09],
    "budget": 1000,
    "position": [0, 0, 0],
    "contour_tolerance": 3,
    "geometry_views": ["front", "right"],
    "views": {"front": [0, 0, 300, 200], "right": [300, 0, 450, 200]}
  }]
}
```

Paths resolve relative to the manifest. Pixel crops are `[left, top, right, bottom]` with exclusive right/bottom, inside the referenced canvas. Dimensions are **width, depth, height in metres**. Local Z is up; front faces -Y. The right drawing has the object's front at the image's left; the top drawing has its front at the bottom. Keep labels and neighbouring objects outside crops.

## Geometry

- `method`: `polygon` intersects silhouette prisms; `round` invokes Hull's round-part inference. Round reconstruction requires front and side evidence.
- `geometry_views`: select trusted outlines; other supplied views still contribute paint.
- `reconstruction_resolution`: assembly-wide resolution for round reconstruction (default 64). It cannot resolve contradictory evidence by itself.
- `contour_tolerance`: source-pixel simplification distance for polygon parts. Default 1.1; the approximately 500-pixel camera views use 6. Tiny edge jitter otherwise becomes full-width ridges. Excessive tolerance erases genuine detail, so the repair is not a universal new default.
- `bevel_fraction`: fraction of the smallest dimension; zero is supported.
- `circular_axis`: `vertical` requires equal width/depth; `front-to-back` requires equal width/height. Inconsistent declared diameters are rejected instead of silently creating ovals. This does not guarantee perfect circularity from contradictory drawings.

Optional `part_map` uses the existing sheetset palette and must match the reference canvas. `mask_mode: "body"` takes its shell carve mask to exclude compact protrusions; `"object"` keeps the complete object mask. This uses semantic masks for segmentation, not for automatic depth estimation. Separate components still need their own views and supplied dimensions.

## Paint and materials

`pad_paint: true` extends colours past the known mask without re-detecting the silhouette from a tight crop, including for uniform-colour parts. `projection_power` controls facing preference (default 4); higher values such as 32 reduce cross-view mixing but can reveal seams in inconsistent paintings. `use_normal_map: false` disables a part's self-baked normal map after the shared bake. It does not remove geometric ridges. Materials use the baked albedo/normal/ORM maps; autonomous material classification and the glass prototype are not part of this line.

## Assembly budgets and prototypes

Every part has an integer `budget`; their sum must fit `triangle_limit`. The pipeline checks allocations before building, each mesh after simplification, and the actual final GLB count. The ordinary size-class ceiling also applies during the shared bake. A custom budget cannot raise that ceiling.

`prototypes` maps identifiers to template specifications. An instance such as `{"name": "knob_left", "prototype": "knob", "position": [...]}` inherits the template and can override its fields. Matching instances reuse local reconstruction and projection setup, receive independent meshes, and each consume their own allocation.

## Placement and hierarchy

`attachment` specifies a named parent, `face` (`front`, `back`, `left`, `right`, `top`) and nonnegative `overlap` in metres. A ray cast finds the parent surface beneath the child's center and seats the child's contact extent into it. Misses are build errors. Dependencies are sorted and cycles rejected.

Front attachments can specify `pixel: [x,y]` in the parent's original front painting. Crop and silhouette bounds map that point into the parent's physical frame. The camera seats its lens at an image-measured center with 6 mm overlap. This is supplied evidence, not autonomous feature recognition.

`parent: "door"` independently preserves a hierarchy while keeping world placement, for example attaching a handle to a door. Seating alone does not imply parenting. Parts survive the shared atlas bake via temporary vertex groups. Legacy `mount: "top"` and `mount: "lens_mount"` are normalized for checkpoint compatibility; new data should use `attachment`.

## Evidence and review

Record guessed dimensions in `assumptions`. Set `dimensions_assumed: false` only when actual measured dimensions are supplied. Continue using `factory/sizing_manual.json` as the source for believable dimensions; this pipeline does not override it with invented image measurements.

Review the build report, exported count, and clay/wireframe renders. A technically valid textured model can hide a bad surface. Hidden geometry, optical prescriptions and material identity remain explicit assumptions. The production camera example is in `examples/camera-clean/`; experimental recipes remain preserved as provenance.
