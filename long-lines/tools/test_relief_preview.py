"""Recorded-map previews preserve metric relief and exclude background cells."""
import unittest
import numpy as np
from propkit.relief_preview import mesh_grid


class PreviewContracts(unittest.TestCase):
    def test_depth_is_metric_and_front_normals_face_outward(self):
        mask = np.ones((8, 8), bool)
        vertices, faces = mesh_grid(np.zeros(mask.shape), np.full(
            mask.shape, -2.), mask, 'front', (1, 1, 1), .01)
        np.testing.assert_allclose(vertices[:, 1], -.48)
        a, b, c = vertices[faces[0]]
        self.assertLess(np.cross(b - a, c - a)[1], 0)

    def test_holes_are_not_filled(self):
        mask = np.ones((8, 8), bool)
        mask[2:6, 2:6] = False
        vertices, faces = mesh_grid(np.zeros(mask.shape), np.zeros(
            mask.shape), mask, 'top', (1, 1, 1), .01)
        self.assertEqual(len(vertices), int(mask.sum()))
        self.assertLess(len(faces), 2 * 7 * 7)

    def test_incompatible_frames_are_rejected(self):
        with self.assertRaises(ValueError):
            mesh_grid(np.zeros((8, 8)), np.zeros((4, 4)), np.ones(
                (8, 8), bool), 'front', (1, 1, 1), .01)


if __name__ == '__main__':
    unittest.main()
