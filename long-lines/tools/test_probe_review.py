"""The diagnostic keeps rejected image evidence separate from lost geometry."""

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from propkit import probe_review


class ProbeReviewTests(unittest.TestCase):
    def test_unknown_final_gain_is_not_treated_as_supported(self):
        with tempfile.TemporaryDirectory() as temporary:
            report = {'probes': [{'id': 'unknown', 'view': 'front',
                                  'anchors_m': [[0, 0, .5]],
                                  'target_offsets_m': [0]}],
                      'unmet_before_reduction': ['unknown'],
                      'views': {'front': {'relief_selection': {'regions': [
                          {'region_id': 0, 'initially_supported': True,
                           'applied': True, 'final_test_gain': None}]}}}}
            records = probe_review.classify(report, (1., 1., 1.), temporary)
            self.assertEqual(records[0]['status'], 'unsupported_source')

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
            self.assertEqual(summary['supported_first_loss_counts']['unresolved'], 1)
            self.assertTrue(Path(summary['overview_image']).is_file())
            self.assertTrue(Path(summary['path']).is_file())

    def test_locates_supported_contrast_lost_in_shared_field(self):
        with tempfile.TemporaryDirectory() as temporary:
            accepted = np.zeros((64, 64), dtype=float)
            shared = np.zeros_like(accepted)
            accepted[:, 15:17] = -2.
            shared[:, 15:17] = -.4
            np.savez_compressed(Path(temporary) / 'front.npz',
                                feature_labels=np.ones((64, 64), dtype=np.uint8),
                                accepted_height_px=accepted,
                                final_shared_height_px=shared,
                                coarse_height_px=np.zeros_like(accepted),
                                metres_per_pixel=.01)
            report = {'probes': [{'id': 'groove', 'view': 'front',
                                  'anchors_m': [[-.25, -.2, .5],
                                                [-.375, -.2, .5],
                                                [-.125, -.2, .5]],
                                  'target_offsets_m': [-.02, 0., 0.]}],
                      'unmet_before_reduction': ['groove'],
                      'pre_reduction_validation': {'probes': [
                          {'id': 'groove', 'expected_contrast_m': -.02,
                           'measured_contrast_m': -.003}]},
                      'views': {'front': {'relief_selection': {'regions': [
                          {'region_id': 1, 'initially_supported': True,
                           'applied': True, 'final_test_gain': .2}]}}}}
            record = probe_review.classify(report, (1., 1., 1.), temporary)[0]
            self.assertEqual(record['status'], 'supported_unmet')
            self.assertAlmostEqual(record['stage_contrasts_m']['accepted_m'], -.02)
            self.assertAlmostEqual(record['stage_contrasts_m']['shared_field_m'], -.004)
            self.assertEqual(record['first_observed_loss'], 'shared_field_or_repair')

    def test_locates_supported_contrast_lost_at_view_fusion(self):
        with tempfile.TemporaryDirectory() as temporary:
            accepted = np.zeros((64, 64), dtype=float)
            fused = np.zeros_like(accepted)
            accepted[:, 15:17] = -2.
            fused[:, 15:17] = -.4
            np.savez_compressed(Path(temporary) / 'front.npz',
                                feature_labels=np.ones((64, 64), dtype=np.uint8),
                                accepted_height_px=accepted,
                                sampled_height_px=accepted,
                                clipped_height_px=accepted,
                                single_view_height_px=accepted,
                                fused_height_px=fused,
                                post_construction_height_px=fused,
                                post_topology_height_px=fused,
                                final_shared_height_px=fused,
                                coarse_height_px=np.zeros_like(accepted),
                                metres_per_pixel=.01)
            probe = {'view': 'front', 'anchors_m': [[-.25, -.2, .5],
                     [-.375, -.2, .5], [-.125, -.2, .5]]}
            with np.load(Path(temporary) / 'front.npz') as arrays:
                contrasts = probe_review.stage_contrasts(arrays, probe,
                                                          (1., 1., 1.))
            self.assertAlmostEqual(contrasts['accepted_m'], -.02)
            self.assertAlmostEqual(contrasts['clipped_m'], -.02)
            self.assertAlmostEqual(contrasts['single_view_m'], -.02)
            self.assertAlmostEqual(contrasts['fused_m'], -.004)
            self.assertAlmostEqual(contrasts['post_construction_m'], -.004)
            self.assertEqual(probe_review.first_observed_loss(
                -.02, -.003, contrasts), 'view_fusion')

    def test_transfer_checkpoint_does_not_blame_fusion_without_evidence(self):
        self.assertEqual(probe_review.first_observed_loss(
            -.02, -.003, {'accepted_m': -.02, 'fused_m': -.004,
                          'shared_field_m': -.004}), 'pre_fusion_or_fusion')
        self.assertEqual(probe_review.first_observed_loss(
            -.02, -.003, {'accepted_m': -.02, 'sampled_m': -.02,
                          'clipped_m': -.004, 'fused_m': -.004,
                          'shared_field_m': -.004}), 'depth_safety_cap')
        self.assertEqual(probe_review.first_observed_loss(
            -.02, -.003, {'accepted_m': -.02, 'sampled_m': -.02,
                          'clipped_m': -.02, 'fused_m': -.004,
                          'shared_field_m': -.004}), 'single_view_or_fusion')
        self.assertEqual(probe_review.first_observed_loss(
            -.02, -.003, {'accepted_m': -.02, 'sampled_m': -.02,
                          'clipped_m': -.02, 'single_view_m': -.004,
                          'fused_m': -.004, 'shared_field_m': -.004}),
            'single_view_field_transfer')

    def test_fusion_trace_flags_competing_view_without_claiming_depth(self):
        with tempfile.TemporaryDirectory() as temporary:
            trace = {'fusion_weight_floor': 1e-4, 'probes': {'groove': {
                'view': 'front', 'anchors': [
                    {'views': {'front': {'weight': .8}, 'right': {'weight': .2}}},
                    {'views': {'front': {'weight': .2}, 'right': {'weight': .8}}},
                    {'views': {'front': {'weight': .6}, 'right': {'weight': .4}}}]}}}
            (Path(temporary) / 'fusion-contributions.json').write_text(
                json.dumps(trace), encoding='utf-8')
            report = {'probes': [{'id': 'groove', 'view': 'front',
                                  'anchors_m': [[0, 0, .5]] * 3,
                                  'target_offsets_m': [0, 0, 0]}],
                      'unmet_before_reduction': ['groove']}
            record = probe_review.classify(report, (1., 1., 1.), temporary)[0]
            review = record['fusion_weight_review']
            self.assertEqual(review['competing_anchor_count'], 1)
            self.assertAlmostEqual(review['source_weight_fraction_center'], .8)
            self.assertEqual(review['below_weight_floor_anchor_count'], 0)


if __name__ == '__main__':
    unittest.main()
