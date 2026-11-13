"""Cross-family contracts: planes, curved skins and continuous height maps."""
import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image
from scipy import ndimage
from propkit.surface_detail import apply_field, visible_root
from propkit.implicit import bounded_field, pad_field


class SurfaceContracts(unittest.TestCase):
    def test_retry_reuses_first_source_estimate_and_checks_coarse_field(self):
        base = self.field(True)
        height = np.full((48, 48), -.01)
        evidence = []
        first = {'dimensions': (1, 1, 1), 'maps': {'front': np.zeros((48, 48))},
                 'shading_inputs': {}, 'report': {'features': [], 'views': {}},
                 'source_evidence_sink': evidence.append}
        with patch('propkit.surface_detail.shading_view', return_value=height) as solve:
            result = apply_field(base, first)
        self.assertEqual(solve.call_count, 1)
        self.assertEqual(len(evidence), 1)
        retry = {'dimensions': (1, 1, 1), 'maps': {'front': np.zeros((48, 48))},
                 'shading_inputs': {}, 'report': {'features': [], 'views': {}},
                 'frozen_source_evidence': evidence[0]}
        with patch('propkit.surface_detail.shading_view', side_effect=AssertionError('re-solved')):
            repeated = apply_field(base, retry)
        np.testing.assert_array_equal(repeated, result)
        self.assertTrue(retry['report']['source_evidence_reused'])
        changed = base.copy()
        changed[0, 0, 0] += .001
        with self.assertRaisesRegex(ValueError, 'coarse source field'):
            apply_field(changed, {'dimensions': (1, 1, 1), 'maps': {'front': height},
                                  'report': {'features': [], 'views': {}},
                                  'frozen_source_evidence': evidence[0]})

    def test_unobserved_original_cavity_cannot_be_filled_by_a_skin_correction(self):
        from propkit.implicit import preserve_components
        from propkit.correction_review import Rejected
        base=np.full((20,20,20),-1.,np.float32)
        base[10,10,10]=1.
        target=base.copy();target[10,10,10]=-1.
        with self.assertRaises(Rejected):
            preserve_components(base,target)

    def test_new_grid_cavity_is_repaired_but_original_cavity_and_open_groove_remain(self):
        from propkit.implicit import preserve_components
        base = np.ones((30,30,30), np.float32)
        base[2:28,2:28,2:28] = -1
        base[8,8,8] = 1
        target=base.copy()
        target[20,20,20] = 1
        target[2:12,15,15] = 1
        result, report = preserve_components(base,target)
        self.assertLess(result[20,20,20],0)
        self.assertGreater(result[8,8,8],0)
        self.assertTrue((result[2:12,15,15] > 0).all())
        self.assertEqual(report['filled_new_cavity_cells'],1)
        self.assertEqual(report['detail_scale'],1.)

    def test_detached_grid_speck_does_not_halve_remote_relief(self):
        from propkit.implicit import preserve_components
        base = np.ones((24, 24, 24), np.float32)
        base[3:21, 3:21, 3:21] = -1
        target = base.copy()
        target[3:5, 3:21, 3:21] = 1
        target[1, 12, 12] = -.2
        target[10:14, 10:14, 3:7] = 1
        result, report = preserve_components(base, target)
        self.assertEqual(report['detail_scale'], 1.)
        self.assertEqual(report['removed_fragment_cells'], 1)
        np.testing.assert_array_equal(result[10:14, 10:14, 3:7], target[10:14, 10:14, 3:7])
        self.assertGreater(result[1, 12, 12], 0)

    def test_original_tiny_physical_part_is_preserved(self):
        from propkit.implicit import preserve_components
        base = np.ones((24, 24, 24), np.float32)
        base[3:18, 3:18, 3:18] = -1
        base[22, 22, 22] = -.1
        result, report = preserve_components(base, base.copy())
        self.assertEqual(report['baseline_solid_components'], 2)
        self.assertLess(result[22, 22, 22], 0)
        self.assertEqual(report['detail_scale'], 1.)

    def test_large_structural_split_still_backs_off(self):
        from propkit.implicit import preserve_components
        base = np.full((20, 20, 20), -1., np.float32)
        target = base.copy(); target[9:11] = 3.
        from propkit.correction_review import Rejected
        with self.assertRaises(Rejected) as caught:
            preserve_components(base, target)
        self.assertEqual(caught.exception.report['decision'], 'reject_and_rollback')

    def test_metric_padding_preserves_exact_sampling_box_boundaries(self):
        from skimage.measure import marching_cubes
        dimensions = (.2, .1, .3)
        shape = (40, 20, 60)
        field = bounded_field(np.full(shape, -1.), dimensions)
        vertices, _, _, _ = marching_cubes(pad_field(field, dimensions), 0)
        physical = (vertices - 1 + .5) * np.asarray(dimensions) / shape
        np.testing.assert_allclose(physical.min(0), 0, atol=1e-8)
        np.testing.assert_allclose(physical.max(0), dimensions, atol=1e-8)

    def field(self, organic=False):
        n = 48
        x = (np.arange(n) + .5) / n - .5
        X, Y, Z = np.meshgrid(x, x, x, indexing='ij')
        return np.sqrt(X * X + Y * Y + Z * Z) - .43 if organic else np.maximum.reduce([abs(X) - .5, abs(Y) - .5, abs(Z) - .5])

    def test_same_field_operator_handles_flat_and_organic_skins_in_all_views(self):
        yy, xx = np.mgrid[:64, :64]
        height = -.04 * np.exp(-((xx - 24)**2 + (yy - 35)**2) / 60)
        feature = {'id': 'observed', 'view': None, 'kind': 'channel', 'probes': [
            {'center_px': [24, 35], 'normal_px': [1, 0], 'radius_px': 4, 'depth_px': 2.56}]}
        for organic in (False, True):
            original = self.field(organic)
            for view in ('front', 'back', 'left', 'right', 'top', 'bottom'):
                feature = dict(feature, view=view)
                plan = {'dimensions': (1, 1, 1), 'maps': {view: height}, 'report': {
                    'features': [feature]}}
                result = apply_field(original, plan)
                self.assertEqual(ndimage.label(result < 0)[1], 1)
                self.assertGreater(
                    int(((original < 0) & (result >= 0)).sum()), 0, (organic, view))
                self.assertEqual(plan['report']['field']['isovalue'], 0)
                self.assertEqual(len(plan['report']['probes']), 1)
                probe = plan['report']['probes'][0]
                point = np.asarray(probe['anchors_m'][0])
                point[probe['axis']] += probe['outward'] * \
                    probe['target_offsets_m'][0]
                indices = (point + [.5, .5, 0]) * 48 - .5
                value = ndimage.map_coordinates(
                    result, indices[:, None], order=1)[0]
                self.assertLess(abs(value), .025, (organic, view, value))

    def test_empty_detail_keeps_original_surface_exactly(self):
        original = self.field(True)
        plan = {'dimensions': (1, 1, 1), 'maps': {'front': np.zeros(
            (40, 40))}, 'report': {'features': []}}
        np.testing.assert_allclose(apply_field(
            original, plan), original, atol=2e-8)

    def test_diagnostic_captures_fusion_before_component_repair(self):
        original = self.field(True)
        plan = {'dimensions': (1, 1, 1),
                'maps': {'front': np.full((48, 48), -.02)},
                'report': {'features': []},
                'capture_fusion_contributions': True,
                'diagnostic_folder': 'unused',
                'diagnostics': {'front': {'mask': np.ones((48, 48), bool),
                                          'metres_per_pixel': 1 / 48}}}
        apply_field(original, plan)
        chart = plan['diagnostics']['front']
        self.assertEqual(chart['sampled_height_px'].shape, (48, 48))
        self.assertEqual(chart['clipped_height_px'].shape, (48, 48))
        self.assertEqual(chart['single_view_height_px'].shape, (48, 48))
        self.assertEqual(chart['fused_height_px'].shape, (48, 48))
        np.testing.assert_allclose(chart['single_view_height_px'],
                                   chart['fused_height_px'], atol=1e-5)
        self.assertEqual(chart['post_topology_height_px'].shape, (48, 48))
        np.testing.assert_allclose(chart['fused_height_px'],
                                   chart['post_topology_height_px'], atol=1e-5)

    def test_fusion_trace_records_view_weights_without_changing_field(self):
        original = self.field()
        yy, xx = np.mgrid[:48, :48]
        height = -.02 * np.exp(-((xx - 24)**2 + (yy - 24)**2) / 50)
        feature = {'id': 'observed', 'view': 'front', 'kind': 'channel',
                   'probes': [{'center_px': [24, 24], 'normal_px': [1, 0],
                               'radius_px': 4, 'sample_span_px': 4}]}
        base = {'dimensions': (1, 1, 1), 'maps': {'front': height},
                'report': {'features': [feature]}}
        control = apply_field(original, base)
        with tempfile.TemporaryDirectory() as temporary:
            plan = {'dimensions': (1, 1, 1), 'maps': {'front': height},
                    'report': {'features': [feature]},
                    'capture_fusion_contributions': True,
                    'diagnostic_folder': temporary}
            traced = apply_field(original, plan)
            np.testing.assert_array_equal(traced, control)
            trace = json.loads((Path(temporary) /
                                'fusion-contributions.json').read_text())
            self.assertIn('observed_0', trace['probes'])
            self.assertEqual(len(trace['probes']['observed_0']['anchors']), 3)
            anchor = trace['probes']['observed_0']['anchors'][0]
            self.assertIn('front', anchor['views'])
            self.assertEqual(set(anchor['visible_root_from_camera_m']),
                             {'baseline_m', 'single_view_m', 'fused_m'})
            self.assertEqual([sample['offset_voxels'] for sample in
                              anchor['field_profile']], list(range(-12, 13)))
            self.assertAlmostEqual(anchor['field_profile'][12]['fused_m'],
                                   anchor['field_profile'][12]
                                   ['single_view_m']['front'], places=6)

    def test_profile_envelope_is_applied_after_original_detail(self):
        original = self.field(True)
        height = np.full((48, 48), -.01)
        ordinary = apply_field(original, {'dimensions': (1, 1, 1),
                                         'maps': {'front': height},
                                         'report': {'features': []}})
        correction = np.zeros_like(original)
        correction[:, :, 20:28] = -.002
        plan = {'dimensions': (1, 1, 1), 'maps': {'front': height},
                'report': {'features': []},
                'post_detail_envelope': lambda base, detailed: detailed + correction}
        routed = apply_field(original, plan)
        np.testing.assert_allclose(routed[:, :, :20], ordinary[:, :, :20])
        np.testing.assert_allclose(routed[:, :, 28:], ordinary[:, :, 28:])
        self.assertIn('profile_topology', plan['report'])

    def test_oblique_curved_skin_retains_observed_depth(self):
        n = 64
        x = (np.arange(n) + .5) / n - .5
        X, Y, Z = np.meshgrid(x, x, x, indexing='ij')
        original = np.sqrt(X * X + Y * Y + Z * Z) - .43
        plan = {'dimensions': (1, 1, 1),
                'maps': {'front': np.full((n, n), -.02)},
                'report': {'features': []}}
        result = apply_field(original, plan)
        before = visible_root(original, 1, False, 1)[0]
        after = visible_root(result, 1, False, 1)[0]
        # The 0.35 m section faces the camera obliquely. The old fusion
        # floor cut a 20 mm observed recess to about 5.5 mm here.
        index = (.35 + .5) * n - .5
        displacement = ndimage.map_coordinates(
            after - before, [[index], [(n - 1) / 2]], order=1)[0]
        self.assertAlmostEqual(float(displacement), .02, delta=.003)

    def test_multiview_relief_preserves_a_thin_structural_connection(self):
        x = (np.arange(48) + .5) / 48 - .5
        X, Y, Z = np.meshgrid(x, x, x, indexing='ij')
        blocks = (abs(X) < .3) & (abs(Y) < .3) & (abs(Z) > .15) & (abs(Z) < .4)
        bridge = (abs(X) < .035) & (abs(Y) < .035) & (abs(Z) < .3)
        solid = blocks | bridge
        field = (ndimage.distance_transform_edt(~solid) -
                 ndimage.distance_transform_edt(solid)) / 48
        plan = {'dimensions': (1, 1, 1), 'maps': {view: np.full((48, 48), -.09)
                                                  for view in ('front', 'back', 'left', 'right')}, 'report': {'features': []}}
        result = apply_field(field, plan)
        self.assertEqual(ndimage.label(result < 0)[1], 1)
        self.assertTrue((result < 0)[:, :, 23:25].any())
        self.assertIn('detail_scale', plan['report']['topology'])

    def test_conflicting_section_is_not_claimed_as_a_validated_groove(self):
        yy, xx = np.mgrid[:64, :64]
        feature = {'id': 'ambiguous', 'view': 'front', 'kind': 'channel', 'sign': -1,
                   'probes': [{'center_px': [24, 35], 'normal_px': [1, 0], 'radius_px': 4}]}
        # A competing overlapping patch has reversed this proposed valley.
        plan = {'dimensions': (1, 1, 1), 'maps': {'front': .04 * np.exp(
            -((xx - 24)**2 + (yy - 35)**2) / 60)}, 'report': {'features': [feature]}}
        apply_field(self.field(), plan)
        self.assertEqual(plan['report']['conflicting_probes'], 1)
        self.assertEqual(plan['report']['probes'], [])


if __name__ == '__main__':
    unittest.main()
