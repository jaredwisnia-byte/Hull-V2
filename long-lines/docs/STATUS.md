# Status

## Done
- Apartment slice: systems, rooms, dressing, street, tests (39 unit, 45 smoke).
- Factory v1 (Nov 9): work orders, intake (view splitting, category sizing), lines (hull, car,
  can, surface, recipe), export standardization, quality gate, ledger, report, condition
  variants. Library gate: 118/118 at the minimum standard. See factory/REPORT.md.

## Next (factory)
1. 100-object demonstration: needs ~100 reference sheets in REFERENCE_SPEC format from Jared
   (prompt template in factory/REFERENCE_SPEC.md); then `intake` + `build --pending`.
2. Facade line for buildings (plan in factory/README.md), starting with the Edison Telecom tower.
3. Brand check is the remaining manual step on every image; consider a text-detection check.
