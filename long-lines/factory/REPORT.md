# Factory report

Generated from `factory/ledger.jsonl` (latest result per asset).

| Measure | Value |
| --- | --- |
| Assets measured | 188 |
| Pass the minimum standard | 187 (99%) |
| Factory builds | 71 |
| Factory builds passing with no correction | 70 |
| Factory builds needing a person | 1 |
| Mean build time (s) | 54 |
| Same inputs -> same gauges | 101 of 104 order/input pairs |
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
| sheetset | 2 | 2 |

## Failure kinds

| Failure | Count |
| --- | --- |
| front outline matches the reference only | 1 |
| back outline matches the reference only | 1 |

## Failing assets

- **telephone_desk_kit** (kit): front outline matches the reference only 64%; back outline matches the reference only 69%
