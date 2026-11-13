"""Numerical CAD-chart contracts, independent of object identity."""
import unittest
import numpy as np
from propkit import spline_surface as surfaces


class SurfaceTests(unittest.TestCase):
    def test_basis_transpose_is_exact(self):
        rng = np.random.default_rng(4)
        basis = surfaces.Basis((35, 47), (7, 6))
        coefficients = rng.normal(size=basis.controls)
        pixels = rng.normal(size=basis.shape)
        self.assertAlmostEqual(float(np.sum(basis.evaluate(coefficients) * pixels)),
                               float(np.sum(coefficients * basis.adjoint(pixels))), places=9)

    def test_trimmed_curved_surface_has_bounded_metric_error(self):
        y, x = np.mgrid[:53, :67]
        u, v = (x + .5) / 67, (y + .5) / 53
        height = .02 * u * u + .03 * u * v + .01 * v * v - .04
        mask = ((u - .5)**2 + (v - .5)**2 < .23) & ((u - .5)
                                                    ** 2 + (v - .5)**2 > .025)
        fit = surfaces.fit_height(height, mask, 1e-5)
        self.assertTrue(fit['report']['accepted'], fit['report'])
        document = surfaces.document(
            fit, [0, 0, 0], [.2, 0, 0], [0, .3, 0], [0, 0, 1])
        restored = surfaces.evaluate_document(
            document, (np.arange(67) + .5) / 67, (np.arange(53) + .5) / 53)
        self.assertLess(
            abs(restored[:, :, 2][mask] - height[mask]).max(), 3e-5)
        self.assertGreaterEqual(len(document['trim_loops_uv']), 2)
        np.testing.assert_allclose(
            restored[:, :, 0], np.broadcast_to(.2 * u, (53, 67)), atol=1e-10)

    def test_rational_evaluation_supports_nonunit_weights(self):
        weight = np.sqrt(.5)
        curve = np.array([[1, 0, 0], [1, 1, 0], [0, 1, 0]])
        points = np.stack([curve, curve + [0, 0, 1]])
        document = {'degree_u': 2, 'degree_v': 1, 'knots_u': [0, 0, 0, 1, 1, 1],
                    'knots_v': [0, 0, 1, 1], 'control_points_vu': points.tolist(),
                    'weights_vu': [[1, weight, 1], [1, weight, 1]]}
        result = surfaces.evaluate_document(
            document, np.linspace(0, 1, 31), [0, .5, 1])
        np.testing.assert_allclose(np.linalg.norm(
            result[:, :, :2], axis=2), 1, atol=1e-10)


if __name__ == '__main__':
    unittest.main()
