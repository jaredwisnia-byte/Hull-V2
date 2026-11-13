"""Reference surfaces and local relief measured against synthetic ground truth."""
import unittest
import numpy as np
from scipy import ndimage
from propkit import regional_relief, region_grouping, joint_shading


class GroupingContracts(unittest.TestCase):
    def test_weak_path_cannot_bypass_a_strong_crease(self):
        labels = np.ones((32, 62), np.int32)
        labels[:15, 31:] = 2
        labels[:15, 30] = 0
        labels[15] = 0
        labels[16:] = 3
        strength = np.zeros(labels.shape)
        strength[:15, 30] = 1
        merged = region_grouping.merge_weak_lines(labels, np.ones(
            labels.shape, bool), strength, protect_strong=True)
        self.assertNotEqual(merged[5, 5], merged[5, 50])

    def test_weak_painted_split_merges_but_strong_crease_remains(self):
        labels = np.ones((30, 60), np.int32)
        labels[:, 20] = 0
        labels[:, 21:40] = 2
        labels[:, 40] = 0
        labels[:, 41:] = 3
        strength = np.zeros(labels.shape)
        strength[:, 40] = 1
        merged = region_grouping.merge_weak_lines(
            labels, np.ones(labels.shape, bool), strength)
        self.assertEqual(merged[10, 10], merged[10, 30])
        self.assertNotEqual(merged[10, 30], merged[10, 50])
        self.assertEqual(merged[10, 40], 0)

    def test_reference_recovers_curved_surface_without_reading_feature_interior(self):
        y, x = np.mgrid[:60, :70]
        truth = .002 * x * x + .003 * y * y + .001 * x * y - .2 * x
        region = (x > 20) & (x < 45) & (y > 15) & (y < 45)
        supplied = truth.copy()
        supplied[region] -= 7
        reference, report = regional_relief.reference_surface(
            supplied, region, np.ones(region.shape, bool))
        self.assertTrue(report['accepted'], report)
        core = ndimage.binary_erosion(region, iterations=2)
        np.testing.assert_allclose(reference[core], truth[core], atol=1e-8)

    def test_missing_surrounding_surface_is_reported(self):
        reference, report = regional_relief.reference_surface(
            np.zeros((20, 20)), np.ones((20, 20), bool), np.ones((20, 20), bool))
        self.assertIsNone(reference)
        self.assertFalse(report['accepted'])


class LocalReliefContracts(unittest.TestCase):
    def fixture(self, sign):
        y, x = np.mgrid[:64, :64]
        region = (x > 10) & (x < 54) & (y > 10) & (y < 54)
        u = np.clip((x - 10) / 44, 0, 1)
        v = np.clip((y - 10) / 44, 0, 1)
        truth = sign * 1.8 * np.sin(np.pi * u)**2 * np.sin(np.pi * v)**2
        base = -.003 * ((x - 32)**2 + (y - 32)**2)
        light = np.array([-.5, -.4, .8, .2])
        material = np.full(base.shape, np.log(.45))
        observed = material + np.log(joint_shading.shade(base + truth, light))
        fold = (y + 3 * x) % 9
        args = (base, np.zeros_like(base), material, observed, observed, light, region.astype(int),
                np.ones(region.shape, bool), fold >= 3, fold == 0, fold == 2, 4)
        return args, truth, region

    def test_both_depth_signs_compete_against_material_only(self):
        for sign, kind in ((-1, 'recess'), (1, 'raised')):
            args, truth, region = self.fixture(sign)
            result, material, report = regional_relief.refine(
                *args, envelope=False)
            self.assertEqual(report['accepted_regions'], 1, report)
            self.assertEqual(report['regions'][0]['winner'], kind, report)
            self.assertLess(
                np.sqrt(np.mean((result[region] - truth[region])**2)), .35)

    def test_flat_appearance_does_not_force_a_cut(self):
        args, truth, region = self.fixture(0)
        result, material, report = regional_relief.refine(
            *args, envelope=False)
        np.testing.assert_allclose(result, 0, atol=1e-9)
        self.assertEqual(report['accepted_regions'], 0)

    def test_budget_defers_regions_explicitly(self):
        args, truth, region = self.fixture(-1)
        result, material, report = regional_relief.refine(
            *args, maximum_regions=0)
        self.assertEqual(report['regions'][0]['status'], 'deferred')
        np.testing.assert_array_equal(result, 0)


if __name__ == '__main__':
    unittest.main()
