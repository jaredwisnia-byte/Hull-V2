"""Verify CAD source normals survive the existing Blender finish operations."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bmesh
import numpy as np
from propkit import bake, cad_mesh, core, simplification
from test_cad_mesh import fixture


class CADBlender(unittest.TestCase):
    def test_source_normals_survive_standardize_and_triangulation(self):
        core.reset()
        solid, size = fixture()
        data = cad_mesh.tessellate(solid, size, .0013)
        obj = cad_mesh.to_object(data, 'cad_test')
        high_data = cad_mesh.tessellate(solid, size, .0002)
        high = cad_mesh.to_object(high_data, 'cad_test__high', register=False)
        obj['dense_source_name'] = high.name
        self.assertEqual(core.PARTS, [obj])
        self.assertTrue(obj['bounded_surface_error'])
        bake.standardize(obj, 'cad_test', 256)
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bmesh.ops.triangulate(bm, faces=list(bm.faces))
        bm.to_mesh(obj.data)
        bm.free()
        simplification.refresh_normals(obj, planar=True)
        self.assertTrue(obj.data.has_custom_normals)
        want = np.asarray([tuple(n.vector) for n in obj.data.attributes[cad_mesh.NORMAL_ATTRIBUTE].data])
        got = np.asarray([tuple(n.vector) for n in obj.data.corner_normals])
        angles = np.arccos(np.clip(np.einsum('ij,ij->i', want, got), -1, 1))
        self.assertLess(float(angles.max()), np.deg2rad(.1))
        self.assertTrue(any(edge.use_edge_sharp for edge in obj.data.edges))
        self.assertEqual(len(obj.data.polygons), len(data['triangles']))
        combined = bake.combine_high_sources([obj], 'cad_test')
        self.assertEqual(combined.name, 'cad_test__high')
        self.assertEqual(len(combined.data.polygons), len(high_data['triangles']))


if __name__ == '__main__':
    result = unittest.main(argv=[sys.argv[0]], exit=False)
    if not result.result.wasSuccessful():
        raise SystemExit(1)
