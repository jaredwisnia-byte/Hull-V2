# Curve-based reconstruction (design, 2026-11-14)

Design for architecture steps 3 and 4 ([ARCHITECTURE.md](ARCHITECTURE.md)). Status: proposed,
not built. Jared's direction:

- **The drawing is the book of truth.** The CAD solid made from the technical drawing
  (`propkit/cad_model.py`) is the geometry the mesh is built from. Today it is only exported as
  STEP while the mesh comes from a voxel blob; that inverts the module's purpose.
- **Curves, not light.** Hull traces real mathematical curves in the views (lines, arcs, conics,
  splines), matches them across views and derives the geometry by mathematics. Pixel brightness
  never sets depth. Light only colours the model.
- **Parts are found automatically**, never only when a sheet happens to draw each part.
- **Noise is removed by statistics**, not by hand-tuned exceptions.
- **Unseen sides follow explicit, recorded logic.**

## What exists to build on

| Need | Existing code | Gap |
|---|---|---|
| Outline curves | `drafting.fit_profile`: lines and arcs within 1 px, opposite views reconciled | Outer contour only (Order 2 adds openings); no interior curves |
| Interior paths | `drawing_traces`, `tracing_backend` (MatchED / phase congruency): traced edges and seams, no depth guessed | Paths are not fitted as curves or matched across views |
| Parts along an axis | `rounding.tracks`: a new part starts where the section changes abruptly ("a handle meeting a barrel") | Used only to set roundness; never becomes a part |
| Cross-sections | `rounding` / `sections` (superellipse), `revolve` (lathe) | Applied to a voxel field, not to solids |
| Surfaces | `spline_surface`: B-spline / NURBS patches with bounded error | Not driven by curves |
| Solids | `cad_model`: profiles extruded and intersected, round parts lofted (build123d / OpenCascade) | Not used for the mesh |
| Assembly | `parts_layout` (locators residual / protrusion / concentric / attach, seating, gap check), `hull_assembly` (contact fitting, 4 mm gap guard) | Only reached when the sheet labels part views |
| Hollows | `blades.py`: a top-view region whose top edge the front view shows as a line is cut down to it | One rule, voxel only |

## How the couch came out well (and what that teaches)

`sofa_olive_suede` used the `hull_parts` line (see LESSONS.md, Nov 9):

1. **Decomposition did the work.** The sheet showed each part on its own (seat, back cushion,
   arm, foot). Each part became a soft hull from its own larger views; organic softness inside a
   simple part is easy, the whole sofa as one hull was not.
2. **Placement came from simple measurements** of the whole-object views: flat stretches of the
   front view's top outline = arms, painted seams above the seat = cushion count and widths, the
   parts' own proportions = thickness, shapes under the body = feet.
3. **Hidden geometry came from one rule** (blades): the seat hidden behind arms and cushions was
   cut down to where the front and top views' edges meet.
4. **Contacts were fitted** (neighbours stretched to each other's surface, 1.5 cm overlap), and a
   gap guard fails any build with 90th-percentile gaps over 4 mm.
5. **An edge guide** (hand-drawn coloured lines: red separations, cyan outline) supplied the part
   boundaries. This design replaces that hand input with curves Hull finds itself.

Lesson recorded then and kept here: *a global search matching every painted edge was too noisy
and carved holes at random; one clear rule beat an optimiser.* So curves are validated one by
one, statistically, before any are matched, and matching uses explicit geometric rules.

## The pipeline

### 1. Curves (pixels are read once, here)

For each view:

- **Outline** from `drafting` (with openings after Order 2).
- **Interior candidates**: line segments by LSD (OpenCV `createLineSegmentDetector`, available in
  the installed OpenCV 5.0) and arcs/ellipses by the same a-contrario test; traced seams from
  `drawing_traces`.
- **Fit** each candidate with the simplest exact curve within the pixel noise: line, circular arc,
  ellipse, then B-spline. Choose the type by a model-selection score (error plus a penalty per
  parameter, i.e. BIC/MDL), so noise never buys a more complex curve.

Every curve keeps its source pixels, fit error and type.

### 2. Statistics: rejecting false curves

A painted sheet has wear, highlights, paint bands and fabric texture. A curve survives only if
every test below passes; each is a measured statistic, never a hand-picked exception:

1. **Not an accident (a-contrario).** A segment is accepted only if the number of false alarms
   (NFA), the expected count of segments that aligned at least this well in random gradient
   noise of the same image, is below 1. This is LSD's own test and has a known false-detection
   rate instead of a tuned threshold.
2. **Scale persistence.** A real edge is found again at 2x and 4x blur; wear and texture vanish.
   Keep curves present in at least two of three scales.
3. **Consistent contrast.** A real edge's contrast is coherent along its length (low coefficient of
   variation of the gradient magnitude across the curve); a highlight fades in and out.
4. **Cross-view consensus (the decisive test).** An orthographic edge must appear in at least two
   views at the same coordinate on their shared axis (front and side share height, front and top
   share width). The tolerance is not guessed: it is the measured registration error between
   the views' outlines (the 95th percentile of outline disagreement on the shared axis), so a
   sheet whose views disagree by a centimetre gets a centimetre tolerance.
5. **Robust fitting.** 3D curve fits use RANSAC (consensus of random minimal samples) so one stray
   point cannot bend a curve.
6. **Symmetry votes.** Manufactured objects are mostly mirror-symmetric. If a curve's mirror image
   (about the object's measured symmetry plane) is also observed, its confidence rises; a curve
   with no mirror on a symmetric object is downgraded.

A curve that fails stays in the report as *observed, not used*. It may still be texture.

### 3. Lifting curves into 3D (orthographic geometry)

- Each accepted curve pair across two views fixes a 3D curve: shared-axis coordinates must agree;
  the remaining coordinate comes from the second view.
- Known projections give primitives directly:
  - a circle in one view and a straight line of the same length in a perpendicular view: a
    cylinder, hole or boss along that axis;
  - an ellipse: a circle seen obliquely, which fixes its axis direction;
  - a curve identical in front and back views: a sweep through the depth.
- This is the classical problem of reconstructing a solid from three orthographic views
  (Idesawa 1973; Wesley and Markowsky 1981, extended to curved surfaces by later work). Hull's
  version differs only in that its views are paintings, which is why step 2 exists.

### 4. Parts, found automatically

A part boundary is accepted where any two of these agree:

1. **Abrupt section change along an axis**: `rounding.tracks` already finds these.
2. **Concave creases in an outline**: where the outline turns inward sharply (a handle meeting a
   barrel). Human vision splits shapes the same way (the "minima rule": part boundaries lie at
   concave curvature minima).
3. **A closed seam curve confirmed in two views**: a separation that runs round the object.
4. **Round end views**: a round region in an end view is its own turned part.

Each part then gets its construction from its curves (step 5), and its placement from the
existing `parts_layout` locators (residual, protrusion, concentric, attach) and `hull_assembly`
contact fitting and gap guard. The sheet needs no labelled part views. A sheet that has them
still uses them, as extra evidence.

### 5. Surfaces and solids from curves (`cad_model`)

Per part, in order of preference:

| Curves show | Construction |
|---|---|
| A profile constant through the depth | Extrude |
| A profile and an axis (round end view) | Revolve |
| Sections changing along an axis | Loft through superellipse sections (`rounding`) |
| A network of curves | Trimmed NURBS patches (`spline_surface`), sewn |
| None of these within tolerance (cushion, carved leg) | Per-part soft hull (the voxel path), as on the couch |

Features (holes, bosses, buttons) are cut or added to their part. The result is one exact solid
per part: **the book of truth**. STEP, the engineering drawing and every mesh come from it.

### 6. Fidelity and output

- Each solid is meshed by OpenCascade at the profile's surface tolerance t (linear and angular
  deflection): `engineering` 0.05 mm, `game_hero` / `game_prop` / `game_background` from viewing
  distance. No blob is simplified.
- Detail narrower than 2t or shallower than t is baked from the exact solid into the normal map.
- Paint is projected only as colour, per part (`source_pixel_ownership`).
- Shading is used only as a QA check (pictorial R^2), never as a depth source.

## Unseen sides: the logic

What no view shows is filled by the first rule below that applies, and every use is recorded.
The rules are ordered from strongest evidence to weakest:

1. **Observed.** Any view shows it: use it.
2. **Symmetry.** If the visible geometry is mirror-symmetric (measured: mirrored curves and outlines
   agree within the registration tolerance), the hidden half mirrors the visible half.
3. **Revolution.** A turned part's hidden side equals its visible side.
4. **Continuation.** A section seen at both ends of a span with no change visible in between
   continues unchanged (an extrusion or sweep); a hole seen in one face and on the opposite face
   goes straight through.
5. **Meeting edges (the blade rule, generalised).** A region bounded in one view by a line that
   another view shows at a lower height is cut down to that line: seats behind arms, the inside of
   a rim whose ellipse the top view shows.
6. **Construction regularity.** Prefer what manufacturing produces: planar faces at right angles,
   constant wall thickness for a confirmed hollow (from `sizing_manual.json` facts, not object
   names), a flat underside resting on the ground, parts seated on their contacts.
7. **Simplest closure.** Otherwise close the region with the simplest surface that stays inside
   every outline. Never invent a feature.

Every assumed surface is drawn on the technical drawing as a **dashed hidden line** (the
engineering convention), listed in the report with its rule, and marked in the build record, so
Jared can review or correct it. Assumed geometry never counts as evidence for QA.

## Order of work (each behind a switch, each gated on the drawn set and the seven objects)

1. **Drawing builds the mesh.** Mesh `cad_model`'s existing solid at the fidelity tolerance and
   compare it with the voxel mesh on the same inputs (`"construction": "cad"`). Smallest change
   that makes the drawing the source of truth.
2. **Automatic parts.** Turn `rounding.tracks` runs plus concave creases into parts, build each with
   `cad_model`, assemble with `parts_layout` locators and the gap guard.
3. **Curve extraction and statistics.** LSD + arc detection, model selection, the six tests;
   report observed / accepted / rejected curves on the drawing.
4. **Cross-view lifting.** 3D curves and primitives; features attached to parts.
5. **Unseen-side rules** with dashed hidden lines and the report.
6. **Curve networks to NURBS** for parts no primitive fits; the voxel path stays the last fallback.

Gates follow `CONTRIBUTING.md`: the mixed set before and after, byte-identical repeat builds
(rule R9), no object-name selection, clay renders inspected.
