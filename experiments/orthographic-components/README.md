# Orthographic component reconstruction experiment

This is an experimental checkpoint, not a change to Hull's production pipeline. All existing files under `long-lines/` remain unchanged.

The external runners import existing `polygon_hull`, `hull_prop`, round-part inference, projected texturing, and bake/export functions. They supply image crops, dimensions, assembly placement, component separation and explicit triangle allocations. This is guided reconstruction, not autonomous semantic understanding of an arbitrary image.

## Recorded results

| Experiment | Final triangles | Input strategy |
| --- | ---: | --- |
| 1974 stove | 8,058 | Original painting, semantic part map, detached-part companion views |
| 1970s SLR | 3,022 | Assembled reference, bare-body views, detached lens and dial prototypes |
| Camera contour repair | 2,646 | Simplified body contours, larger references, measured lens mount |

## Contour repair

The camera's horizontal bands were geometry: pixel-scale changes in the side silhouette were extruded across the whole body and then bevelled. Clay renders confirmed the bands remained without textures or normal maps. The `camera-clean` recipe sets `contour_tolerance: 6` (source pixels) before polygon-hull construction; body complexity fell from 2,134 to 592 triangles. The main rear panel passed a numerical plane-deviation check. Clay and wireframe evidence is stored in `camera-clean/`.

This tolerance is an explicit recipe setting, not a universal new default. It can remove genuine fine features on other references. The shared camera runner additionally supports trusted geometry views, paint padding, projection strength, reconstruction resolution, measured front mount seating, per-part bevel fractions, and disabling a part's self-baked normal map. Defaults preserve the original recipe behavior.

Run the repaired recipe with `python run.py camera-clean --blender PATH_TO_BLENDER --deps PATH_TO_DEPENDENCIES --workdir EXTERNAL_WORK_DIRECTORY`. This builds from the included images, without depending on any previous model file. Glass and material-reasoning prototypes are excluded.

The stove is a fixed recipe preserved as a reproducible baseline. Its physical dimensions and placement rules remain embedded in its external runner; it has not yet been generalized into the manifest format. The camera uses a manifest-driven runner with crop boxes, dimensions, positions and per-part budgets. Dimensions are assumptions, not manufacturer specifications.

## Run

Use Blender 5.2.3 LTS with Pillow, SciPy, scikit-image and NumPy compatible with its Python 3.13. Install dependencies into an external directory, not Blender's installation or the checkout.

```
python run.py camera --blender PATH_TO_BLENDER --deps PATH_TO_DEPENDENCIES --workdir EXTERNAL_WORK_DIRECTORY
python run.py stove --blender PATH_TO_BLENDER --deps PATH_TO_DEPENDENCIES --workdir ANOTHER_EXTERNAL_DIRECTORY
```

`run.py` derives Hull's tools path from its checkout and writes all generated models and textures to the requested external directory. It does not require the original machine's paths. Do not use the checkout itself as the work directory.

## Limits and evidence

Generated orthographic views can contradict each other. Hidden surfaces are inferred artwork. Separating the bare body from the component painting helps prevent duplicate painted objects, but does not guarantee matching geometry. The stove still has duplicate painted burner profiles; its spirals remain primarily texture. Its separate door has only a neutral backing, not a reconstructed oven chamber. The camera's placement and lens seating need visual review.

Triangle budgets are allocated to the complete assembly before the shared bake, rather than applying the full small-object allowance independently to every copy. The stove's exported GLB count was verified against Blender. Reports and representative renders are included; full generated model binaries and intermediate files are excluded from this checkpoint.

Camera generated art was guided by a user-supplied photograph of a 1970s Canon F-1; the new painted camera omits branding. This is an independent workflow test, not a claim that all artifacts have been solved.
