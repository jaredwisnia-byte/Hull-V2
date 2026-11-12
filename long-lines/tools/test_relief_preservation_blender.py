"""Blender regression: uncertainty must not erase a real dense groove."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parent))
import bpy  # noqa: E402
import numpy as np  # noqa: E402
from propkit import surface_detail, simplification, local_features  # noqa: E402


class PreservationContracts(unittest.TestCase):
    def test_uncalibrated_groove_survives_bounded_reduction(self):
        x = np.linspace(-.1, .1, 81)
        z = np.linspace(0, .5, 161)
        xx, zz = np.meshgrid(x, z)
        depth = .004 * np.exp(-(xx / .012)**2) * np.sin(np.pi * zz / .5)**2
        vertices = np.c_[xx.ravel(), (-.02 + depth).ravel(), zz.ravel()]
        indices = np.arange(xx.size).reshape(xx.shape)
        a, b = indices[:-1, :-1], indices[:-1, 1:]
        c, d = indices[1:, :-1], indices[1:, 1:]
        faces = np.r_[np.c_[a.ravel(), b.ravel(), c.ravel()], np.c_[b.ravel(), d.ravel(), c.ravel()]]
        mesh = bpy.data.meshes.new('groove')
        mesh.from_pydata(vertices, [], faces)
        mesh.update()
        obj = bpy.data.objects.new('groove', mesh)
        bpy.context.collection.objects.link(obj)
        probes = []
        for n, height in enumerate(np.linspace(.1, .4, 7)):
            offsets = [-.004 * np.exp(-(u / .012)**2) * np.sin(np.pi * height / .5)**2 for u in (0, -.035, .035)]
            probes.append({'id': str(n), 'view': 'front', 'kind': 'groove', 'axis': 1, 'outward': -1,
                           'anchors_m': [[u, -.02, height] for u in (0, -.035, .035)],
                           'target_offsets_m': offsets, 'tolerance_m': .0001,
                           'depth_estimate': {'absolute_depth_supported_under_model': False}})
        report = {'probes': probes}
        guard = surface_detail.protected_samples(obj, report, geometry_tolerance=.0013)
        self.assertIsNotNone(guard)
        self.assertTrue(report['depth_review_required'])
        self.assertFalse(report['physical_depth_verified_by_preservation'])
        self.assertEqual(len(guard['contrast_report']['probes']), 7)
        self.assertFalse(guard['source_report']['probes'])
        count, error = simplification.decimate_to_error(obj, .0013, samples=1000, protected=guard)
        check = local_features.check_surface_features([tuple(v.co) for v in obj.data.vertices],
                                                       [tuple(p.vertices) for p in obj.data.polygons], report)
        self.assertFalse(check['fails'], check)
        self.assertLess(count, len(faces) / 10)
        self.assertLessEqual(error, .0013)
        bpy.data.objects.remove(obj, do_unlink=True)


if __name__ == '__main__':
    unittest.main(argv=[sys.argv[0]])
