# Component pipeline validation

Validated on Windows with Blender 5.2.3 LTS / Python 3.13 and Godot 4.4.1. Dependency versions are recorded in `requirements-hull.txt`.

| Check | Result |
| --- | --- |
| Manifest validation tests | 8 passing tests, including whole-assembly over-allocation, circular dimensions, invalid crops, prototype expansion and dependency cycles |
| Blender component integration | Passed contour-ridge check, shared bake/GLB, prototype reuse, independent meshes, parenting, actual surface seating, factory dispatch and triangle ceiling |
| Existing sizing tests | All 4 groups passed |
| Existing hull geometry regressions | 0 failures (box, slope, vase, housing, disc and cord checks) |
| New production camera build | 2,646 actual exported triangles, separate components retained |
| Archived stove compatibility build | 8,058 actual exported triangles |
| Godot unit checks | 39 checks, 0 failures |
| Godot smoke test | 45 checks, 0 failures |

The production camera was built with `tools/hull.py build` and inspected with the new clay renderer: the main housing panels remain free of the previous horizontal ridge artifact. A synthetic rippled side silhouette also has a planar residual regression check in `test_components.py`.

These checks establish the tested behavior; they do not prove that arbitrary generated paintings contain enough evidence to reconstruct correct hidden geometry. Contour tolerance, dimensions, attachment points and uncertain depth remain explicit recipe settings. Existing sizing rules are preserved. The glass/material-reasoning demonstrations were not promoted.

Generated Godot import metadata and runtime model binaries are not committed as code changes. The older experiment camera launcher now delegates to the production modules instead of maintaining a second implementation.
