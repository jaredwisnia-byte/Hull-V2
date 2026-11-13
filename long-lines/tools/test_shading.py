"""Continuous pixel reconstruction contracts; no object/primitive annotations."""
import unittest
import numpy as np
from PIL import Image
from propkit import shading


def painted(height, light, albedo=None):
    value = shading.illumination(height, light)
    rgb = value[..., None] * \
        (np.full((*height.shape, 3), .45) if albedo is None else albedo)
    srgb = np.where(rgb <= .0031308, rgb * 12.92, 1.055 *
                    np.maximum(rgb, 0)**(1 / 2.4) - .055)
    return Image.fromarray(np.uint8(np.clip(srgb, 0, 1) * 255))


class ShadingContracts(unittest.TestCase):
    def test_gradient_adjoint_is_exact(self):
        rng = np.random.default_rng(7)
        height, p, q = rng.normal(size=(3, 19, 23))
        gx, gy = shading.gradients(height)
        self.assertAlmostEqual(float(np.sum(gx * p + gy * q)),
                               float(np.sum(height * shading.adjoint(p, q))), places=10)

    def test_continuous_curved_relief_from_shading(self):
        y, x = np.mgrid[:96, :96]
        mask = (x > 5) & (x < 90) & (y > 5) & (y < 90)
        height = -3 * np.exp(-((x - 48 - 9 * np.sin(y / 20)) / 8)**2) * np.sin(
            np.pi * np.clip((y - 6) / 84, 0, 1))**2
        light = np.array([-.6, -.4, .8])
        light /= np.linalg.norm(light)
        result, report = shading.reconstruct(painted(height, light), mask,
                                             np.zeros_like(height), 8, light=light, iterations=150)
        self.assertTrue(report['accepted'], report)
        self.assertGreater(np.corrcoef(height[mask], result[mask])[0, 1], .9)
        self.assertLess(np.sqrt(np.mean((height[mask] - result[mask])**2)), .5)
        self.assertEqual(report['integrability'],
                         'exact discrete height gradient')
        self.assertTrue(np.all(result[~mask] == 0))

    def test_chromatic_material_step_is_not_manufactured(self):
        height = np.zeros((64, 64))
        mask = np.ones_like(height, bool)
        material = np.full((64, 64, 3), [.2, .4, .25])
        material[:, 32:] = [.5, .15, .3]
        light = np.array([-.6, -.4, .8])
        light /= np.linalg.norm(light)
        result, report = shading.reconstruct(painted(height, light, material), mask,
                                             height, 8, light=light)
        self.assertFalse(report['accepted'], report)
        self.assertEqual(float(abs(result).max()), 0.)

    def test_flat_image_does_not_create_topography(self):
        image = Image.new('RGB', (48, 48), (128, 128, 128))
        result, report = shading.reconstruct(image, np.ones((48, 48), bool),
                                             np.zeros((48, 48)), 4)
        self.assertFalse(report['accepted'])
        self.assertEqual(float(abs(result).max()), 0.)
        self.assertIn('albedo', report['uncertainty'])


if __name__ == '__main__':
    unittest.main()
