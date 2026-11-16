"""CAD tessellation contracts on a manufactured solid outside the image cases."""
import unittest

import numpy as np
from build123d import Box, Cylinder, Location
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

from propkit import cad_mesh


def fixture():
    solid = (Box(100, 80, 40).moved(Location((50, 40, 20))) +
             Cylinder(20, 60).moved(Location((50, 40, 60))))
    return solid, {'width': .1, 'depth': .08, 'height': .09}


class CADMesh(unittest.TestCase):
    def test_box_and_cylinder_bounds_connectivity_orientation_and_repeat(self):
        solid, size = fixture()
        a = cad_mesh.tessellate(solid, size, .0013)
        b = cad_mesh.tessellate(solid, size, .0013)
        for key in ('vertices', 'triangles', 'normals', 'face_ids'):
            np.testing.assert_array_equal(a[key], b[key])
        self.assertEqual(a['report']['mesh_sha256'], b['report']['mesh_sha256'])
        v, t = a['vertices'], a['triangles']
        np.testing.assert_allclose(v.min(0), [-.05, -.04, 0], atol=1e-8)
        np.testing.assert_allclose(v.max(0), [.05, .04, .09], atol=1e-8)
        edges = np.concatenate([t[:, [0, 1]], t[:, [1, 2]], t[:, [2, 0]]])
        graph = coo_matrix((np.ones(len(edges)), (edges[:, 0], edges[:, 1])), shape=(len(v), len(v)))
        count, _ = connected_components(graph, directed=False)
        self.assertEqual(count, 1)
        points = v[t]
        crosses = np.cross(points[:, 1] - points[:, 0], points[:, 2] - points[:, 0])
        face_normals = crosses / np.linalg.norm(crosses, axis=1)[:, None]
        self.assertTrue(np.all(np.einsum('ij,ikj->ik', face_normals, a['normals']) > .8))
        volume = np.einsum('ij,ij->i', points[:, 0], np.cross(points[:, 1], points[:, 2])).sum() / 6
        self.assertGreater(volume, 0)
        self.assertLess(abs(volume - solid.volume / 1e9) / (solid.volume / 1e9), .05)
        adjacent = {}
        folds = 0
        for index, triangle in enumerate(t):
            for x, y in zip(triangle, np.roll(triangle, -1)):
                key = tuple(sorted((int(x), int(y))))
                if key in adjacent:
                    folds += int(np.dot(face_normals[index], face_normals[adjacent[key]]) < np.cos(2))
                else:
                    adjacent[key] = index
        self.assertEqual(folds, 0)

    def test_resolution_is_recomputed_after_fine_mesh_cache(self):
        solid, size = fixture()
        coarse = cad_mesh.tessellate(solid, size, .002)
        fine = cad_mesh.tessellate(solid, size, .00005)
        coarse_again = cad_mesh.tessellate(solid, size, .002)
        self.assertGreater(len(fine['triangles']), len(coarse['triangles']))
        np.testing.assert_array_equal(coarse['triangles'], coarse_again['triangles'])
        np.testing.assert_array_equal(coarse['vertices'], coarse_again['vertices'])

    def test_invalid_deflection_is_explicit(self):
        solid, size = fixture()
        for value in (0, -1, float('nan'), float('inf')):
            with self.subTest(value=value), self.assertRaises(ValueError):
                cad_mesh.tessellate(solid, size, value)

    def test_geometry_helper_invalidation_has_an_explicit_accessor_error(self):
        solid, size = fixture()
        cad_mesh.tessellate(solid, size, .0013)
        face = solid.faces()[0]
        mesh, _ = cad_mesh._face_triangulation(face, 0)
        self.assertGreater(mesh.NbTriangles(), 0)
        face.bounding_box()  # build123d deliberately removes this face's mesh cache
        with self.assertRaisesRegex(RuntimeError, 'cache was invalidated'):
            cad_mesh._face_triangulation(face, 0)


if __name__ == '__main__':
    unittest.main()
