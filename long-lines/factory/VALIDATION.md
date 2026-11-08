# Geometry validation protocol (Jared, Nov 8 2026)

Every asset is a physical object. Every meaningful feature needs support from at least one of:
visual evidence, functional necessity, manufacturing necessity, structural necessity,
historical/design convention, intentional aesthetics. Unsupported features are suspected errors,
flagged, not silently deleted. The goal is to stop each class of error recurring, not to fix one model.

Rules (short form; full text in the session record of Nov 8):
1. Justify every protrusion: what it is, why it sticks out, how it attaches, size vs function, consistent across views.
2. Justify every recess: what goes in, clearance, surrounding material, through or blind, conflicts.
3. Reconstruct the assembly: continuous shells, separate parts, moving parts, joints, seals, surface decoration.
4. Cross-view consistency: views agree on width, depth, height and feature positions; report conflicts.
5. Physical plausibility at real scale; keep measured, estimated and assumed dimensions apart.
6. A texture line is not an edge: only build what has physical depth.
7. Plausible manufacturing method (sheet metal, casting, moulding, wood, masonry...).
8. Inspect from all sides and three-quarters: overhangs, bulges, floating parts, discontinuities.
9. Resolve uncertainty with function; record estimates and confidence; prefer the simplest geometry.
10. Final review per feature: what, why, attached to what, consistent, sized right, geometry or texture,
    manufacturable, does removing it make the model more or less faithful?

Correction priority: 1 structure, 2 geometric plausibility, 3 assembly, 4 surface, 5 decoration.
Don't add polygons unless needed. No category exceptions without a demonstrated need.

## Status in the factory

| Rule | How the factory applies it | State |
| --- | --- | --- |
| 1, 6 evidence | sheetset: part map region + depth relief or side profile, else painted only | automated |
| 2, 9 sizing by function | `sizing_manual.json` facts and formulas; report gives the source of every size | automated |
| 3 assembly | assembly rules: continuous shell, one part per physical part, doors alike, one base | automated (sheetset) |
| 4 cross-view consistency | | to build: compare view extents and feature positions, report conflicts |
| 5 measured vs estimated | report `sources`: side view / depth map / catalogue / painted only | partial: no confidence yet |
| 7 manufacturing | | to build: per-category construction in the manual (sheet metal = uniform shell, rounded bends) |
| 8 multi-angle | critic turnaround, clay render, `match_check.py`, shell continuity check | partly automated |
| texture | blended view projection with occlusion, baked into the mesh's own UV atlas; UV stretch gauge in the gate | automated (Nov 8) |
| 4 cross-view (partial) | a side-view part is built only if the front view shows something past that edge | automated (sheet sets) |
| 10 per-feature ablation | | to build: keep a part only if it improves agreement with the reference depth |
| correction priority | gate's codified corrections | to order by this hierarchy |
