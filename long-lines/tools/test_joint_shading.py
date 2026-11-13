"""Coupled fitting and depth-identifiability tests with known synthetic truth."""
import unittest
import os
from unittest.mock import patch
import numpy as np
from PIL import Image
from propkit import shading, joint_shading, depth_measurement


def fixture():
    y, x = np.mgrid[:64, :64]
    mask = (x > 4) & (x < 59) & (y > 4) & (y < 59)
    base = -.006 * ((x - 32)**2 + (y - 32)**2)
    height = -2 * np.exp(-((x - 32 - 5 * np.sin(y / 13)) / 5)**2) * \
        np.sin(np.pi * np.clip((y - 5) / 54, 0, 1))**2
    light = np.array([-.6, -.4, .8])
    light /= np.linalg.norm(light)
    linear = .45 * shading.illumination(base + height, light)
    srgb = np.where(linear <= .0031308, linear * 12.92,
                    1.055 * np.maximum(linear, 0)**(1 / 2.4) - .055)
    image = Image.fromarray(
        np.uint8(np.repeat(srgb[..., None], 3, axis=2) * 255))
    return image, mask, base, height, light


class JointTests(unittest.TestCase):
    def test_prebuild_trace_is_consumed_without_retracing(self):
        image, mask, base, _, _ = fixture()
        traced = joint_shading.prepare_image_trace(image, mask)['traced']
        from propkit import feature_regions
        with patch.object(feature_regions, 'trace', side_effect=AssertionError(
                'solver retraced instead of consuming drawing')):
            height, report = joint_shading.reconstruct(
                image, mask, base, 6, iterations=8,
                traced_override=traced)
        self.assertEqual(height.shape, mask.shape)
        self.assertEqual(report['boundary_pixels'], int(traced['boundaries'].sum()))

    def test_black_pixels_keep_material_fit_finite(self):
        rgb = np.full((12, 12, 3), .2)
        rgb[3:7, 4:8] = 0
        observed = np.log(np.maximum(rgb.mean(2), 1e-5))
        prior, chroma = joint_shading.material_prior(
            rgb, observed, np.zeros((12, 12)), np.ones((12, 12)))
        self.assertTrue(np.isfinite(chroma).all())
        self.assertTrue(np.isfinite(prior).all())

    def setUp(self):
        backend = patch.dict(os.environ, HULL_TRACE_BACKEND="classical")
        backend.start()
        self.addCleanup(backend.stop)

    def test_unknown_light_and_material_fit_converges_on_curved_base(self):
        image, mask, base, truth, light = fixture()
        height, report = joint_shading.reconstruct(
            image, mask, base, 6, iterations=100)
        self.assertTrue(report['accepted'], report)
        self.assertTrue(report['converged'], report)
        self.assertGreater(np.corrcoef(truth[mask], height[mask])[0, 1], .9)
        self.assertLess(np.sqrt(np.mean((truth[mask] - height[mask])**2)), .3)
        self.assertEqual(report['light_source'],
                         'jointly_fitted_with_explicit_gauge')
        self.assertFalse(report['depth_information']['data_only_identifiable'])

    def test_calibrated_depth_has_explicit_physical_scale(self):
        image, mask, base, truth, light = fixture()
        height, report = joint_shading.reconstruct(
            image, mask, base, 6, light=light, albedo=.45, iterations=100)
        self.assertTrue(report['depth_information']
                        ['informative_under_model'], report)
        points = [[35, 32], [23, 32], [47, 32]]
        estimate = depth_measurement.estimate(
            height, points, .001, report, scale_status='calibrated')
        expected = depth_measurement.estimate(
            truth, points, .001, report, scale_status='calibrated')
        self.assertLess(abs(estimate['depth_m'] - expected['depth_m']), .0005)
        self.assertEqual(estimate['status'], 'calibrated_model_estimate')

    def test_flat_base_cannot_calibrate_unknown_light_direction(self):
        observed = np.full((24, 24), np.log(.4))
        light, report = joint_shading.fit_light(observed, np.zeros_like(observed), np.zeros_like(observed),
                                                np.ones_like(observed), np.array([-.4, -.5, .8, .25]))
        self.assertFalse(report['direction_identifiable'])
        self.assertEqual(report['rank'], 1)

    def test_depth_estimate_does_not_hide_unknown_calibration(self):
        height = np.zeros((20, 20))
        height[8:12, 8:12] = -3
        result = depth_measurement.estimate(
            height, [[10, 10], [3, 10], [17, 10]], .002, {})
        self.assertFalse(result['absolute_depth_validated'])
        self.assertEqual(result['physical_scale_status'], 'estimated')

    def test_withheld_test_intensities_cannot_change_fitted_geometry(self):
        from scipy import ndimage
        image, mask, base, truth, light = fixture()
        image = image.resize((160, 160), Image.Resampling.LANCZOS)
        mask = ndimage.zoom(mask, 2.5, order=0)
        base = ndimage.zoom(base, 2.5, order=1) * 2.5
        pixels = np.asarray(image).copy()
        y, x = np.indices(mask.shape)
        from propkit.pixel_folds import balanced
        testing = mask & (balanced(mask.shape) == 1)
        changed = pixels.copy()
        changed[testing] = np.uint8(pixels[testing] * .65)
        before, after = {}, {}
        joint_shading.reconstruct(
            image, mask, base, 15, iterations=70, diagnostics=before)
        joint_shading.reconstruct(Image.fromarray(
            changed), mask, base, 15, iterations=70, diagnostics=after)
        np.testing.assert_allclose(
            before['hypothesis_height_px'], after['hypothesis_height_px'], atol=1e-10)


if __name__ == '__main__':
    unittest.main()
