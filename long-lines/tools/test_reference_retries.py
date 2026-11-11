"""Adaptive surrounding-surface fits and bounded strategy attempts."""
import unittest
import numpy as np
from propkit.reference_fitting import fit


class RetryContracts(unittest.TestCase):
    def fixture(self):
        y, x = np.mgrid[:70, :80]
        region = (x > 22) & (x < 55) & (y > 18) & (y < 50)
        return x, y, region, np.ones(region.shape, bool)

    def test_plane_is_preferred_for_a_plane(self):
        x, y, region, valid = self.fixture()
        base = .2 * x - .1 * y
        result, report = fit(base, region, valid)
        self.assertTrue(report['accepted'])
        self.assertEqual(report['model'], 'plane')
        self.assertLessEqual(len(report['attempts']), 9)
        np.testing.assert_allclose(result, base, atol=1e-8)

    def test_nonlinear_reference_can_retry_beyond_a_quadratic(self):
        x, y, region, valid = self.fixture()
        base = 3 * np.sin(x / 13) + 2 * np.cos(y / 15)
        result, report = fit(base, region, valid, tolerance=.3)
        self.assertTrue(
            any(a['model'] == 'thin_plate' for a in report['attempts']))
        self.assertTrue(report['accepted'], report)
        self.assertLess(report['ring_error_p95_px'], .3)

    def test_retrieved_strategy_does_not_bypass_validation(self):
        x, y, region, valid = self.fixture()
        base = .2 * x - .1 * y
        a, first = fit(base, region, valid)
        b, second = fit(base, region, valid, hints=[
                        {'strategy': 'thin_plate:3'}])
        np.testing.assert_allclose(a, b, atol=1e-8)
        self.assertEqual(first['strategy'], second['strategy'])
        self.assertEqual(second['attempts'][0]['strategy'], 'thin_plate:3')

    def test_insufficient_support_is_retained_as_failure_history(self):
        result, report = fit(np.zeros((20, 20)), np.ones(
            (20, 20), bool), np.ones((20, 20), bool))
        self.assertIsNone(result)
        self.assertFalse(report['accepted'])
        self.assertEqual(len(report['attempts']), 9)


if __name__ == '__main__':
    unittest.main()
