"""Curved-surface contract for a supported local view-fusion retry."""

import unittest

import numpy as np
from scipy import ndimage

from propkit import local_retry


class LocalRetryTests(unittest.TestCase):
    def setUp(self):
        size = 72
        x, y, z = np.mgrid[:size, :size, :size].astype(float)
        x = (x + .5) / size - .5
        y = (y + .5) / size - .5
        z = (z + .5) / size
        self.base = (np.sqrt((x / .35)**2 + (y / .3)**2 +
                             ((z - .5) / .45)**2) - 1) * .3
        u, v = np.meshgrid((np.arange(96) + .5) / 96,
                           (np.arange(96) + .5) / 96)
        height = (-.025 * np.exp(-((u - .5) / .03)**2 / 2)
                  * np.exp(-((v - .5) / .3)**2 / 2))
        self.probe = {'id': 'curved_recess', 'view': 'front', 'axis': 1,
                      'outward': -1,
                      'anchors_m': [[0, -.3, .5], [-.055, -.3, .5],
                                    [.055, -.3, .5]],
                      'target_offsets_m': [-.025, 0, 0]}
        self.plan = {'dimensions': (1., 1., 1.),
                     'maps': {'front': height},
                     'diagnostics': {'front': {'feature_labels': np.ones((96, 96), int)}},
                     'report': {'features': [], 'probes': [self.probe],
                                'views': {'front': {'relief_selection': {'regions': [{
                                    'region_id': 1, 'initially_supported': True,
                                    'applied': True, 'final_test_gain': .1}]}}}}}
        self.target = {'view': 'front', 'center_uv': [.5, .5],
                       'status': 'supported_unmet'}

    def test_supported_recess_on_curved_body_survives_field_gates(self):
        candidate, review = local_retry.attempt(
            self.base, self.base, self.plan, [self.target])
        self.assertTrue(review['applied'], review)
        self.assertEqual(review['baseline_field_failures'], 1)
        self.assertEqual(review['candidate_field_failures'], 0)
        self.assertEqual(review['introduced_failures'], [])
        self.assertEqual(ndimage.label(candidate < 0)[1], 1)
        self.assertLessEqual(review['outline_change_fraction'],
                             review['outline_change_limit'])
        self.assertLess(local_retry._contrast(candidate, self.probe, (1., 1., 1.)), -.0125)

    def test_unsupported_source_cannot_generate_a_repair(self):
        self.plan['report']['views']['front']['relief_selection']['regions'][0][
            'initially_supported'] = False
        candidate, review = local_retry.attempt(
            self.base, self.base, self.plan, [self.target])
        self.assertFalse(review['applied'])
        np.testing.assert_array_equal(candidate, self.base)


if __name__ == '__main__':
    unittest.main()
