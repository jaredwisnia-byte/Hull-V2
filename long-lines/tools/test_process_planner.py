"""A simple profile can replace an envelope without creating a part seam."""
import unittest
import json
import tempfile
import numpy as np
from pathlib import Path
from PIL import Image, ImageDraw

from propkit import process_planner


class ProcessPlannerTests(unittest.TestCase):
    def test_one_view_reports_missing_geometry_evidence(self):
        plan, _ = process_planner.plan_methods({'front': 'one.png'})
        self.assertEqual(plan['method'], 'insufficient_views')
        self.assertIsNone(plan['base'])

    def test_round_and_box_images_choose_different_tools_without_names(self):
        def sheet(folder, round_top):
            folder.mkdir()
            views = {}
            for view in ('front', 'right', 'top'):
                image = Image.new('RGB', (120, 120), (0, 0, 0))
                draw = ImageDraw.Draw(image)
                if view == 'top' and round_top:
                    draw.ellipse((22, 22, 98, 98), fill=(180, 140, 90))
                else:
                    draw.rectangle((22, 22, 98, 98), fill=(180, 140, 90))
                path = folder / f'v_{view}.png'
                image.save(path)
                views[view] = str(path)
            return views

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            round_views = sheet(root / 'looks_like_a_box', True)
            square_views = sheet(root / 'looks_like_a_vase', False)
            round_plan, _ = process_planner.plan_methods(round_views)
            box_plan, _ = process_planner.plan_methods(square_views)
        self.assertEqual(round_plan['method'], 'lathe_vertical')
        self.assertEqual(box_plan['method'], 'continuous_field')
        self.assertFalse(round_plan['uses_object_name'])
        self.assertFalse(box_plan['uses_object_name'])
        json.dumps(round_plan, allow_nan=False)
        json.dumps(box_plan, allow_nan=False)

    def test_sectional_evidence_routes_without_a_round_end(self):
        from unittest.mock import patch
        with patch('propkit.silhouette.silhouette', return_value=(np.ones((80, 80), bool), None)), \
                patch('propkit.revolve.round_body', return_value=None), \
                patch('propkit.sections.infer', return_value=['bands']) as infer, \
                patch('propkit.sections.curved_runs', return_value=[{'v_top': .2, 'v_bottom': .7}]):
            plan, bands = process_planner.plan_methods({'front': 'unused', 'right': 'unused'})
        self.assertEqual(plan['method'], 'sectioned_field')
        self.assertEqual(bands, ['bands'])
        infer.assert_called_once()

    def test_section_planning_uses_the_bottom_view_builder_will_use(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            bottom = Path(tmp) / 'v_bottom.png'
            bottom.touch()
            views = {'front': str(Path(tmp) / 'v_front.png'),
                     'right': str(Path(tmp) / 'v_right.png')}
            with patch('propkit.silhouette.silhouette',
                       return_value=(np.ones((80, 80), bool), None)), \
                    patch('propkit.revolve.round_body', return_value=None), \
                    patch('propkit.sections.infer', return_value=[]) as infer:
                process_planner.plan_methods(views)
        self.assertEqual(infer.call_args.args[0]['bottom'], str(bottom))

    def test_local_profile_is_examined_inside_a_wide_whole_image(self):
        from unittest.mock import patch
        from propkit import construction
        mask = np.ones((80, 80), bool)
        image = Image.new('RGB', (80, 80), (140, 90, 50))
        report = {'status': 'fitted', 'band': [.2, .8],
                  'features': [], 'regions': []}
        with patch('propkit.silhouette.silhouette', return_value=(mask, image)), \
                patch('propkit.profile_inference.analyse', return_value=(report, {})), \
                patch('propkit.profile_inference.feature_identities', return_value=[]):
            model = construction.infer({'front': 'unused', 'right': 'unused'}, 1.)
        self.assertIsNotNone(model)
        self.assertEqual(model['report']['band'], [.2, .8])

    def test_complete_candidate_requires_gain_without_new_damage(self):
        def result(tris, folds, misses, outline=.95):
            return {'fails': misses,
                    'metrics': {'tris': tris, 'extreme_folds': {'per_1k': folds},
                                'geometric_components': 1,
                                'silhouette_iou': {'front': outline}}}
        def measured(identifier, u=.5):
            return {'relief': {'dimensions_m': [1, 1, 1],
                               'probes': [{'id': identifier, 'view': 'front',
                                           'anchors_m': [[u - .5, 0, .5]]}]}}
        baseline = result(20000, 8, ['missing shading depth: old'])
        old, new = measured('old'), measured('new')
        good = process_planner.compare_exports(
            baseline, result(3000, 7, ['missing shading depth: new']), old, new)
        self.assertTrue(good['accepted'])
        self.assertFalse(process_planner.compare_exports(
            baseline, result(3000, 7, ['missing shading depth: new', 'new seam']), old, new)['accepted'])
        self.assertFalse(process_planner.compare_exports(
            baseline, result(3000, 7, ['missing shading depth: new'], .93), old, new)['accepted'])
        self.assertFalse(process_planner.compare_exports(
            baseline, result(19000, 7, ['missing shading depth: new']), old, new)['accepted'])
        self.assertFalse(process_planner.compare_exports(
            baseline, result(3000, 7, ['missing shading depth: new']),
            old, measured('new', u=.7))['accepted'])
        broken = process_planner.compare_exports(
            baseline, {'fails': ['build error'], 'metrics': {}}, old, {})
        self.assertFalse(broken['accepted'])
        self.assertFalse(broken['checks']['meaningful_gain'])
        json.dumps(broken, allow_nan=False)

    def test_dense_gate_stops_detail_regression_before_baking(self):
        self.assertTrue(process_planner.dense_gate(7, 4)['accepted'])
        self.assertFalse(process_planner.dense_gate(7, 13)['accepted'])
        self.assertFalse(process_planner.dense_gate(None, 0)['accepted'])

    def test_field_preflight_rejects_a_profile_that_splits_the_solid(self):
        from unittest.mock import patch
        base = np.full((24, 24, 24), -.1)
        split = base.copy()
        split[:, :, 12] = .2
        with patch.object(process_planner, 'replace_envelope', return_value=base):
            self.assertTrue(process_planner.preflight_field(
                base, base, {}, (1, 1, 1))['accepted'])
        with patch.object(process_planner, 'replace_envelope', return_value=split):
            review = process_planner.preflight_field(base, base, {}, (1, 1, 1))
        self.assertFalse(review['accepted'])
        self.assertIn('topology_review', review)
        json.dumps(review, allow_nan=False)
        with patch.object(process_planner, 'replace_envelope', side_effect=ValueError('bad fit')):
            unavailable = process_planner.preflight_field(base, base, {}, (1, 1, 1))
        self.assertFalse(unavailable['accepted'])
        self.assertIn('bad fit', unavailable['planner_error'])

    def test_profile_envelope_keeps_other_regions_and_soft_joins(self):
        profile = {'width': np.full(100, 24.), 'center': np.full(100, 49.5),
                   'image_width': 100}
        model = {'profiles': {'front': profile, 'right': profile},
                 'report': {'height_m': 1., 'band': [.2, .8], 'features': [],
                            'camera_axis_fit': {'roll_degrees': {},
                                                'bend_coefficients': [[0, 0], [0, 0]]}}}
        x = (np.arange(80) + .5) / 80 - .5
        y = (np.arange(80) + .5) / 80 - .5
        baseline = np.broadcast_to(
            np.sqrt(x[:, None, None]**2 + y[None, :, None]**2) - .19,
            (80, 80, 160)).copy()
        result = process_planner.replace_envelope(baseline, model, (1, 1, 1))
        np.testing.assert_array_equal(result[:, :, 10], baseline[:, :, 10])
        np.testing.assert_array_equal(result[:, :, 150], baseline[:, :, 150])
        self.assertLess(result[49, 40, 80], 0)  # inside fitted radius
        self.assertGreater(result[56, 40, 80], 0)  # outside fitted radius
        # Transition never creates an abrupt change in field value.
        self.assertLess(np.max(np.abs(result[:, :, 31] - result[:, :, 32])), .02)
        detail = np.zeros_like(baseline)
        detail[39:42, 39:42, 70:90] = -.002
        corrected = baseline + detail + (result - baseline)
        np.testing.assert_array_equal(corrected[:, :, 10], baseline[:, :, 10])
        np.testing.assert_allclose(corrected - result, detail, atol=1e-12)

    def test_short_or_incoherent_profile_cannot_be_routed(self):
        from unittest.mock import patch
        for band, rms in (([.3, .45], 0), ([.2, .7], .01)):
            model = {'report': {'band': band, 'features': [],
                                'camera_axis_fit': {'residual_rms': rms}}}
            with patch('propkit.construction.infer', return_value=model):
                selected, report = process_planner.propose({}, 1)
            self.assertIsNone(selected)
            self.assertEqual(report['choice'], 'continuous_field')

    def test_optional_planner_failure_preserves_ordinary_route(self):
        from unittest.mock import patch
        with patch('propkit.construction.infer', side_effect=ValueError('bad profile')):
            model, report = process_planner.propose({}, 1.)
        self.assertIsNone(model)
        self.assertEqual(report['choice'], 'continuous_field')
        self.assertIn('bad profile', report['planner_error'])


if __name__ == '__main__':
    unittest.main()
