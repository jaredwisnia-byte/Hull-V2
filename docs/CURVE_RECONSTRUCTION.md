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

## Seen first, crutch second: consistent curves decide the construction (2026-11-14)

Jared: *"Start with what we can see and develop a crutch for what it can't. The curve, for
something that is consistent along multiple views, can tell Hull what it wants to do."*

This is how an artist or a draughtsman reads a set of views: they do not measure brightness, they
read which lines agree with which, and each agreement *means* a construction. Hull works in
three tiers and never mixes them:

| Tier | Evidence | Use |
|---|---|---|
| **Seen and consistent** | The same curve found in two or more views, agreeing on their shared axis within the measured registration tolerance | **Authoritative.** It decides the construction (table below) |
| **Seen once** | A curve in one view only | A proposal. Used only where geometry fixes its third coordinate: a feature on a face that view sees head-on lies on that face; otherwise it is texture |
| **Not seen** | No view shows it | The crutch: the unseen-side rules above, then the artist's regularities below. Always drawn dashed and reported |

### What a consistent curve tells Hull to build

Each row is a geometric fact about orthographic projection, not a rule about any kind of object.

| What the views agree on | It means | Construction |
|---|---|---|
| The same closed profile in two opposite views (front = mirrored back) | Nothing changes through the depth | Extrude that profile |
| A circle in one view; two parallel lines of the same length in a perpendicular view | A cylinder, hole or boss on that axis | Cylinder (cut if the circle shows background) |
| A circle in an end view; a varying outline along the axis in the side view | A turned shape | Revolve the side outline about the circle's centre |
| An ellipse | A circle seen at a tilt; the axis ratio gives the tilt | Circle with that axis direction |
| Sections changing smoothly along an axis in two views | A shaped body | Loft through the superellipse sections (`rounding`) |
| A closed seam inside the outline at the same coordinates in two views | A physical separation | Part boundary: split the part |
| A concave corner of the outline at the same height in two views | Two bodies joined (the minima rule) | Part boundary |
| A line at height h in one view meeting a region the other view bounds lower | A step or hollow (the couch's blade rule) | Cut the region down to h |
| A curve on a face seen head-on, its depth visible as a step in a second view | A raised or sunken feature of known depth | Boss or pocket on that face |
| A curve on a face seen head-on, no depth anywhere | Decoration | Texture and normal map only |

Agreement is scored, not assumed: the number of supporting views, the residual on the shared axis
(in units of the measured registration tolerance) and the fit error. A construction is accepted
only when its curves pass step 2's statistics *and* agree across views; it records which curves
decided it, so every face of the solid can be traced back to the lines that caused it.

### Reading lines like an artist (step 1 extended)

Before matching, each accepted curve is classified, because an artist treats each kind differently:

- **outline**: on the view's silhouette;
- **crease**: a sharp edge between faces; seen in two views at agreeing coordinates;
- **part boundary**: a closed or nearly closed seam;
- **cross-section / contour**: a curve wrapping across a curved surface; it says how the surface
  bends (CrossShade shows that such cross-section lines determine surface normals);
- **decoration**: paint; it changes colour but has no counterpart in another view.

Broken curves are joined first (a dial ring traced as short pieces becomes one circle) by fitting
circles and ellipses to chains of arcs, with the same a-contrario test LSD uses (as ELSDc does for
ellipses; Hull implements the test itself rather than linking that AGPL code).

### The pictorial view as a fourth witness

Most sheets include a three-quarter picture. Hull currently fits a camera to it by outline only
(`drawing_qa.against_pictorial`). Read like a perspective drawing it gives much more:

- families of lines that are parallel in 3D meet at vanishing points; voting for them (RANSAC over
  line intersections) recovers the camera directly (single-view metrology);
- ellipses in it fix the axes of round parts;
- it shows corners and faces between the orthographic views, so it can **confirm or veto** an
  unseen-side assumption before it is used.

It is never the only source for a construction; it is a witness that raises or lowers confidence.

### The crutch: the artist's regularities

Where no view decides, Hull applies the regularities designers draw with, but **selectively**: a
regularity is enforced only where the seen curves already nearly satisfy it (True2Form's selective
regularization), judged by robust statistics, never assumed wholesale:

- parallel and perpendicular curves; coplanar curves; curves of equal length;
- mirror symmetry: curve pairs symmetric about an axis-aligned plane fix the hidden half
  (Cordier et al.; Hähnlein et al.);
- cross-sections at right angles to a body's axis;
- straight or circular continuation of a curve that leaves the view.

Then the unseen-side rules above, in order. Everything the crutch adds is dashed, reported and
excluded from QA evidence.

### Drawing it back: the artist's check

The finished curve network and solid are projected back into every sheet view and the pictorial
view, as line drawings, and compared line against line with the traced curves. A missing or extra
line is located on the drawing. This is "does it look right from there?" made measurable, and it
uses no light.

## Research behind this design

| Topic | Work | What Hull takes |
|---|---|---|
| Solids from three orthographic views | Idesawa 1973; Wesley and Markowsky, "Fleshing out projections", IBM J. Res. Dev. 1981 (polyhedra); Sakurai and Gossard 1988 (curved faces); Liu, Hu, Chen and Sun, CAD 2001 (planar, quadric and toroidal faces via conics) | Matching curves across views, conic edges from their projections, keeping several candidates when the views are ambiguous |
| Line detection with a known false-alarm rate | Grompone von Gioi et al., LSD (2010); Pătrăucean, Gurdjos and Grompone von Gioi, ELSD / ELSDc (2012) | The a-contrario test (NFA < 1) for lines, arcs and ellipses |
| 3D curves from 2D sketches | Xu, Chang, Sheffer, Bousseau, McCrae and Singh, True2Form, SIGGRAPH 2014 | Selective regularity: enforce parallelism, orthogonality, planarity and symmetry only where the drawing supports them |
| Lifting real design sketches | Gryaditskaya, Hähnlein, Liu, Sheffer and Bousseau, SIGGRAPH Asia 2020; Hähnlein et al., symmetry-driven reconstruction, SIGGRAPH 2022 | Telling true 3D intersections from accidental overlaps; symmetric curve pairs |
| Mirror-symmetric shapes from sketches | Cordier, Seo, Melkemi and Sapidis, CAD 2013 | Lifting symmetric curve pairs; the hidden half |
| Cross-section curves | Shao, Bousseau, Sheffer and Singh, CrossShade, SIGGRAPH 2012 | Cross-section lines determine surface normals |
| Perspective measurement | Criminisi, Reid and Zisserman, "Single View Metrology", IJCV 2000 | Vanishing points and camera from the pictorial view |
| Where parts begin | Hoffman and Richards, "Parts of recognition", Cognition 1984 (the minima rule) | Part boundaries at concave creases, confirmed by a second cue because negative minima alone are not always boundaries |

## Order of work (each behind a switch, each gated on the drawn set and the seven objects)

1. **Drawing builds the mesh.** Mesh `cad_model`'s existing solid at the fidelity tolerance and
   compare it with the voxel mesh on the same inputs (`"construction": "cad"`). Smallest change
   that makes the drawing the source of truth.
2. **Automatic parts.** Turn `rounding.tracks` runs plus concave creases into parts, build each with
   `cad_model`, assemble with `parts_layout` locators and the gap guard.
3. **Curve extraction and statistics.** LSD + arc detection, model selection, the six tests;
   report observed / accepted / rejected curves on the drawing. Then join broken arcs and classify
   lines (outline, crease, part boundary, cross-section, decoration).
4. **Cross-view lifting: consistent curves decide.** Score agreement across views and apply the
   construction table above; 3D curves and primitives; features attached to parts.
5. **The pictorial view as a witness**: vanishing points, camera, ellipse axes; confirm or veto.
6. **The crutch**: selective regularities, then the unseen-side rules, with dashed hidden lines.
7. **Drawing it back**: project the result into every view and compare line against line.
8. **Curve networks to NURBS** for parts no primitive fits; the voxel path stays the last fallback.

Gates follow `CONTRIBUTING.md`: the mixed set before and after, byte-identical repeat builds
(rule R9), no object-name selection, clay renders inspected.

## Progress

**2026-11-14, preview of step 1 (no code change).** The `cad_model` solids that Order 1's builds
already exported (`vision_*.step`) were meshed by OpenCascade at the four profile tolerances and
rendered as clay beside the voxel meshes. The solids have no folds or crumpling, and fidelity
works: the hair dryer is 26,778 triangles at `engineering`, 3,978 at `game_hero`, 1,778 at
`game_prop` and 1,144 at `game_background` (voxel mesh today: 737, 100 folds per 1,000). What the
solids lack is exactly what the curve stages add: outlines are extruded and intersected, so
cross-sections are boxy where no round end view was found (several round parts were skipped as
"would change a view outline"), the cassette handle is filled (Order 2), the camera has a thin
fin, and the mixer bowl and head are one block (no parts).

**2026-11-14, step 3 started: `propkit/curves.py`** (single-view statistics, test `test_curves.py`,
registered as core check `curves`). LSD candidates, chain-level scale persistence, contrast
coherence, symmetry votes, BIC choice between line, circle, ellipse (direct least squares) and
B-spline; deterministic. On three views of each of the seven objects it keeps 36-60% of
candidates. On the toaster's side view it keeps the outline, both slots, the lever slot and the
panel edges, and rejects most chrome reflections and wear; it also keeps one highlight band and
rejects some faint real edges, and leaves the dial ring as separate pieces. Single-view
statistics cannot do better alone: cross-view consensus (step 4) is the decisive filter.

**2026-11-14, steps 3-4 begun: `propkit/curve_views.py`** (tests `test_curve_views.py`, core check
`curve-views`) and `curves.py` extensions (broken arcs joined into circles; outline / closed /
interior labels; persistence by brightness-step retention as well as LSD, required at half of the
eligible coarse scales). Cross-view agreement uses the `hull.py` view convention, a tolerance
measured from the outlines' breakpoints, and constructions `through`, `cylinder` and `plane`.
On a synthetic box with a boss, a groove and a front-only paint band it finds the cylinder, the
groove's plane, the groove running through, and leaves the paint band as seen once.

First run on the seven objects taught the most important thing so far: **without a chance test,
cross-view agreement is meaningless on painted sheets.** 98-100 % of 340-550 curves per object
found a partner and hundreds of cylinders and planes appeared, because tolerances are 2.5-6 % of
the object and every view is full of lines (the sofa lesson again). Every agreement and
construction now carries its probability of coincidence (candidates x window) and counts only at
5 % or less. After that: 0-107 curves per object are consistent (typewriter 0, toaster 95, mixer
107), 0-18 `through` constructions, 0-2 cylinders, no planes; the rest are marked
`coincidental`. What survives on the toaster is plausible (the panel edge running round the
sides, the slot openings), but several surviving cylinders are doubtful.

**Next: registration, not more rules.** The limiting factor is the tolerance. Normalising each
view to its outline box leaves the painted views 2.5-6 % apart (the camera's views disagree in
proportion by 9-15 %). Registering views piecewise along each shared axis by their matched
outline breakpoints (a monotone piecewise-linear map, as the drawing stage's view reconciliation
already does for outlines) should bring tolerance near a pixel where outlines agree, which shrinks
every chance probability by the same factor. That comes before trusting any construction.

**2026-11-15, registration: views mapped piecewise before they are compared.** `curve_views`
now matches outline breakpoints between two views on a shared axis (same sense of change,
mutual nearest, made monotone so one stray pair cannot fold the map), builds a monotone
piecewise-linear map from them (stretch kept between 0.5 and 2), and compares every curve,
`through`, `cylinder` and `plane` after the map. The tolerance is now the 95th percentile of the
**leave-one-out** residual: each anchor predicted from a map built without it, so a map that
only memorises its anchors does not look precise. With fewer than two anchors, or no gain over
box-only alignment, a pair stays rigid. Neighbouring breakpoints of the same sense (one step two
rows tall) are merged. Tests: an uneven stretch is recovered; opposite-sense breakpoints never
match; crossed matches cannot fold the map; a stepped tower drawn with 5 % uneven proportions
gives a plane at the groove only after registration (rigid: tolerance 0.048, no evidence).

On the seven objects (median tolerance, rigid -> registered; consistent curves; pairs
registered piecewise of 18): toaster 3.8 -> 1.6 % (91; 14), mixer 6.0 -> 1.8 % (102; 15), dryer
3.4 -> 2.0 % (115; 8), clock 3.9 -> 2.3 % (109; 11), cassette 5.2 -> 3.1 % (49; 11), typewriter
5.8 -> 4.0 % (33; 10), camera 6.0 -> 5.8 % (39; 4). What survives looks right where it is
interior: the toaster's panel band front and back, the dryer's colour band in three views, the
mixer bowl through left and right, the camera's bellows lines through left and right. Two honest
limits: most consistent curves are still outline fragments (the outline agrees with itself
after registration, which says little), and the camera barely registers: its views disagree by
more than the 10 % matching window, so few breakpoints pair. One false positive is visible (a
diagonal across the cassette's window). Features seen in one view only (the toaster's dial, the
clock face) stay seen once, as they should; they are the crutch's business.

Next: count outline fragments separately from interior evidence, then try a two-stage match for
the camera (coarse scale from the whole profile, then breakpoints), before automatic parts.
