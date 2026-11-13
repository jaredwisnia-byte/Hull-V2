"""Resume, provenance, cache isolation and corrupted-checkpoint recovery."""
import tempfile
import unittest
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
import numpy as np
from propkit.build_memory import BuildMemory
from propkit import regional_relief
import test_regional_relief as fixtures


class MemoryContracts(unittest.TestCase):
    def test_replaced_checkpoint_is_reported_without_collection(self):
        with tempfile.TemporaryDirectory() as folder, closing(BuildMemory(Path(folder) / 'memory.sqlite3')) as memory:
            record = {'status': 'accepted'}
            memory.save('key', 'v1', record, [1], np.ones((4, 4)), np.zeros((4, 4)))
            first = next(memory.artifacts.glob('*.npz'))
            memory.save('key', 'v1', record, [1], np.ones((4, 4)) * 2, np.zeros((4, 4)))
            report = memory.retention_inventory(verify_hashes=True)
            self.assertTrue(report['snapshot_consistent'])
            self.assertFalse(report['collection_authorized'])
            self.assertEqual(report['counts'], {'referenced': 1, 'unreferenced': 1})
            self.assertEqual(report['files']['unreferenced'][0]['name'], first.name)
            self.assertTrue(first.is_file())
            self.assertTrue(report['files']['referenced'][0]['matches_record'])

    def test_final_failure_is_recorded_separately_from_geometry_truth(self):
        import json
        from propkit.memory_outcomes import record
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'memory.sqlite3'
            result = record({'pass': False, 'fails': ['depth lost'], 'metrics': {'tris': 3000}},
                            {'asset': 'synthetic_test'}, path=path)
            self.assertEqual(result['status'], 'recorded')
            with closing(BuildMemory(path)) as memory:
                payload = json.loads(memory.db.execute(
                    "SELECT detail FROM events WHERE state='build_outcome'").fetchone()[0])
                self.assertFalse(payload['outcome']['pass'])
                self.assertFalse(payload['physical_geometry_verified'])
                self.assertEqual(memory.summary()['patches'], 0)

    def test_record_is_versioned_and_never_self_certifies_geometry(self):
        with tempfile.TemporaryDirectory() as folder, closing(BuildMemory(Path(folder) / 'memory.sqlite3')) as memory:
            record = {'status': 'accepted', 'physical_geometry_verified': True,
                      'reference': {'accepted': True, 'strategy': 'quadratic:1'}}
            memory.save('key', 'v1', record, [
                        1, 2, 3], np.ones((4, 4)), np.zeros((4, 4)))
            self.assertIsNone(memory.load('key', 'v2'))
            height, material, stored = memory.load('key', 'v1')
            self.assertFalse(stored['physical_geometry_verified'])
            hints = memory.suggest([1, 2, 3], 'v1')
            self.assertEqual(hints[0]['strategy'], 'quadratic:1')
            self.assertEqual(memory.suggest([100, 2, 3], 'v1'), [])

    def test_corrupt_artifact_is_not_replayed(self):
        with tempfile.TemporaryDirectory() as folder, closing(BuildMemory(Path(folder) / 'memory.sqlite3')) as memory:
            memory.save('key', 'v1', {'status': 'preserved_existing'}, [
                        0], np.ones((4, 4)), np.zeros((4, 4)))
            path = next(memory.artifacts.glob('*.npz'))
            path.write_bytes(b'interrupted or corrupt')
            self.assertIsNone(memory.load('key', 'v1'))
            self.assertEqual(memory.db.execute(
                "SELECT state FROM events ORDER BY id DESC LIMIT 1").fetchone()[0], 'checkpoint_invalid')

    def test_deferred_region_resumes_then_replays_without_refitting(self):
        args, truth, region = fixtures.LocalReliefContracts().fixture(-1)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'memory.sqlite3'
            first, _, report = regional_relief.refine(
                *args, memory_path=path, maximum_regions=0, envelope=False)
            self.assertEqual(report['regions'][0]['status'], 'deferred')
            second, material, report = regional_relief.refine(
                *args, memory_path=path, maximum_regions=1, envelope=False)
            self.assertEqual(report['new_regions_processed'], 1)
            with patch.object(regional_relief, 'reference_surface', side_effect=AssertionError('must resume')):
                third, replayed, report = regional_relief.refine(
                    *args, memory_path=path, maximum_regions=0, envelope=False)
            self.assertEqual(report['resumed_regions'], 1)
            np.testing.assert_array_equal(second, third)
            np.testing.assert_array_equal(material, replayed)

    def test_final_test_pixels_do_not_change_memory_identity(self):
        args, truth, region = fixtures.LocalReliefContracts().fixture(-1)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'memory.sqlite3'
            first, _, report = regional_relief.refine(
                *args, memory_path=path, envelope=False)
            changed = list(args)
            y, x = np.indices(region.shape)
            holdout = (y + 3 * x) % 9 == 1
            changed[3] = args[3].copy()
            changed[3][holdout] += 1
            changed[4] = args[4].copy()
            changed[4][holdout] -= 1
            second, _, report = regional_relief.refine(
                *changed, memory_path=path, envelope=False)
            self.assertEqual(report['resumed_regions'], 1)
            np.testing.assert_array_equal(first, second)


if __name__ == '__main__':
    unittest.main()
