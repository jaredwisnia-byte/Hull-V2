"""Known-geometry section contracts; no Blender or model download required."""
import unittest
import numpy as np
from propkit.sectioning import CuttingPlane, intersect_mesh, closed_contours, section_image


class SectionTests(unittest.TestCase):
    def square(self, radius):
        points = np.array([[-radius, -radius], [radius, -radius],
                           [radius, radius], [-radius, radius]])
        return np.stack([points, np.roll(points, -1, axis=0)], axis=1)

    def test_nested_void_remains_unhatched(self):
        segments = np.concatenate([self.square(1), self.square(.5)])
        image, report = section_image(segments, size=201, pixels_per_metre=80)
        self.assertEqual(report['closed_loops'], 2)
        self.assertEqual(report['open_components'], 0)
        self.assertEqual(image.getpixel((100, 100)), (255, 255, 255))
        self.assertNotEqual(image.getpixel((155, 100)), (255, 255, 255))
        self.assertAlmostEqual(
            report['cut_area_m2_raster_estimate'], 3, delta=.08)

    def test_open_section_is_never_filled(self):
        segments = self.square(1)[:3]
        image, report = section_image(segments)
        self.assertEqual(report['closed_loops'], 0)
        self.assertEqual(report['open_components'], 1)
        self.assertEqual(image.getpixel((180, 180)), (255, 255, 255))

    def test_branch_is_reported(self):
        segments = np.concatenate(
            [self.square(1), np.array([[[-1, -1], [0, 0]]])])
        loops, rejected = closed_contours(segments)
        self.assertEqual(len(loops), 0)
        self.assertEqual(rejected, 1)

    def test_oblique_cut_lies_in_requested_plane(self):
        vertices = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 1]])
        plane = CuttingPlane((.25, 0, 0), (1, 1, 0))
        result = intersect_mesh(vertices, np.array([[0, 1, 2]]), plane)
        self.assertEqual(result.shape, (1, 2, 2))
        origin, normal, horizontal, vertical = plane.frame()
        restored = origin + result[..., 0, None] * \
            horizontal + result[..., 1, None]*vertical
        np.testing.assert_allclose((restored-origin)@normal, 0, atol=1e-12)

    def test_invalid_plane_rejected(self):
        for normal in ((0, 0, 0), (np.nan, 0, 1)):
            with self.assertRaises(ValueError):
                CuttingPlane((0, 0, 0), normal).frame()


if __name__ == '__main__':
    unittest.main()
