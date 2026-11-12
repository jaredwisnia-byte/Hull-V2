"""Whole-view failures must not automatically discard supported local geometry."""
import unittest
import numpy as np
from propkit.joint_shading import shade
from propkit.relief_selection import select, extend_supported


class SelectionContracts(unittest.TestCase):
    def fixture(self, both=False):
        y, x = np.mgrid[:96, :96]
        labels = np.zeros(x.shape, np.int32)
        labels[12:84, 8:40] = 1
        labels[12:84, 56:88] = 2
        height = np.zeros(x.shape)
        for offset in (8, 56):
            u = np.clip((x - offset) / 32, 0, 1)
            v = np.clip((y - 12) / 72, 0, 1)
            height -= 2 * np.sin(np.pi * u)**2 * np.sin(np.pi * v)**2
        truth = height if both else np.where(labels == 1, height, 0)
        base = np.zeros(x.shape)
        material = np.full(x.shape, np.log(.5))
        light = np.array([-.5, -.2, .8, .2])
        observed = material + np.log(shade(base + truth, light))
        fold = (y + 3 * x) % 9
        mask = np.ones(x.shape, bool)
        return (base, height, material, light, material, light, observed, labels, mask, fold == 0, fold == 2, fold == 1)

    def test_supported_patch_survives_failure_elsewhere(self):
        args = self.fixture()
        applied, material, report, maps = select(*args)
        self.assertEqual(report['mode'], 'regional', report)
        self.assertEqual(report['applied_regions'], 1)
        self.assertTrue(np.any(applied[args[7] == 1] < 0))
        self.assertLess(
            np.max(abs(applied[args[7] == 2])), .2 * np.max(abs(args[1])))
        self.assertTrue(report['final_test_pass'])

    def test_continuation_keeps_supported_boundary_depth(self):
        height = np.full((40, 40), -2.)
        selected = np.zeros(height.shape, bool)
        selected[12:28, 12:28] = True
        mask = np.ones(height.shape, bool)
        mask[[0, -1], :] = False
        mask[:, [0, -1]] = False
        extended, converged = extend_supported(height, selected, mask)
        self.assertTrue(converged)
        np.testing.assert_array_equal(extended[selected], -2.)
        self.assertLess(extended[11, 20], -1.)
        np.testing.assert_array_equal(extended[~mask], 0.)
        self.assertGreaterEqual(extended.min(), -2.00001)
        self.assertLessEqual(extended.max(), .00001)

    def test_ambiguous_regions_keep_their_proposal_not_a_zero_prior(self):
        args = list(self.fixture())
        args[6] = args[4] + np.log(shade(args[0], args[5])) + .1
        applied, material, report, maps = select(*args)
        self.assertEqual(report['mode'], 'provisional')
        self.assertTrue(report['needs_review'])
        np.testing.assert_allclose(applied, args[1], atol=1e-10)
        self.assertGreater(report['provisional_pixels'], 0)

    def test_weak_evidence_is_not_a_material_only_verdict(self):
        args = list(self.fixture(both=True))
        args[1] = args[1] * .001
        args[6] = args[2] + np.log(shade(args[0] + args[1], args[3]))
        applied, material, report, maps = select(*args)
        self.assertEqual(report['mode'], 'provisional')
        np.testing.assert_allclose(applied, args[1], atol=1e-10)

    def test_linear_solver_failure_is_not_accepted(self):
        from unittest.mock import patch
        args = self.fixture()
        with patch('propkit.relief_selection.cg', return_value=(np.zeros(args[1].size), 1)):
            with self.assertRaisesRegex(RuntimeError, 'did not converge'):
                select(*args)

    def test_final_test_pixels_cannot_choose_geometry(self):
        args = list(self.fixture())
        first, material, report, maps = select(*args)
        changed = args[6].copy()
        changed[args[-1]] += 2
        args[6] = changed
        second, other, report, maps = select(*args)
        np.testing.assert_array_equal(first, second)
        np.testing.assert_array_equal(material, other)
        self.assertFalse(report['final_test_pass'])

    def test_whole_view_support_preserves_the_proposal(self):
        args = self.fixture(both=True)
        applied, material, report, maps = select(*args)
        self.assertEqual(report['mode'], 'whole_view')
        np.testing.assert_array_equal(applied, args[1])

    def test_no_explanatory_signal_does_not_force_relief(self):
        args = list(self.fixture())
        args[6] = args[4] + np.log(shade(args[0], args[5]))
        applied, material, report, maps = select(*args)
        self.assertEqual(report['mode'], 'none')
        np.testing.assert_array_equal(applied, 0)


if __name__ == '__main__':
    unittest.main()
