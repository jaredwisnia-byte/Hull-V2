"""Blender regression: uncertainty must not erase a real dense groove."""
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parent))
import bpy  # noqa: E402
import numpy as np  # noqa: E402
from propkit import surface_detail, simplification, local_features  # noqa: E402


class PreservationContracts(unittest.TestCase):
    def test_rejected_reduction_candidates_leave_original_geometry_untouched(self):
        import json
        from unittest.mock import patch
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16)
        obj = bpy.context.object
        vertices = np.asarray([tuple(v.co) for v in obj.data.vertices])
        triangles = sum(len(p.vertices)-2 for p in obj.data.polygons)
        guard = {'points': np.asarray([[0.,0.,1.]]), 'tolerance_m': np.asarray([.001]),
                 'contrast_report': {'probes': []}}
        failed = {'fails': ['missing groove depth: synthetic'], 'probes': []}
        with patch.object(local_features, 'check_surface_features', return_value=failed):
            count, error = simplification.decimate_to_error(obj,.01,protected=guard)
        self.assertEqual(count,triangles)
        self.assertEqual(error,0.)
        np.testing.assert_array_equal(vertices,np.asarray([tuple(v.co) for v in obj.data.vertices]))
        reviews=json.loads(obj['simplification_correction_reviews'])
        self.assertTrue(reviews)
        self.assertTrue(all(not r['accepted'] for r in reviews))
        self.assertFalse(obj.vertex_groups.get('__hull_detail_guard'))

    def test_automatic_build_does_not_drop_a_view_to_hide_outline_failure(self):
        import factory
        import copy
        order = {'automatic_depth': True, 'line': 'hull', 'hull': {}}
        before = copy.deepcopy(order)
        result = {'fails': ['back outline mismatch', 'holes in mesh'], 'metrics': {}}
        self.assertFalse(factory.correct(order, result))
        self.assertEqual(order, before)
        self.assertEqual(result['correction_reviews'][0]['decision'], 'reject_and_rollback')

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
        self.assertEqual(len(guard['source_report']['probes']), 7)
        count, error = simplification.decimate_to_error(obj, .0013, samples=1000, protected=guard)
        check = local_features.check_surface_features([tuple(v.co) for v in obj.data.vertices],
                                                       [tuple(p.vertices) for p in obj.data.polygons], report)
        self.assertFalse(check['fails'], check)
        self.assertLess(count, len(faces) / 10)
        self.assertLessEqual(error, .0013)
        bpy.data.objects.remove(obj, do_unlink=True)


# Budget enforcement must not destroy a surface already reduced within an error bound.
class BudgetContracts(unittest.TestCase):
    def test_legacy_assembly_reduction_records_fixed_error_before_projection(self):
        from propkit import core
        core.reset()
        bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16)
        obj = bpy.context.object
        report = {}
        simplification.reduce_assembly_part(obj, {}, report)
        record = report['reduction'][0]
        self.assertTrue(obj['bounded_surface_error'])
        self.assertLessEqual(record['sampled_error_m'], record['tolerance_m'])
        self.assertEqual(record['stage'], 'before texture projection')
        self.assertLessEqual(record['triangles'], record['before'])

    def test_contact_witnesses_detect_lost_support_after_reduction(self):
        from propkit import core
        from propkit.hull_assembly import check_gaps
        core.reset()
        frame = core.box((1, 1, 1), loc=(0, 0, 1), bevel=0)
        foot = core.box((.2, .2, .5), loc=(0, 0, .25), bevel=0)
        bpy.context.view_layer.update()
        foot.data.update()
        witnesses = {foot.name: foot.data.copy()}
        boxes = [{'kind': 'foot', 'obj': foot, 'z': [0, .5]}]
        passing = check_gaps(boxes, [], frame, {}, witnesses)
        self.assertLessEqual(passing[0]['p90_mm'], .01)
        for vertex in foot.data.vertices:
            vertex.co.z -= .04
        foot.data.update()
        failing = check_gaps(boxes, [], frame, {}, witnesses)
        self.assertGreater(failing[0]['p90_mm'], 30)

    def test_final_baker_preserves_error_bounded_mesh_over_ceiling(self):
        from copy import deepcopy
        from unittest.mock import patch
        from propkit import bake, core
        core.reset()
        bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16)
        obj = bpy.context.object
        obj['bounded_surface_error'] = True
        before = sum(len(p.vertices)-2 for p in obj.data.polygons)
        standards = deepcopy(bake.STANDARDS)
        for value in standards['size_classes'].values():
            value['tri_budget'] = 20
        with patch.object(bake, 'STANDARDS', standards):
            _, notes = bake.standardize(obj, 'bounded_fixture', 256)
        self.assertEqual(before, sum(len(p.vertices)-2 for p in obj.data.polygons))
        self.assertTrue(any('QA must flag' in note for note in notes))


if __name__ == '__main__':
    unittest.main(argv=[sys.argv[0]])
