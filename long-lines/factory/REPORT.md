# Factory report

Generated from `factory/ledger.jsonl` (latest result per asset).

| Measure | Value |
| --- | --- |
| Assets measured | 187 |
| Pass the minimum standard | 186 (99%) |
| Factory builds | 70 |
| Factory builds passing with no correction | 69 |
| Factory builds needing a person | 1 |
| Mean build time (s) | 55 |
| Same inputs -> same gauges | 88 of 91 order/input pairs |
| Median triangles | 1128 |
| Max triangles | 38000 |

## By production line

| Line | Assets | Passing |
| --- | --- | --- |
| atlas | 10 | 10 |
| extrude | 41 | 41 |
| facade | 16 | 16 |
| hull | 1 | 1 |
| kit | 1 | 0 |
| painted | 11 | 11 |
| recipe | 106 | 106 |
| sheetset | 1 | 1 |

## Failure kinds

| Failure | Count |
| --- | --- |
| front outline matches the reference only | 1 |
| back outline matches the reference only | 1 |

## Failing assets

- **telephone_desk_kit** (kit): front outline matches the reference only 64%; back outline matches the reference only 69%
