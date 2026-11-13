"""The stage critic reports evidence and never grants itself geometry authority."""
import copy
import tempfile
import unittest
from pathlib import Path
import numpy as np
from propkit.stage_review import inspect


class ReviewContracts(unittest.TestCase):
    def test_half_strength_field_and_bound_clipping_are_exposed(self):
        with tempfile.TemporaryDirectory() as folder:
            height = np.full((20, 20), -2.)
            np.savez_compressed(Path(folder) / 'front.npz', mask=np.ones((20,20),bool),
                                hypothesis_height_px=height, accepted_height_px=height,
                                coarse_height_px=np.zeros((20,20)), final_shared_height_px=height*.5,
                                spline_controls_px=np.full((6,6),-2.))
            report = inspect({}, {'relief': {'views': {'front': {'depth_bound_px': 2.}}}}, folder)
            codes = {f['code'] for f in report['findings']}
            self.assertIn('depth_bound_saturated', codes)
            self.assertIn('relief_attenuated_in_shared_field', codes)
            gauge = next(g for g in report['diagnostic_gauges'] if g['gauge']=='proposal_to_shared_field')
            self.assertAlmostEqual(gauge['least_squares_gain'], .5)

    def test_correction_gate_failure_remains_visible(self):
        report = {'accepted': False, 'decision': 'reject_and_rollback',
                  'reasons': ['detail_retention exceeded budget']}
        review = inspect({'correction_review_failure': report}, {})
        self.assertEqual(review['correction_reviews'], [report])
        self.assertTrue(any(f['code'] == 'unsafe_correction_blocked' for f in review['findings']))

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

    def test_opposing_mask_cut_remains_reviewable(self):
        candidate = {'id': 'back:opening:1', 'kind': 'opposed_mask_opening',
                     'cross_view_witness': 'front', 'area_source_px': 408,
                     'status': 'construction_candidate_in_use_physical_hole_unverified'}
        review = inspect({'pass': True, 'fails': []}, {'source_drawing': {
            'sheet': 'technical-traces.png', 'opening_candidates': [candidate]}})
        self.assertEqual(review['status'], 'needs_review')
        finding = review['findings'][0]
        self.assertEqual(finding['code'], 'opening_mask_physical_meaning_unverified')
        self.assertEqual(finding['evidence']['candidates'], [candidate])
        self.assertFalse(review['physical_geometry_verified'])

    def test_preflight_view_conflict_cannot_pass_stage_review(self):
        review = inspect({'pass': True, 'fails': []}, {'source_drawing': {
            'sheet': 'technical-traces.png', 'view_conflicts_in_use': ['top']}})
        self.assertEqual(review['status'], 'needs_review')
        self.assertEqual(review['findings'][0]['code'],
                         'preflight_view_conflict_used_for_geometry')

    def test_reconciled_trace_without_source_mapping_requires_review(self):
        review = inspect({'pass': True, 'fails': []}, {'source_drawing': {
            'sheet': 'technical-traces.png',
            'reconciled_views_without_source_pixel_map': ['right']}})
        self.assertEqual(review['status'], 'needs_review')
        self.assertEqual(review['findings'][0]['code'],
                         'reconciled_view_lacks_source_pixel_map')

    def test_separate_part_evidence_is_also_checked(self):
        measured = {'surface_details': {'handle': {
            'pre_reduction_validation': {'probes': [{'id': 'a', 'retained': True}]}}}}
        result = {'metrics': {'part_surface_features': {
            'handle': {'probes': [{'id': 'a', 'retained': False}]}}}}
        review = inspect(result, measured)
        self.assertEqual(review['findings'][0]['part'], 'handle')


if __name__ == '__main__':
    unittest.main()
