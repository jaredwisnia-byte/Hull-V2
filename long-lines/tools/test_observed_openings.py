"""Opposed source openings must survive generic visual-hull intake."""
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from propkit.silhouette import observed_silhouettes, opening_occlusion
from propkit import surface_detail


class ObservedOpeningsTest(unittest.TestCase):
    def test_opposed_opening_survives_and_unpaired_mark_does_not(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            body = np.zeros((100, 100, 3), dtype=np.uint8)
            body[10:90, 10:90] = (210, 170, 120)
            opening = np.zeros((100, 100), dtype=np.uint8)
            opening[22:42, 25:75] = 255
            views = {}
            for view in ('front', 'back'):
                path = root / ('v_' + view + '.png')
                Image.fromarray(body).save(path)
                views[view] = str(path)
            Image.fromarray(opening).save(root / 'h_front.png')
            masks, report = observed_silhouettes(views)
            self.assertEqual(report['accepted'].get('front', 0), 0)
            self.assertTrue(masks['front'][0][12:32, 15:65].all())
            plain = surface_detail.analyse(views, (.2, .1, .4), {})
            unpaired = surface_detail.analyse(views, (.2, .1, .4), {},
                                              silhouettes=masks)
            self.assertEqual(unpaired['report']['excluded_opening_pixels']['front'], 0)
            np.testing.assert_array_equal(
                plain['shading_inputs']['front']['valid'],
                unpaired['shading_inputs']['front']['valid'])
            Image.fromarray(opening).save(root / 'h_back.png')
            masks, report = observed_silhouettes(views)
            self.assertGreater(report['accepted']['front'], 800)
            self.assertFalse(masks['front'][0][12:32, 15:65].any())
            expected = masks['front'][0]
            self.assertEqual(opening_occlusion(expected, expected), 0)
            self.assertGreater(opening_occlusion(expected, np.ones_like(expected)), 0.99)

            plan = surface_detail.analyse(views, (.2, .1, .4), {},
                                          silhouettes=masks)
            self.assertGreater(plan['report']['excluded_opening_pixels']['front'], 800)
            self.assertFalse(plan['shading_inputs']['front']['valid'][12:32, 15:65].any())


if __name__ == '__main__':
    unittest.main()
