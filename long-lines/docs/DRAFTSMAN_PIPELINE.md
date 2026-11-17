# The draftsman pipeline: one drawing stage, every tool in order (plan, 2026-11-16)

Jared's method: a draftsman reads the views by carrying every feature from view to view along
projection lines. The drawing that results is the book of truth, and the model is built from it.
Today the tools for this exist but run apart (`curves`, `curve_views`, the trained edge detector,
`draftsman`, the lever fix, the knob rule). This plan joins them into one stage, in order, inside
`drafting.prepare`, and builds the model from its result.

Rules for the whole plan:
- Additive. The outline body stays; what already works stays (lever fix, roundness, openings,
  texturing). New stages only take over where their evidence is stronger, and say so.
- General. No object names, no per-object numbers. Every rule is checked on all seven objects and
  the drawn set unchanged before it is trusted.
- Visible. Each stage writes an image Jared can check, and its decisions into `drawing.json`.
- Repeatable (R9). Same input, same bytes.

## Stage 1: views (exists)
Orient, size and outline the six views (`drafting.prepare` today).
Check image: the six oriented views with their outlines.

## Stage 2: features in every view
Trace every feature in all six views as a closed outline of lines and arcs: structural edges from
`feature_regions` with the trained detector (`tracing_backend`, auto), curves from `curves.py` as
supporting evidence, each area fitted by `drafting.fit_profile`. Small repeated features (keys)
are grouped by paint and size.
Check image: each view with every traced feature outline.
Done when: knob circles, lever, keys, space bar traced on the typewriter; nothing object-specific.

## Stage 3: alignment and projection matching
Register every view onto its reference (width and height on the front, depth on the side) with
`curve_views` outline breakpoints plus repeated-part rows. Match features along projection lines:
feature-to-feature pairs confirmed in the third view (feature or paint), the shape view deciding
the cross-section, each feature used once; rows of repeated parts completed along their own row.
All combinations of opposite views are read, so a part best seen from the left or back counts.
Check image: the draftsman sheet, third-angle, true scale, six views; each part solid only in the
views that confirm it; projection lines and the 45-degree mitre.
Done when: on the typewriter the knobs, lever, space bar and every key row are matched with no
junk boxes; the other six sheets show no matches Jared would reject.

## Stage 4: parts in the drawing
Each matched part goes into the drawing record: its box (mm), its shape view, its traced profile
(lines and arcs), its confirming views. Drawn into the DXF and the drawing PNG as parts, with the
draftsman sheet beside them.
Check image: the drawing sheet with parts on it.

## Stage 5: the model from the drawing
The body stays the outline body (with the lever fix and roundness). Each part then refines it:
- a part sticking out of the body is cut to its shape-view profile along its length (a knob round);
- a part sitting on a face (a key) is raised to its own box, with the gaps between instances cut
  down to the surface it sits on;
- a recess the parts imply (the type basket) is cut to the depth the side view shows.
The CAD solid takes the same parts as features on the profile solid.
Check: renders, clay turnaround and GLB of the typewriter; QA numbers against the lever-fix build.
Done when: the typewriter is visibly better than the lever-fix build (round knobs, keys, no deck
plateau) and no other object gets worse.

## Stage 6: all objects
Build all seven and the drawn set; show every sheet and turnaround; commit only what passes.

## Order of work and checkpoints
1. Stage 2 into `drafting.prepare` (feature images in every build). Show Jared.
2. Stage 3 (sheet in every build); clean the matching until the typewriter sheet is right. Show.
3. Run stages 1-3 on all seven; show the seven sheets; fix general faults only.
4. Stage 4. Show.
5. Stage 5, one part kind at a time (protruding parts, then raised parts, then recesses), building
   the typewriter after each and showing it; then all seven.
6. Commit; merge only with Jared's yes.
