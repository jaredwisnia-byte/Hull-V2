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
  for the best outline match; IoU ≥ 0.82 passes. Overlay `pictorial-match-*.png`. The pictorial
  view is never used to build, so it is an independent witness.

## Engineering export (`tools/propkit/cad_model.py`)

A CAD solid (OpenCascade via build123d) is built from the drawing the way a designer would:
the front, side and top profiles are extruded and intersected, and round axes are lofted
through ellipses. Exports: `<name>.step` (tooling), `<name>_cad.stl`, `<name>_cad_drawing.dxf/png`
(hidden-line front/top/right views, isometric, hatched sections A-A and B-B, dimensions, volume,
surface area, centre of mass, mass for a stated material), `<name>_cad.json`.

Limits, stated on every sheet: sizes are estimates at intake's scale; wall thickness,
internals, fasteners, draft and tolerances cannot be seen on a reference sheet.
