"""Synthetic evidence regressions; no per-object coordinates in the pipeline."""
import numpy as np
import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from propkit.engineering import construction_graph, section_segments  # noqa: E402
from propkit.depth_inference import profile_depth, select_relief  # noqa: E402


class InferenceTests(unittest.TestCase):
    @unittest.skipUnless('bpy' in sys.modules, 'mesh displacement requires Blender')
    def test_selected_signed_depth_changes_geometry_and_obeys_cap(self):
        import bpy
        from propkit import relief
        from unittest.mock import patch
        with patch.object(relief, 'shared_light', return_value=np.array([-.7, -.7])), \
                patch.object(relief, 'view_relief', return_value=(np.zeros((16, 16)), {})):
            for sign in (-1, 1):
                mesh = bpy.data.meshes.new('test')
                mesh.from_pydata(
                    [(-.5, 0, 0), (.5, 0, 0), (.5, 0, 1), (-.5, 0, 1)], [], [(0, 1, 2, 3)])
                obj = bpy.data.objects.new('test', mesh)
                bpy.context.scene.collection.objects.link(obj)
                report = {}
                hook = relief.hook({'front': 'unused'}, 1, 1, 1, report,
                                   maps_override={'front': np.full((16, 16), sign*20.)}, keep_high=False, cap_share=.02)
                hook(obj)
                self.assertTrue(all(abs(v.co.y+sign*.02) <
                                1e-6 for v in mesh.vertices))
                bpy.data.objects.remove(obj, do_unlink=True)

    def test_depth_ignores_thin_mounting_pins(self):
        mask = np.zeros((100, 100), bool)
        mask[:, 10:30] = True
        mask[45:55, 30:90] = True
        result = profile_depth(.05, {'right': mask}, (.003, .02))
        self.assertAlmostEqual(result['depth_m'], .01)
        self.assertEqual(result['source'], 'side_profile')

    def test_conflicting_profiles_do_not_silently_average(self):
        result = profile_depth(.05, {'left': np.ones(
            (100, 20)), 'right': np.ones((100, 70))}, (.003, .02))
        self.assertTrue(result['profile_conflict'])
        self.assertTrue(result['needs_review'])
        self.assertEqual(result['source'], 'physical_prior')

    def test_observed_depth_not_clamped_to_prior(self):
        result = profile_depth(.05, {'right': np.ones(
            (100, 40))}, (.003, .008))
        self.assertAlmostEqual(result['depth_m'], .02)
        self.assertTrue(result['prior_conflict'])

    def test_missing_profile_uses_explicit_uncertain_prior(self):
        result = profile_depth(.05, {}, (.003, .008))
        self.assertEqual(result['source'], 'physical_prior')
        self.assertTrue(result['needs_review'])

    def test_raise_recess_and_flat_hypotheses(self):
        y, x = np.mgrid[-1:1:51j, -1:1:51j]
        dome = np.exp(-5*(x*x+y*y))
        light = np.array([-.7, -.7])
        gy, gx = np.gradient(dome)
        signal = -gx*light[0]-gy*light[1]
        candidates = {'raised': dome, 'recessed': -dome}
        mask = np.ones(dome.shape, bool)
        self.assertEqual(select_relief(
            signal, candidates, light, mask)[0], 'raised')
        self.assertEqual(select_relief(-signal, candidates,
                         light, mask)[0], 'recessed')
        self.assertEqual(select_relief(np.ones_like(signal),
                         candidates, light, mask)[0], 'flat')

    def test_ambiguous_hypotheses_are_flat(self):
        y, x = np.mgrid[-1:1:51j, -1:1:51j]
        h = x*x+y*y
        signal = -np.gradient(h)[1]
        self.assertEqual(select_relief(signal, {'a': h, 'b': h.copy()}, [
                         1, 0], np.ones(h.shape, bool))[0], 'flat')

    def test_local_feature_is_not_vetoed_by_unrelated_painted_noise(self):
        y, x = np.mgrid[-1:1:61j, -1:1:61j]
        height = np.exp(-5 * (x*x + y*y))
        gy, gx = np.gradient(height)
        signal = -gx
        mask = x < 0
        painted = signal.copy()
        painted[~mask] = np.random.default_rng(4).normal(0, 10, (~mask).sum())
        self.assertEqual(select_relief(
            painted, {'relief': height}, [1, 0], mask)[0], 'relief')
        self.assertEqual(select_relief(painted, {'relief': height}, [
                         1, 0], np.ones(mask.shape, bool))[0], 'flat')

    def test_graph_rejects_cycles_and_negative_dimensions(self):
        with self.assertRaises(ValueError):
            construction_graph(
                {'parts': [{'name': 'a', 'attach': {'to': 'a'}}]})
        with self.assertRaises(ValueError):
            construction_graph(
                {'parts': [{'name': 'a', 'vision_box': [1, 0, 0, 1, 0, 1]}]})

    def test_single_body_order_has_one_shared_identity(self):
        graph = construction_graph({'name': 'single_body', 'line': 'hull'})
        self.assertEqual([n['id'] for n in graph['nodes']], ['single_body'])
        self.assertFalse(graph['production_ready'])

    def test_sections_are_actual_intersections(self):
        vertices = np.array([[0, 0, 0], [1, 0, 0], [0, 0, 1]])
        segments = section_segments(vertices, np.array([[0, 1, 2]]), .5)
        self.assertEqual(segments.shape, (1, 2, 2))
        self.assertAlmostEqual(np.linalg.norm(
            segments[0, 1]-segments[0, 0]), .5)
        self.assertEqual(len(section_segments(
            vertices, np.array([[0, 1, 2]]), 2)), 0)


if __name__ == '__main__':
    unittest.main(argv=[__file__])
