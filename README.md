# Hull V2

Reconstruct painted orthographic references as textured, separately named 3D components. This is an independent development copy of the original asset factory.

## Start here

- [Component workflow and manifest reference](long-lines/factory/COMPONENTS.md)
- [Factory manual](long-lines/factory/README.md)
- [Sizing instructions](long-lines/factory/SIZING.md) and [sizing rules](long-lines/factory/sizing_manual.json)
- [Reproducible camera example](long-lines/factory/examples/camera-clean/manifest.json)
- [Preserved experiments and comparison renders](experiments/orthographic-components/README.md)

```sh
blender -b --factory-startup -P long-lines/tools/hull.py -- validate long-lines/factory/examples/camera-clean/manifest.json
blender -b --factory-startup -P long-lines/tools/hull.py -- build long-lines/factory/examples/camera-clean/manifest.json --output ./build
blender -b --factory-startup -P long-lines/tools/hull.py -- render ./build/camera_clean/camera_clean.glb --output ./build/camera.png --mode clay
```

Install [the verified dependencies](requirements-hull.txt) in Blender's Python environment. External dependencies can be supplied with `PYTHONPATH` and Blender's `--python-use-system-env`. `HULL_WORK_DIR` optionally selects a scratch directory; otherwise the operating system's temporary directory is used.

## Production functionality

Companion-view manifests, reusable prototype instances, named components and parent hierarchies; explicit attachment seating; per-part contour simplification and trusted outlines; optional circular-diameter validation; semantic shell masks; colour padding and configurable projection; one assembly-wide triangle budget; shared atlases and textured GLB exports; packed Blender projects; clay and wireframe inspection.

**Autonomous image understanding, hidden-depth inference, optical-glass reconstruction and material recognition are not implemented.** Supplied dimensions and hypotheses remain visible in manifests and reports. Glass/material demonstrations are not promoted into this workflow.

## Repository map

| Location | Purpose |
| --- | --- |
| `long-lines/tools/hull.py` | Hull V2 CLI |
| `long-lines/tools/propkit/components/` | Validation, reconstruction, placement, export and inspection |
| `long-lines/tools/propkit/` | Shared geometry, texturing, sizing and legacy lines |
| `long-lines/factory/` | Standards, sizing, work orders and examples |
| `experiments/` | Preserved experiments, not a second production implementation |
| `long-lines/` | Existing Godot integration, retained at its original paths |

The imported repository also contains unrelated Midnight Watch web files. Their [original documentation is preserved](docs/legacy-midnight-watch.md); they are not part of Hull's reconstruction pipeline.

## Checks

```sh
python long-lines/tools/test_component_manifest.py
python long-lines/tools/test_sizing.py
blender -b --factory-startup -P long-lines/tools/test_components.py
blender -b --factory-startup -P long-lines/tools/test_hull_geometry.py
```

The integration fixture checks contour-ridge suppression, attachment seating, parent hierarchy, shared baking, and actual exported counts. Inspect real examples in clay/wireframe before accepting visual changes.
