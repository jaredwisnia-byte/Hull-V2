"""Run archive: files a fake run, stores identical GLBs once, never overwrites, verifies."""
import json, sqlite3, sys, tempfile, unittest
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hull_archive as ha


def fake_run(work, run):
    (work / f'RUN_REPORT_run{run}.md').write_text(
        'Date: 2026-11-15\nStarting revision: `aaaaaaa`\nFinal revision: `bbbbbbb`\n'
        '**STOPPED at Order 3.**\n\n# Baseline\n\n| Object | GLB SHA-1 |\n|---|---|\n'
        '| 001_toaster | `6e681abc8671a0219ad60615f351a1b7d2e819df` |\n', encoding='utf-8')
    (work / f'checks/run{run}-order3-attempt2').mkdir(parents=True)
    (work / f'checks/run{run}-order3-attempt2/source.patch').write_text('diff', encoding='utf-8')
    for build in (f'run{run}-baseline', f'run{run}-baseline-repeat'):
        obj = work / 'builds' / build / '001_toaster'
        obj.mkdir(parents=True)
        (obj / 'model.glb').write_bytes(b'glTF same bytes')
        (obj / 'model.blend').write_bytes(b'not kept')
        (obj / 'result.json').write_text(json.dumps(
            {'status': 'needs_review', 'qa': {'pass': False}}), encoding='utf-8')
        (work / 'builds' / build / 'summary.json').write_text('{}', encoding='utf-8')
        (work / 'builds' / build / 'cross-sections').mkdir()
        (work / 'builds' / build / 'cross-sections' / 'a.png').write_bytes(b'png')


class Archive(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)   # runs after the database handles close
        base = Path(self.tmp.name)
        ha.ROOT, ha.WORK = base / 'archive', base / 'work'
        ha.DB = ha.ROOT / 'hull.db'
        ha.ROOT.mkdir(); ha.WORK.mkdir()
        fake_run(ha.WORK, 7)

    def test_files_indexes_and_deduplicates(self):
        ha.file_run(7)
        db = self.enterContext(closing(sqlite3.connect(ha.DB)))
        self.assertEqual(db.execute('select start_rev, final_rev from runs').fetchone(),
                         ('aaaaaaa', 'bbbbbbb'))
        builds = db.execute('select build, blob, status, qa_pass from builds').fetchall()
        self.assertEqual(len(builds), 2)
        self.assertEqual(len({b[1] for b in builds}), 1, 'identical GLBs stored once')
        self.assertEqual(builds[0][2:], ('needs_review', 0))
        self.assertEqual(len(list((ha.ROOT / 'blobs').iterdir())), 1)
        self.assertFalse(list(ha.ROOT.rglob('*.blend')), '.blend files are not kept')
        kept = ha.ROOT / 'runs/run7/builds/run7-baseline'
        self.assertTrue((kept / 'summary.json').exists() and (kept / 'cross-sections/a.png').exists(),
                        'build-level evidence is kept')
        self.assertEqual(db.execute('select order_no, attempt from attempts').fetchone(), (3, 2))
        self.assertEqual(db.execute('select object, sha1 from glb_hashes').fetchone(),
                         ('001_toaster', '`6e681abc8671a0219ad60615f351a1b7d2e819df`'))
        self.assertTrue((ha.WORK / 'builds/run7-baseline/001_toaster/model.blend').exists(),
                        'filing copies; the source is untouched')
        self.assertTrue(ha.verify())

    def test_refiling_is_idempotent_and_overwrite_refused(self):
        ha.file_run(7)
        ha.file_run(7)
        db = self.enterContext(closing(sqlite3.connect(ha.DB)))
        self.assertEqual(db.execute('select count(*) from builds').fetchone()[0], 2)
        self.assertEqual(db.execute('select count(*) from cells').fetchone()[0], 2)
        (ha.WORK / 'checks/run7-order3-attempt2/source.patch').write_text('changed')
        with self.assertRaises(SystemExit):
            ha.file_run(7)

    def test_verify_catches_a_damaged_copy(self):
        ha.file_run(7)
        (ha.ROOT / 'runs/run7/checks/run7-order3-attempt2/source.patch').write_text('x')
        self.assertFalse(ha.verify())


if __name__ == '__main__':
    unittest.main()
