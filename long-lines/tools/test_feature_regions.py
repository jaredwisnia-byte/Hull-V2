"""Internal boundary evidence, appearance ambiguity and exact-frame exports."""
import unittest
import os
from unittest.mock import patch
import tempfile
from pathlib import Path
import numpy as np
from PIL import Image
from scipy import ndimage
from propkit import feature_regions


class RegionTests(unittest.TestCase):
    def setUp(self):
        backend = patch.dict(os.environ, HULL_TRACE_BACKEND="classical")
        backend.start()
        self.addCleanup(backend.stop)

    def fixture(self):
        y, x = np.mgrid[:120, :140]
        shape = ((x > 25) & (x < 90) & (y > 25) & (y < 90)) | (
            (x > 70) & (x < 115) & (y > 60) & (y < 100))
        values = .5 - .25 * ndimage.gaussian_filter(shape.astype(float), 1)
        return np.repeat(values[..., None], 3, axis=2), np.ones(shape.shape, bool), shape

    def test_arbitrary_internal_shape_has_traced_boundaries_and_regions(self):
        rgb, mask, shape = self.fixture()
        result = feature_regions.trace(rgb, mask)
        rim = ndimage.binary_dilation(shape) ^ ndimage.binary_erosion(shape)
        recall = (rim & ndimage.binary_dilation(
            result['boundaries'], iterations=3)).sum() / rim.sum()
        self.assertGreater(recall, .8)
        self.assertGreater(len(result['regions']), 0)
        self.assertGreater(len(result['edge_curves_xy']), 0)
        self.assertTrue(
            all(r['depth_sign'] == 'unresolved' for r in result['regions']))
        self.assertFalse(result['physical_parts_created'])
        for region in result['regions']:
            y, x = np.nonzero(result['labels'] == region['id'])
            outline = np.concatenate(region['contours_xy'])
            np.testing.assert_allclose(
                outline.min(0), [x.min() - .5, y.min() - .5])

    def test_uniform_surface_has_no_invented_detail(self):
        result = feature_regions.trace(
            np.full((80, 80, 3), .4), np.ones((80, 80), bool))
        self.assertEqual(len(result['regions']), 0)
        self.assertFalse(result['boundaries'].any())

    def test_chromatic_boundaries_are_marked_as_appearance_ambiguous(self):
        rgb, mask, shape = self.fixture()
        rgb[shape] = [.15, .35, .6]
        result = feature_regions.trace(rgb, mask)
        self.assertGreater(result['appearance_boundaries'].sum(), 20)

    def test_mask_and_rotation_do_not_change_boundary_meaning(self):
        rgb, mask, shape = self.fixture()
        mask[:10] = False
        a = feature_regions.trace(rgb, mask)
        b = feature_regions.trace(np.rot90(rgb), np.rot90(mask))
        self.assertFalse(a['boundaries'][~mask].any())
        self.assertGreater((a['boundaries'] & np.rot90(
            b['boundaries'], -1)).sum() / max(1, a['boundaries'].sum()), .9)

    def test_export_records_analysis_frame_and_integer_labels(self):
        rgb, mask, shape = self.fixture()
        result = feature_regions.trace(rgb, mask)
        with tempfile.TemporaryDirectory() as folder:
            report = feature_regions.export(
                result, Image.fromarray(np.uint8(rgb * 255)), folder, 'view')
            self.assertEqual(report['image_size'], [140, 120])
            self.assertTrue(Path(report['overlay']).is_file())
            with np.load(Path(folder) / 'view-feature-regions.npz') as data:
                np.testing.assert_array_equal(data['labels'], result['labels'])


if __name__ == '__main__':
    unittest.main()
