# Assembly line run

| Order | Line | Intake | Build | Render | Total | Result |
|---|---|---|---|---|---|---|
| electronics_tv_crt | hull_parts | 1 s | 23 s | 19 s | 44 s | shipped |

Stations: intake (views cut from the sheet, guide lines removed) -> build (geometry, paint, bake, export, quality gate) -> render (docs/renders/NAME.png). Run with `python3 tools/line.py --drawn`.

## electronics_tv_crt
- intake: 14 views cut from electronics_tv_crt/sheet.png
- build: shipped
- render: docs/renders/electronics_tv_crt.png
