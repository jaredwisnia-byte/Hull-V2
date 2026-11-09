# Assembly line run

| Order | Line | Intake | Build | Render | Total | Result |
|---|---|---|---|---|---|---|
| electronics_tv_crt2 | hull | 1 s | 45 s | 19 s | 65 s | shipped |

Stations: intake (views cut from the sheet, guide lines removed) -> build (geometry, paint, bake, export, quality gate) -> render (docs/renders/NAME.png). Run with `python3 tools/line.py --drawn`.

## electronics_tv_crt2
- intake: 6 views cut from electronics_tv_crt2/sheet.png
- build: shipped
- render: docs/renders/electronics_tv_crt2.png
