# Assembly line run

| Order | Line | Intake | Build | Render | Total | Result |
|---|---|---|---|---|---|---|
| car_sedan_tan | hull | 0 s | 51 s | 12 s | 64 s | shipped |
| coffee_maker_drip | hull_parts | 0 s | 36 s | 21 s | 58 s | shipped |
| electronics_tv_westbury | hull | 0 s | 32 s | 18 s | 50 s | shipped |
| sofa_olive_suede | hull_parts | 0 s | 152 s | 17 s | 169 s | shipped |
| table_leg_carved | hull | 1 s | 134 s | 9 s | 144 s | shipped |
| table_leg_guided | hull | 2 s | 148 s | 10 s | 160 s | shipped |
| wallphone_rotary | hull_parts | 1 s | 50 s | 16 s | 67 s | shipped |

Stations: intake (views cut from the sheet, guide lines removed) -> build (geometry, paint, bake, export, quality gate) -> render (docs/renders/NAME.png). Run with `python3 tools/line.py --drawn`.

## car_sedan_tan
- intake: 5 views on file
- build: shipped
- render: docs/renders/car_sedan_tan.png

## coffee_maker_drip
- intake: 27 views on file
- build: shipped
- render: docs/renders/coffee_maker_drip.png

## electronics_tv_westbury
- intake: 5 views on file
- build: shipped
- render: docs/renders/electronics_tv_westbury.png

## sofa_olive_suede
- intake: 23 views on file
- build: shipped
- render: docs/renders/sofa_olive_suede.png

## table_leg_carved
- intake: 5 views cut from table_leg_carved/sheet.png
- build: shipped
- render: docs/renders/table_leg_carved.png

## table_leg_guided
- intake: 6 views cut from table_leg_guided/sheet.png; guide lines read and painted out
- build: shipped
- render: docs/renders/table_leg_guided.png

## wallphone_rotary
- intake: 25 views cut from wallphone_rotary/sheet.png
- build: shipped
- render: docs/renders/wallphone_rotary.png

## After the run
- electronics_tv_westbury: shipped by the line, then restored to the version Jared approved and its order
  locked. The rebuild was close, but today's hull drops the faint recessed bezel step the approved one has;
  an approved asset must not get worse because the line ran. Locked orders are rendered, never rebuilt.
