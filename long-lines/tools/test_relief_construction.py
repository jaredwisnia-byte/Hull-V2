"""Geometric cross-view support and reverse-mould set operations."""
import unittest
import numpy as np
from scipy.spatial import cKDTree
from skimage.measure import marching_cubes
from propkit import construction_fields, relief_consistency


class ConstructionContracts(unittest.TestCase):
    def test_sampled_boolean_cannot_shift_a_fitted_surface_unchecked(self):
        base = np.array([-.5, .5])
        target = np.array([-.3, .7])
        result, report = construction_fields.reconstruct(
            base, target, maximum_root_shift_cells=.01)
        self.assertFalse(report['composition_applied'])
        np.testing.assert_array_equal(result, target)

    def test_subtraction_and_addition_preserve_target_solid_and_surface(self):
        x, y, z = np.meshgrid(*[np.linspace(-1, 1, 64)] * 3, indexing='ij')
        base = np.maximum.reduce([abs(x) - .7, abs(y) - .7, abs(z) - .7])
        cutter = np.sqrt((x - .15 * np.sin(z * 4))**2 + y * y) - .15
        raised = np.sqrt((x - .7)**2 + y * y + z * z) - .25
        target = np.minimum(np.maximum(base, -cutter),
                            raised).astype(np.float32)
        result, report = construction_fields.reconstruct(
            base.astype(np.float32), target)
        self.assertEqual(report['membership_errors'], 0)
        self.assertGreater(report['removed_cells'], 0)
        self.assertGreater(report['added_cells'], 0)
        a = marching_cubes(target, 0)[0]
        b = marching_cubes(result, 0)[0]
        self.assertLess(np.percentile(cKDTree(a).query(b)[0], 99), 1.5)

    def test_empty_change_does_not_invent_a_volume(self):
        x, y, z = np.meshgrid(*[np.linspace(-1, 1, 24)] * 3, indexing='ij')
        base = np.sqrt(x * x + y * y + z * z) - .7
        result, report = construction_fields.reconstruct(base, base)
        np.testing.assert_allclose(result, base)
        self.assertEqual(report['removed_cells'] + report['added_cells'], 0)


class CrossViewContracts(unittest.TestCase):
    def charts(self):
        y, x = np.mgrid[:96, :96]
        horizontal = (x + .5) / 96 * 2 - 1
        vertical = 1 - (y + .5) / 96 * 2
        square = .8**2 - horizontal**2 - vertical**2
        mask = square > 0
        root = 1 - np.sqrt(np.maximum(square, 0))
        common = {'mask': mask, 'height': np.zeros(
            mask.shape), 'root': root, 'pixel_m': 2 / 96, 'accepted': True}
        return {'front': dict(common, labels=(mask & (horizontal > .1)).astype(int)),
                'right': dict(common, labels=(mask & (horizontal < -.1)).astype(int))}

    def test_same_curved_patch_has_reciprocal_support(self):
        report = relief_consistency.compare(self.charts(), (2, 2, 2))
        self.assertEqual(report['supported_regions'], 2, report)

    def test_conflicting_depth_is_not_declared_supported(self):
        charts = self.charts()
        charts['right']['root'] = charts['right']['root'] + .3
        report = relief_consistency.compare(charts, (2, 2, 2))
        self.assertEqual(report['supported_regions'], 0, report)
        self.assertTrue(report['needs_review'])

    def test_one_view_remains_unresolved(self):
        report = relief_consistency.compare(
            {'front': self.charts()['front']}, (2, 2, 2))
        self.assertEqual(report['supported_regions'], 0)
        self.assertTrue(report['needs_review'])


if __name__ == '__main__':
    unittest.main()
