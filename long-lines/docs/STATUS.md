# Status

## Done
- Apartment slice: systems, rooms, dressing, street, tests (39 unit, 45 smoke).
- Factory v1 (Nov 9): work orders, intake (view splitting, category sizing), lines (hull, car,
  can, surface, recipe), export standardization, quality gate, ledger, report, condition
  variants. Library gate: 118/118 at the minimum standard. See factory/REPORT.md.

- Drive batch 2 (Nov 8): Exteriors, appliances and interior trim sheets processed through
  three new lines (facade, atlas, extrude) plus 18 exterior wall surfaces. Sheet specs in
  `factory/sheets_*.json`; Sullivan Street now uses facade-line buildings.

- Sheetset line (Nov 8): first v2 sheet set (fridge_1 from ChatGPT: painted + depth + part map +
  section + manifest) builds through `intake_set`. Assembly rules from ChatGPT's review are in
  the line and in `factory/parts_catalog.json` (continuous shell, one part per physical part,
  doors as separate slabs, one base). Library gate: 186/186 at the minimum standard.

## Next (factory)
1. 100-object demonstration: needs ~100 reference sheets in REFERENCE_SPEC format from Jared
   (prompt template in factory/REFERENCE_SPEC.md); then `intake` + `build --pending`.
2. Tall buildings: the facade line builds whole painted elevations (to ~10 storeys). The
   Edison Telecom tower needs the modular version (base / repeated bay / setback / crown
   from one elevation, plan in factory/README.md).
3. Not processed yet: `objects1.png` (20 small objects in one sheet, too small per object for
   the atlas line; ask for one sheet per object or per few objects); interior trim sheets
   3, 7, 8 and 10 (same extrude line, need a sheet spec); the street concept boards (reference
   only). Jared says new sheets carry no brand names, so the brand check is retired.
4. Sheetset: openable doors need separate nodes in the GLB plus hinge markers (ties in with
   orientation/snap markers); the section image is not used yet; make the catalogue's "why"
   computable from human/object constants (finger, hand, glass, insulation).
5. Place trim pieces in the apartment (baseboards / crown along walls, casings on doorways)
   and appliances in the kitchen in place of the recipe ones.
