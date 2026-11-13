# Hull factory

Painted reference sheets in, textured 3D props out. Everything under this folder is the
asset factory; the directory keeps its historical name.

![Library contact sheet](docs/library/contact_sheet_1.png)

## What is here

| Folder | Contents |
| --- | --- |
| `tools/` | The factory: `factory.py` (intake, build, QA, report), `line.py` (the assembly line), the shared kit `propkit/`, and hand recipes in `props/` |
| `factory/` | Standards, categories, sizing manual, work orders, ledger and KPIs. Start with [factory/README.md](factory/README.md) |
| `assets/source_textures/` | The painted reference views each order is built from |
| `assets/props/` | The built library: one folder per prop (GLB plus albedo, normal and ORM maps) and `library.json` |
| `assets/surfaces/`, `data/surfaces.json` | Seamless painted surface tiles and their catalogue, used by recipes |
| `docs/` | Renders, benchmarks, audits, and `LESSONS.md` |

Exported GLBs are glTF, Y-up, metres, with the front facing +Z and the origin at the floor
contact. They load in any engine or DCC tool; the maps are separate PNGs
(`tools/open_in_blender.py NAME` wires them up in Blender).

## Run it

Needs Blender 5.2 and Python 3.13 with `requirements-core.txt` (see the root README).

```bash
# Build and render orders down the assembly line (every station in its own Blender worker)
python long-lines/tools/line.py car_sedan_tan wallphone_rotary
python long-lines/tools/line.py --drawn          # every order built from a drawing

# Individual stations
blender -b --factory-startup -P long-lines/tools/factory.py -- build NAME
blender -b --factory-startup -P long-lines/tools/factory.py -- qa --library
blender -b --factory-startup -P long-lines/tools/factory.py -- report
```

Results land in `docs/renders/NAME.png`, the contact sheet `docs/renders/line.png` and the
run log `docs/renders/LINE.md`. Orders marked `"locked"` (approved assets) are rendered,
never rebuilt.

## Production lines

hull (multiview sheets), hull_parts (parts sheets), sheetset, atlas (appliance part
atlases), extrude (trim and mouldings), facade (building elevations), car, can, surface
and recipe. Each line, its inputs and its limits are described in
[factory/README.md](factory/README.md); the input format is in
[factory/REFERENCE_SPEC.md](factory/REFERENCE_SPEC.md).

## Judging a change

Rebuild the drawn set and compare `docs/renders/line.png` before and after. A change that
makes any of these props worse is not done (see the root `AGENTS.md`).
