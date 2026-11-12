"""The diagnostic keeps rejected image evidence separate from lost geometry."""

import tempfile
import unittest
from pathlib import Path

import numpy as np

from propkit import probe_review


class ProbeReviewTests(unittest.TestCase):
    def test_region_provenance_and_overview_are_recorded(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary) / 'shading'
            folder.mkdir()
            labels = np.ones((64, 64), dtype=np.uint8)
            labels[:, 32:] = 2
            height = np.zeros((64, 64), np.float32)
            np.savez_compressed(folder / 'front.npz', feature_labels=labels,
                                hypothesis_height_px=height,
                                accepted_height_px=height,
                                final_shared_height_px=height,
                                coarse_height_px=height,
                                observed_log_luminance=np.full((64, 64), -1.))
            probes = []
            for identifier, x in (('supported', -.25), ('rejected', .25)):
                probes.append({'id': identifier, 'view': 'front',
                               'anchors_m': [[x, -.2, .5]] * 3,
                               'target_offsets_m': [-.01, 0, 0]})
            report = {'diagnostic_folder': str(folder), 'probes': probes,
                      'unmet_before_reduction': ['supported', 'rejected'],
                      'pre_reduction_validation': {'probes': []},
                      'views': {'front': {'relief_selection': {'regions': [
                          {'region_id': 1, 'initially_supported': True,
                           'applied': True, 'final_test_gain': .2},
                          {'region_id': 2, 'initially_supported': False,
                           'applied': False, 'final_test_gain': -.1}]}}}}
            summary = probe_review.write(report, (1., 1., 1.))
            self.assertEqual(summary['supported_unmet'], 1)
            self.assertEqual(summary['unsupported_source'], 1)
            self.assertTrue(Path(summary['overview_image']).is_file())
            self.assertTrue(Path(summary['path']).is_file())


if __name__ == '__main__':
    unittest.main()
