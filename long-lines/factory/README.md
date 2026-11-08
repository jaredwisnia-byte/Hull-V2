# The asset factory

The factory is the product; the models are its output. This folder holds the factory's
standards, work orders, ledger and report. The machinery is in `tools/`.

## Flow

```
reference image ─► INTAKE ─► work order ─► LINE (build) ─► BAKE/EXPORT ─► QA GATE ─┬─► shipped
 (REFERENCE_SPEC)   classify,   factory/      one per         propkit.bake    propkit.qa   │   (library.json)
                    split views, orders/      category        GLB + 3 maps    standards    └─► 1 codified
                    size from                                                                  correction,
                    categories.json                                                            then "needs_person"
every step ─► factory/ledger.jsonl ─► factory/REPORT.md (KPIs)
```

## Commands (all run inside Blender's Python)

```bash
F="blender -b --factory-startup -P long-lines/tools/factory.py --"
$F intake sheet.png furniture_chair_kitchen --category chair     # writes the work order + views
$F build furniture_chair_kitchen                                 # or --pending, --all-orders
$F qa --library                                                  # gate every asset in the library
$F report                                                        # rewrite REPORT.md
blender -b --factory-startup -P long-lines/tools/critique.py -- NAME [VIEWS]   # turnaround, for spot checks
```

## Standards (gauges)
- `standards.json`: units, axes, origin, naming, file set, size classes (texture size and
  triangle budget per class) and the **minimum acceptable standard** the gate enforces.
  The gate does not chase perfection: pass and ship, or one automatic correction, then flag.
- `categories.json`: per category, the production line, the typical real size and line
  options. This is the judgment a person used to make per object.
- `REFERENCE_SPEC.md`: the input gauge, plus a prompt template for the image generator.

## Production lines (specialized machines, shared standards)

| Line | Input | Machine | Good for |
| --- | --- | --- | --- |
| hull | multiview sheet (spec) | `propkit/hull.py`: silhouettes carve a voxel block, painted parts get depth from `part_rules.py` | boxy and solid objects: electronics, appliances, cabinets, crates, suitcases, street boxes |
| car | `car_v1` sheet | `props/cars_painted.py`: one shared body, paint swapped | vehicles of one body family |
| can | label sheet | `props/goods_painted.py` | cylindrical packaging |
| surface | square texture | `tools/make_tiles.py` | floors, walls, carpets, materials |
| recipe | none (code) | `props/*.py` hand recipes | open or thin shapes the hull can't see (bowls, frames, chairs with gaps) and one-off hero props |
| facade (next) | facade sheet | modular bays, cornices, storefronts, assembler | buildings and streets |

A new line is justified only when a category repeatedly fails another line's gate.

## Codified corrections (the gate's one retry)
- hull: an outline that fails on one view: that view becomes paint-only (dark-on-dark backs).
- hull: holes: convex silhouettes. Over budget: halve the decimation ratio.
Add a rule here and in `factory.py:correct()` whenever a person fixes the same thing twice.

## Condition variants
Every baked model takes `condition` (0 baked .. 1 derelict: faded, grimy, rusted metal),
`snow` and `frost` per placement in layout JSON. One model, many states.

## KPIs (REPORT.md)
Pass rate at the minimum standard, builds passing with no correction, builds needing a
person, mean build time, triangle statistics, failure kinds by frequency, per-line totals.
The ledger records input and output hashes, so the same inputs can be checked to give the
same output.

## Scaling to buildings (plan)
Buildings use the same standards with a facade line: establish real dimensions from
storeys (residential 3.0 m, 1960s office 3.7 m floor to floor; a 50-storey tower is about
185 m plus crown), reconstruct massing (base, shaft, setbacks, crown) from the reference,
detect the repeating bay from the facade (period autocorrelation, as `make_tiles.py` does),
model a handful of modules per building (bay, corner, base, setback, crown) at 2-3 levels
of detail, and assemble them by rule. A tall building is many bays, not a stretched box.
