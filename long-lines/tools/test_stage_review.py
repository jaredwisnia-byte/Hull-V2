"""The stage critic reports evidence and never grants itself geometry authority."""
import copy
import tempfile
import unittest
from pathlib import Path
import numpy as np
from propkit.stage_review import inspect


class ReviewContracts(unittest.TestCase):
    def test_loss_between_dense_and_exported_geometry_is_identified(self):
        measured = {'relief': {'pre_reduction_validation': {'probes': [
            {'id': 'a', 'retained': True}, {'id': 'b', 'retained': True}]}}}
        result = {'metrics': {'surface_features': {'probes': [{'id': 'a', 'retained': False}, {
            'id': 'b', 'retained': True}]}}, 'fails': ['depth missing']}
        original = copy.deepcopy((result, measured))
        review = inspect(result, measured)
        loss = next(
            r for r in review['findings'] if r['code'] == 'features_lost_after_dense_stage')
        self.assertEqual(loss['evidence']['probe_ids'], ['a'])
        self.assertEqual((result, measured), original)
        self.assertFalse(review['uses_llm'])
        self.assertFalse(review['inspects_render_pixels'])

    def test_rejected_nonflat_proposal_is_visible_to_the_reviewer(self):
        with tempfile.TemporaryDirectory() as folder:
            y, x = np.mgrid[:20, :20]
            np.savez_compressed(Path(folder) / 'front.npz', mask=np.ones((20, 20), bool),
                                hypothesis_height_px=np.sin(x / 3), accepted_height_px=np.zeros((20, 20)))
            review = inspect({'fails': []}, {'relief': {
                             'views': {'front': {'accepted': False}}}}, folder)
            self.assertTrue(
                any(r['code'] == 'proposal_entirely_withheld' for r in review['findings']))
            self.assertEqual(review['status'], 'needs_review')

    def test_colour_edge_exclusion_is_reported_not_treated_as_geometry_truth(self):
        review = inspect({}, {'relief': {'views': {'front': {
                         'boundary_policy': 'achromatic', 'boundary_pixels': 100, 'boundary_pixels_used': 10}}}})
        self.assertEqual(review['findings'][0]['code'],
                         'boundary_evidence_excluded')
        self.assertFalse(review['physical_geometry_verified'])

    def test_provisional_geometry_is_not_mislabeled_as_a_failed_image_test(self):
        review = inspect({}, {'relief': {'views': {'front': {'needs_review': True,
                         'relief_selection': {'provisional_pixels': 100, 'provisional_regions': 2,
                                              'final_test_pass': True}}}}})
        self.assertEqual([f['code'] for f in review['findings']], ['provisional_relief_retained'])

    def test_clean_metrics_do_not_certify_physical_geometry(self):
        review = inspect({'pass': True, 'fails': []}, {})
        self.assertEqual(review['status'], 'no_flagged_issue')
        self.assertFalse(review['physical_geometry_verified'])

    def test_separate_part_evidence_is_also_checked(self):
        measured = {'surface_details': {'handle': {
            'pre_reduction_validation': {'probes': [{'id': 'a', 'retained': True}]}}}}
        result = {'metrics': {'part_surface_features': {
            'handle': {'probes': [{'id': 'a', 'retained': False}]}}}}
        review = inspect(result, measured)
        self.assertEqual(review['findings'][0]['part'], 'handle')


if __name__ == '__main__':
    unittest.main()
