"""Evidence, pose, raster ownership and appearance regressions on synthetic data."""
import unittest
import numpy as np
from propkit import profile_inference as profiles
from propkit.ownership import match_ownership
from propkit.pixel_bake import linear_rgb, srgb, uv, overlap_offsets, camera_uv
from propkit.raster import depth_buffer, triangle_samples


class ProfileContracts(unittest.TestCase):
    def test_painted_stripe_is_reported_as_a_competing_explanation(self):
        u = np.linspace(-1, 1, 161)
        stripe = .5 * np.exp(-.2 * np.exp(-(u / .09)**4))
        evidence = {'rgb': np.broadcast_to(
            stripe[None, :, None], (100, 161, 3)), 'u': u}
        groove = {'v': [.2, .8], 'path_u': np.zeros(
            60), 'u': 0, 'width_u': .15}
        fit = profiles.fit_channel(evidence, groove)
        self.assertTrue(fit['ambiguous_with_paint'])
        self.assertLess(fit['paint_mse'], 1e-5)

    def test_seam_correction_is_global_bounded_and_rejects_paint_conflict(self):
        colours = np.full((40, 2, 3), .3)
        colours[:, 1] += .02
        offsets = overlap_offsets(colours, np.ones((40, 2), bool))
        np.testing.assert_allclose(
            colours[:, 0] - offsets[0], colours[:, 1] - offsets[1], atol=1e-10)
        colours[:, 1] = [.8, .1, .1]
        np.testing.assert_array_equal(overlap_offsets(
            colours, np.ones((40, 2), bool)), np.zeros((2, 3)))

    def test_camera_roll_reprojects_corrected_shape_to_original_image(self):
        record = {'dimensions': (1, 1, 2), 'camera_fit': {
            'pivot_v': .5, 'roll_degrees': {'front': 10}}}
        mapping = camera_uv('front', np.array([[0, 0, 2]]), record)
        self.assertAlmostEqual(mapping[0, 0], .5 - np.sin(np.radians(10)))
        self.assertAlmostEqual(mapping[0, 1], .5 + .5 * np.cos(np.radians(10)))

    def test_roll_does_not_remove_shared_curvature(self):
        count = 400
        band = (.2, .8)
        t = np.linspace(-1, 1, 80)
        bend = .012 * (t * t - np.mean(t * t))
        data = {}
        for name, sign, roll in [('front', 1, .025), ('back', -1, -.01), ('right', 0, .015), ('left', 0, -.02)]:
            center = np.interp(np.arange(count), np.linspace(
                80, 319, 80), 200 + count * (sign * bend + roll * t))
            data[name] = {'center': center}
        fit = profiles.fit_axis(data, band)
        self.assertAlmostEqual(fit['bend_coefficients'][0][0], .012, places=4)
        self.assertLess(fit['residual_rms'], 1e-4)
        self.assertAlmostEqual(fit['roll_degrees']['front'], np.degrees(
            np.arctan(.025 / .3)), places=2)
        self.assertIn('ambiguous', fit['gauge'])

    def test_matching_observations_make_one_physical_channel(self):
        def observation(u):
            return {'u': u, 'width_u': .1, 'fit': {'accepted': True, 'depth_fraction': .01, 'ambiguous_with_paint': False}}
        report = {'views': {'front': {'grooves': [observation(2**-.5)]},
                            'right': {'grooves': [observation(-2**-.5)]}}}
        features = profiles.feature_identities(report)
        self.assertEqual(len(features), 1)
        self.assertEqual(features[0]['cross_view_support'], 2)
        self.assertFalse(features[0]['uncertain'])
        report = {'views': {'back': {'grooves': [observation(2**-.5)]},
                            'left': {'grooves': [observation(-2**-.5)]}}}
        features = profiles.feature_identities(report)
        self.assertEqual(len(features), 1)
        self.assertEqual(features[0]['cross_view_support'], 2)

    def test_uniform_appearance_does_not_invent_grooves(self):
        mask = np.ones((200, 50), bool)
        image = np.full((200, 50, 3), 128, np.uint8)
        evidence = profiles.elevation(mask, image)
        found, _ = profiles.trace_valleys(evidence, (.2, .8))
        self.assertEqual(found, [])

    def test_flat_channel_candidate_is_rejected(self):
        evidence = {'rgb': np.full((100, 161, 3), .5),
                    'u': np.linspace(-1, 1, 161)}
        groove = {'v': [.2, .8], 'path_u': np.zeros(
            60), 'u': 0, 'width_u': .15}
        self.assertFalse(profiles.fit_channel(evidence, groove)['accepted'])

    def test_visibility_chooses_front_owner_independent_of_face_order(self):
        points = np.array([[0, 0], [4, 0], [0, 4], [0, 0], [4, 0], [0, 4]])
        faces = np.array([[0, 1, 2], [3, 4, 5]])
        z = np.array([2, 2, 2, 1, 1, 1])
        depth, owners = depth_buffer(points, faces, z, [7, 9], 5, 5)
        self.assertEqual(owners[1, 1], 9)
        self.assertEqual(depth[1, 1], 1)
        self.assertEqual(owners[4, 4], -1)
        _, reverse = depth_buffer(points, faces[::-1], z, [9, 7], 5, 5)
        np.testing.assert_array_equal(owners, reverse)

    def test_degenerate_triangle_is_not_rasterized(self):
        self.assertIsNone(triangle_samples([[0, 0], [1, 1], [2, 2]], 4, 4))

    def test_opposing_coincident_caps_keep_distinct_identity(self):
        document = {'triangle_centroids_m': [[0, 0, 0], [0, 0, 0]],
                    'triangle_normals': [[0, 0, 1], [0, 0, -1]], 'triangle_owners': [0, 1]}
        result = match_ownership(document, [[0, 0, 0], [0, 0, 0]], [
                                 [0, 0, -1], [0, 0, 1]])
        np.testing.assert_array_equal(result, [1, 0])
        document['triangle_normals'][1] = [0, 0, 1]
        with self.assertRaisesRegex(ValueError, 'ambiguous'):
            match_ownership(document, [[0, 0, 0]], [[0, 0, 1]])

    def test_changed_export_cannot_receive_stale_identity(self):
        document = {'triangle_centroids_m': [[0, 0, 0]], 'triangle_normals': [
            [0, 0, 1]], 'triangle_owners': [0]}
        with self.assertRaisesRegex(ValueError, 'changed'):
            match_ownership(document, [[.01, 0, 0]], [[0, 0, 1]])

    def test_colour_round_trip_and_view_orientation(self):
        values = np.linspace(0, 1, 100)
        np.testing.assert_allclose(
            srgb(linear_rgb(values)), values, atol=1e-10)
        point = np.array([[-1, -2, 3]])
        np.testing.assert_allclose(uv('front', point, (2, 4, 3)), [[0, 1]])
        np.testing.assert_allclose(uv('back', point, (2, 4, 3)), [[1, 1]])
        np.testing.assert_allclose(uv('right', point, (2, 4, 3)), [[0, 1]])


if __name__ == '__main__':
    unittest.main()
