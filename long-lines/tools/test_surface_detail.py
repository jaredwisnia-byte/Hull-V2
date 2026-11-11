"""Cross-family contracts: planes, curved skins and continuous height maps."""
import unittest
import numpy as np
from PIL import Image
from scipy import ndimage
from propkit.surface_detail import apply_field
from propkit.implicit import bounded_field, pad_field


class SurfaceContracts(unittest.TestCase):
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
