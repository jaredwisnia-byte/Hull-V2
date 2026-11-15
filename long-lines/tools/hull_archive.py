"""Hull run archive: copies a finished Codex run into archive/ and indexes it in hull.db.

Plan and rules: long-lines/docs/ARCHIVE.md. The archive itself is not in git (it holds
run evidence and GLBs); this tool is.

Usage (Python 3.13, standard library only):
    python hull_archive.py file RUN            # e.g. file 3; copies, never moves or deletes
    python hull_archive.py extra SRC DEST KIND # file one more path (file or folder) under archive/DEST
    python hull_archive.py query "SQL"         # read-only query against hull.db
    python hull_archive.py verify              # re-hash every archived file against the index

Sources come from codex-work by rule (RUN_REPORT_runN.md, CODEX_ORDERS_runN.md,
BASELINE_runN.md, checks/runN-*, regression/runN-*, builds/runN-*) plus the
per-run extras in EXTRAS. Model GLBs are stored once each by content
(blobs/<sha1>.glb); builds are deterministic, so .blend files and other
intermediates are not kept: rebuild from the recorded commit to get them back.
"""
import hashlib, json, os, re, shutil, sqlite3, sys, time
from contextlib import closing
from pathlib import Path

# The repository, the archive and codex-work sit side by side (Documents/Codex/...);
# HULL_ARCHIVE and HULL_CODEX_WORK override either location.
_BESIDE = Path(__file__).resolve().parents[2].parent
ROOT = Path(os.environ.get('HULL_ARCHIVE', _BESIDE / 'archive'))
WORK = Path(os.environ.get('HULL_CODEX_WORK', _BESIDE / 'codex-work'))
DB = ROOT / 'hull.db'

# Files from runs that predate the runN naming, or that sit loose in codex-work.
EXTRAS = {
    1: [('ORDER1.md', 'orders'), ('ORDER2.md', 'orders'),
        ('regression/before', 'regression'), ('regression/after', 'regression'),
        ('builds/order1', 'build'), ('builds/order2-attempt1', 'build'),
        ('builds/order2-attempt2', 'build'), ('builds/order2-attempt3', 'build')],
    3: [('cad-diagnosis.log', 'log'), ('drawn-run3-baseline.log', 'log'),
        ('drawn-run3-order2-attempt1.log', 'log'), ('ledger-before-run3.jsonl', 'ledger')],
}
BUILD_KEEP = {'result.json', 'engineering.json', 'build-console.log', 'render.log'}

SCHEMA = """
create table if not exists runs(run integer primary key, date text, start_rev text,
    final_rev text, disposition text, archived_at text);
create table if not exists files(dest text primary key, run integer, kind text,
    src text, bytes integer, sha256 text);
create table if not exists builds(run integer, build text, object text, glb_sha1 text,
    blob text, status text, qa_pass integer, result_json text,
    primary key(run, build, object));
create table if not exists attempts(run integer, order_no integer, attempt integer,
    folder text primary key);
create table if not exists cells(run integer, source text, section text, object text,
    col text, value text);
create view if not exists glb_hashes as
    select run, source, section, object, col, value as sha1 from cells
    where length(replace(value, '`', '')) = 40 and replace(value, '`', '') not glob '*[^0-9a-f]*';
"""


def sha(path, algo='sha256'):
    h = hashlib.new(algo)
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def copy(db, run, kind, src, dest):
    """Copy one file; refuse to overwrite a different archived file."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    digest = sha(src)
    if dest.exists():
        if sha(dest) != digest:
            raise SystemExit(f'refusing to overwrite changed archive file: {dest}')
    else:
        shutil.copy2(src, dest)
    db.execute('insert or replace into files values(?,?,?,?,?,?)',
               (dest.relative_to(ROOT).as_posix(), run, kind,
                src.relative_to(WORK).as_posix(), src.stat().st_size, digest))


def copy_tree(db, run, kind, src, dest):
    for p in sorted(src.rglob('*')):
        if p.is_file():
            copy(db, run, kind, p, dest / p.relative_to(src))


def file_build(db, run, src):
    """One build folder: GLBs by content, result files beside them, index each object."""
    out = ROOT / 'runs' / f'run{run}' / 'builds' / src.name
    # build-level evidence (summaries, contact sheets, CAD audits, cross-sections) is kept whole
    for p in sorted(src.iterdir()):
        if p.is_file():
            copy(db, run, 'build', p, out / p.name)
        elif not (p / 'model.glb').exists():
            copy_tree(db, run, 'build', p, out / p.name)
    for obj in sorted(d for d in src.iterdir() if d.is_dir() and (d / 'model.glb').exists()):
        for p in sorted(obj.iterdir()):
            if p.name in BUILD_KEEP:
                copy(db, run, 'build', p, out / obj.name / p.name)
        glb = obj / 'model.glb'
        if not glb.exists():
            continue
        h1 = sha(glb, 'sha1')
        blob = ROOT / 'blobs' / f'{h1}.glb'
        copy(db, run, 'glb', glb, blob)
        res = obj / 'result.json'
        data = json.loads(res.read_text(encoding='utf-8')) if res.exists() else {}
        qa = (data.get('qa') or {}).get('pass', data.get('qa_pass'))
        db.execute('insert or replace into builds values(?,?,?,?,?,?,?,?)',
                   (run, src.name, obj.name, h1, blob.relative_to(ROOT).as_posix(),
                    data.get('status'), None if qa is None else int(bool(qa)),
                    json.dumps(data, sort_keys=True) if data else None))


def parse_tables(db, run, source, text):
    """Every markdown table row that names an object (001_toaster ...) becomes cells."""
    section, header = '', None
    for line in text.splitlines():
        if line.startswith('#'):
            section, header = line.lstrip('#').strip(), None
            continue
        if not line.startswith('|'):
            header = None
            continue
        cells = [c.strip() for c in line.strip().strip('|').split('|')]
        if all(re.fullmatch(r':?-+:?', c) for c in cells):
            continue
        if header is None:
            header = cells
            continue
        obj = next((c.strip('`').split('/')[-1] for c in cells
                    if re.fullmatch(r'`?[\w/-]*\d{3}_\w+`?', c)), None)
        if obj is None:
            continue
        for col, value in zip(header, cells):
            db.execute('insert into cells values(?,?,?,?,?,?)',
                       (run, source, section, obj, col, value))


def parse_report(text, date=None):
    """Date, start and final revision, disposition. Reports are prose, so several phrasings
    are accepted; `date` (the report file's date) is the fallback when none is written."""
    def grab(*patterns):
        for pattern in patterns:
            m = re.search(pattern, text, re.I | re.M)
            if m:
                return m.group(1).strip()
        return None
    sha_ = r'`?([0-9a-f]{7,40})'
    disposition = grab(r'Disposition:\s*\*{0,2}([^*\n]+)',
                       r'^\*\*((?:stopped|complete|pass|fail|order)[^*]*)\*\*')
    start = grab(r'Starting (?:and final )?revision:\s*' + sha_, r'reset\b[^\n]*?\bto\s+' + sha_)
    final = grab(r'Final revision:\s*' + sha_, r'local commit\s+' + sha_,
                 r'Starting and final revision:\s*' + sha_) or start
    return grab(r'Date:\s*([\d-]{10})') or date, start, final, disposition


def file_run(run):
    """File run N. A refusal part-way rolls the index back; copied files stay and re-verify."""
    with closing(sqlite3.connect(DB)) as db:
        _file_run(db, run)


def _file_run(db, run):
    db.executescript(SCHEMA)
    db.execute('delete from cells where run=?', (run,))
    dest = ROOT / 'runs' / f'run{run}'
    for name, kind in ((f'CODEX_ORDERS_run{run}.md', 'orders'),
                       (f'RUN_REPORT_run{run}.md', 'report'),
                       (f'BASELINE_run{run}.md', 'baseline')):
        src = WORK / name
        if src.exists():
            copy(db, run, kind, src, dest / name)
            parse_tables(db, run, name, src.read_text(encoding='utf-8'))
    for src in sorted(WORK.glob(f'checks/run{run}-*')):
        kind = 'check'
        if src.is_dir():
            copy_tree(db, run, kind, src, dest / 'checks' / src.name)
            m = re.fullmatch(rf'run{run}-order(\d+)-attempt(\d+)', src.name)
            if m:
                db.execute('insert or replace into attempts values(?,?,?,?)',
                           (run, int(m[1]), int(m[2]), src.name))
        else:
            copy(db, run, kind, src, dest / 'checks' / src.name)
    for src in sorted(WORK.glob(f'regression/run{run}-*')):
        copy_tree(db, run, 'regression', src, dest / 'regression' / src.name)
    for src in sorted(WORK.glob(f'builds/run{run}-*')):
        file_build(db, run, src)
    for rel, kind in EXTRAS.get(run, []):
        src = WORK / rel
        if kind == 'build':
            file_build(db, run, src)
        elif src.is_dir():
            copy_tree(db, run, kind, src, dest / rel)
        else:
            copy(db, run, kind, src, dest / src.name)
            if src.suffix == '.md':
                parse_tables(db, run, src.name, src.read_text(encoding='utf-8'))
    report = WORK / f'RUN_REPORT_run{run}.md'
    info = (parse_report(report.read_text(encoding='utf-8'),
                         time.strftime('%Y-%m-%d', time.localtime(report.stat().st_mtime)))
            if report.exists() else (None,) * 4)
    db.execute('insert or replace into runs values(?,?,?,?,?,?)',
               (run, *info, time.strftime('%Y-%m-%d %H:%M:%S')))
    db.commit()
    n = db.execute('select count(*), coalesce(sum(bytes),0) from files where run=?', (run,)).fetchone()
    print(f'run {run}: {n[0]} files, {n[1] / 1e6:.1f} MB catalogued')


def extra(src, dest, kind):
    """File something outside the run rules (briefs, Claude's scripts). Run is NULL."""
    global WORK
    src = Path(src).resolve()
    WORK = src.parent if src.is_file() else src
    target = ROOT / dest
    with closing(sqlite3.connect(DB)) as db:
        db.executescript(SCHEMA)
        if src.is_dir():
            copy_tree(db, None, kind, src, target)
        else:
            copy(db, None, kind, src, target / src.name)
        db.commit()


def verify():
    with closing(sqlite3.connect(DB)) as db:
        rows = db.execute('select dest, sha256 from files').fetchall()
    bad = [d for d, h in rows if not (ROOT / d).exists() or sha(ROOT / d) != h]
    total = len(rows)
    print(f'{total - len(bad)}/{total} archived files match the index')
    for d in bad:
        print('MISMATCH', d)
    return not bad


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    if cmd == 'file':
        file_run(int(sys.argv[2]))
    elif cmd == 'extra':
        extra(*sys.argv[2:5])
    elif cmd == 'query':
        with closing(sqlite3.connect(f'file:{DB}?mode=ro', uri=True)) as db:
            cur = db.execute(sys.argv[2])
            print('\t'.join(c[0] for c in cur.description))
            for row in cur:
                print('\t'.join('' if v is None else str(v) for v in row))
    elif cmd == 'verify':
        sys.exit(0 if verify() else 1)
    else:
        print(__doc__)
