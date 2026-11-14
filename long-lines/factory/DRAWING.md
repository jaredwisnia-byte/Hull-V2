# The drawing stage

An image-only order goes: **intake** (the sheet is split into views) → **drawing** → build →
QA → exports. The drawing comes first and the mesh is made from it. Nothing is built from the
raw paintings' outlines any more.

## What the drawing stage does (`tools/propkit/drafting.py`)

1. **Puts every view in the standard frame** (third-angle projection: top view above the front
   with the front edge at its bottom, right view to the right, bottom view below the front).
   A top or bottom view is tried in all eight orientations (four turns, mirrored or not) and the
   one whose proportion and outline agree with the front and side views is used. The decision
   and its scores go in the record and in the drawing's notes.
2. **Agrees the size.** Width and height from the front view, depth from the side view, at the
   scale intake fitted from the sizing manual. Each other view's own proportion is reported
   against that size.
3. **Draws clean profiles.** Each outline becomes straight lines and true arcs (one closed
   polyline with bulges, as CAD stores it) within 1 px of the painted outline. Near-square lines
   are snapped square. A mirror-symmetric view (most fronts and tops) is made exactly symmetric.
4. **Finds features.** Circles inside a view (openings, dials, bosses) are measured; an end view
   whose outline follows a circle marks that axis as **round**: the build gives the part round
   cross-sections along it (any axis, not only vertical).
5. **Writes the drawing**: `<name>.dxf` (AutoCAD, mm, layers OUTLINE/CENTER/DIMENSIONS/NOTES/
   FEATURES/BORDER, associative dimensions, title block), `<name>_drawing.png`, `drawing.json`.

## Measured roundness (`tools/propkit/rounding.py`)

Two outlines that share an axis fix each slice across it only as rectangles (one per pair of
outline spans). Each rectangle is given the superellipse |u/a|^n + |v/b|^n <= 1 that fills it:
n = 2 is an ellipse, larger n squarer, n = infinity the rectangle (the plain visual hull). One n
per **part**: connected runs of rectangles along each axis, split where the section changes
abruptly (a handle meeting a barrel). Rounding never changes any view's outline: a corner a view
needs is put back.

n is measured, never chosen by object type:
- **Pictorial view:** the camera is solved once from the unrounded shape and held fixed. For each
  part, the exponent whose outline best matches the picture where that part forms the outline
  wins, if it beats the square section by more than the measurement resolution. (A square
  section seen at angle t spans w(|cos t| + |sin t|); a round one spans w.)
- **Painted shading** (second witness; used only without a pictorial view): edge-to-middle
  brightness under light from the viewer follows the cosine of the surface tilt, a known
  function of n. Paint bands make it unreliable on most sheets, which is why it is second.

## Local features (`tools/propkit/features.py`)

A bump one outline shows (a switch on a handle) would otherwise widen every rectangle at its
height across the whole part. Along each part, a short run (at most 25% of the part, at most 30%
of its section deep) where a section edge stands out from its running-median trend is a bump.
Its width is measured in the painting of the view that **faces** it (looks along the bump's
direction from the side it sticks out on), as the columns whose colour changes where the bump
starts and stops (compared with the same columns just before and after it, so stripes and
panels running along the part cancel). The bump is built only that wide in the mesh and in
the CAD solid; with no distinct painted feature it keeps the full width and says so.

## How the build uses it (`tools/factory.py`, `tools/propkit/hull.py`)

- The oriented views become the order's views (paint, relief and QA all see the same frame).
- The hull carves with the drawn profiles (observed openings kept) at the drawing's size.
- `round_sections`: inside the end view's circle every slice is the ellipse that fills that
  slice's extent (`hull.round_section_field`), so it only ever removes material; offcuts left
  floating outside the circle are removed.
- Orders opt out with `"drafting": false`. It is on by default for vision-generated orders.

## QA against what the object should look like (`tools/propkit/drawing_qa.py`)

- **Against the drawing, in mm, never rescaled:** overall sizes within max(2 mm, 3%); each view's
  mesh outline must cover the drawn profile at IoU ≥ 0.90 with 95% of the outline within 3% of
  the object's size. Overlays `drawing-match-<view>.png` (red = drawn but missing, blue = extra).
- **Against the sheet's pictorial (isometric) view:** intake now saves it
  (`p_pictorial_<id>.png`, order `reference_images`). The camera angle is searched (from above)
  for the best outline match; IoU ≥ 0.85 passes. Overlay `pictorial-match-*.png`. The pictorial
  view is never used to build, so it is an independent witness.
- **Inside the outline:** at that camera, one light is fitted to the pictorial painting from the
  mesh's own surface normals (brightness = n·l + c, linear least squares) and the share of the
  painted brightness the geometry explains (R²) must reach the pass level. A boxed handle where
  the picture shades smoothly explains less (square vs round dryer: 0.21 vs 0.31). Overlay
  `shading-match-*.png` (painting left, fitted shading right).

## Engineering export (`tools/propkit/cad_model.py`)

A CAD solid (OpenCascade via build123d) is built from the drawing the way a designer would:
the front, side and top profiles are extruded and intersected, round end views are lofted
through ellipses, measured round parts are lofted through superellipse sections at their own
(smoothed) stations, and local features are cut to their measured width. Each replacement is
accepted only if every view's outline stays within 0.3% and the overall size within 1 mm;
otherwise the extrusion stands and the report says why. Exports: `<name>.step` (tooling), `<name>_cad.stl`, `<name>_cad_drawing.dxf/png`
(hidden-line front/top/right views, isometric, hatched sections A-A and B-B, dimensions, volume,
surface area, centre of mass, mass for a stated material), `<name>_cad.json`.

Limits, stated on every sheet: sizes are estimates at intake's scale; wall thickness,
internals, fasteners, draft and tolerances cannot be seen on a reference sheet.
