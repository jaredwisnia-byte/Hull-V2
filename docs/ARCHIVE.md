# Run archive: plan and rules (2026-11-15)

Every Codex run leaves orders, a report, a baseline, per-attempt evidence and builds. The
archive keeps that record in one place, indexed so a question like "which runs changed the
toaster's model, and what did QA say each time?" is one query, not an afternoon of reading.

The tool lives in git (`long-lines/tools/hull_archive.py`, test `test_hull_archive.py`).
The archive itself does not: it holds run evidence and GLBs (624 MB for runs 1-3) and sits
beside the repository at `Documents/Codex/archive` (override with `HULL_ARCHIVE`;
`HULL_CODEX_WORK` sets where runs are filed from).

## What is kept and what is not

| Kept | Why |
|---|---|
| Orders, report, baseline for each run | the decisions and their reasons |
| `checks/runN-*`: patches, logs, drawing-match renders, probes | the evidence behind each verdict |
| `regression/runN-*` | before/after renders of the drawn line |
| Per build and object: `result.json`, `engineering.json`, logs | QA verdicts and measurements |
| Every model GLB, once, as `blobs/<sha1>.glb` | the output itself; identical builds share one file |

| Not kept | Why |
|---|---|
| `.blend` files and other build intermediates | builds are byte-identical for the same commit, input and toolchain (R9): rebuild from the recorded commit |
| Anything outside a run (live working state, `builds/*-current`) | not a record of a decision |

Filing **copies**; it never moves or deletes anything in `codex-work`. A file already in the
archive is never overwritten: if its source has changed since, filing stops and says so.

## The index (`hull.db`, SQLite)

| Table | One row per | Holds |
|---|---|---|
| `runs` | run | date, start and final revision, disposition line from the report |
| `builds` | build x object | GLB SHA-1, blob path, status, QA pass, full `result.json` |
| `attempts` | `checks/runN-orderM-attemptK` folder | run, order, attempt |
| `cells` | object row in any markdown table of orders/report/baseline | section, column, value |
| `glb_hashes` (view) | cell holding a SHA-1 | the hash tables Codex and Claude wrote |
| `files` | archived file | source path, size, SHA-256 |

Examples:
```
python long-lines/tools/hull_archive.py query "select run, build, glb_sha1 from builds where object='001_toaster'"
python long-lines/tools/hull_archive.py query "select build, object, json_extract(result_json, '$.qa.fails') from builds where run=3"
```
`query` opens the database read-only.

## Procedure (part of every run review)

1. Codex finishes or stops; Claude reads the report (unchanged).
2. **File the run** before merging anything from it: `hull_archive.py file N`, then
   `hull_archive.py verify`. Both must succeed; a refusal means a filed file changed after
   the fact, and that is investigated, not overwritten.
3. Merge (with Jared's go-ahead) and write the next orders. The next orders' baseline table
   can be checked against `glb_hashes` for the previous run.
4. Clearing `codex-work` intermediates (today about 3 GB of `builds/`) happens only after
   step 2 passed and only with Jared's yes, each time.

## Phases

1. **Done (2026-11-15):** tool, index and test; runs 1-3, Codex briefs A-C, parked orders and
   Claude's session scripts and determinism hash lists filed; 3,121 files verified.
2. **Run 4:** file it during its review; add its extras (if any loose files) to `EXTRAS`.
3. **Drawing QA per view:** Order 5 (R10) makes QA report p95 distance, size error and IoU per
   view; add a `views` table (run, build, object, view, p95_mm, size_mm, iou, pass) filled
   from `result.json`, so tolerance trends are queryable per object and view.
4. **Trend report:** a query script that prints, per object, the GLB hash and per-view QA
   across runs, and flags any change of bytes that a run did not intend (an R9 check over
   history, not just within a run).
5. **Rebuild spot check:** pick an archived build, rebuild it from its recorded commit with
   the saved-intake harness, and confirm the same SHA-1; proves "not kept, can be rebuilt".
6. **Off-machine copy:** `hull.db` is small; copy the archive (or at least `hull.db`, reports
   and orders) somewhere other than this PC. Destination is Jared's choice.

## Known gaps

- Run 1's report gives no starting revision in a form the filer reads; its `start_rev` is empty.
- No archived build passed QA. That is the record, not an import error: under the old QA
  every build was `needs_review`.
- Markdown tables are parsed as written; a table without an object name in a cell
  (`001_toaster` and so on) is kept as a file but not indexed.
