"""The drawing QA gauge uses the same bottom-view frame as the drawing and the CAD solid.

Drafting.FRAME, VIEW_UV, part_graph.AXES and cad_model keep a bottom view's X and reverse only
its Y. drawing_qa used to mirror X as well, so a correct solid failed its bottom view (run 3,
Order 3 diagnosis by Codex). An asymmetric plan shape catches any mirror.
"""
import unittest
import numpy as np
from propkit import cad_model, drafting, drawing_qa

TOP = [[0, 0, 0], [50, 0, 0], [100, 50, 0], [100, 100, 0], [0, 100, 0]]
SIZE = {'width': 100, 'depth': 100, 'height': 100}


def record():
    rect = [[0, 0, 0], [100, 0, 0], [100, 100, 0], [0, 100, 0]]
    profiles = {v: {'vertices_px': rect, 'image_px': [100, 100]}
                for v in ('front', 'back', 'right', 'left')}
    profiles['top'] = {'vertices_px': TOP, 'image_px': [100, 100]}
    profiles['bottom'] = {'vertices_px': [[x, 100 - y, b] for x, y, b in TOP], 'image_px': [100, 100]}
    return {'profiles': profiles, 'size_m': {'width': .1, 'depth': .1, 'height': .1}}


class BottomFrame(unittest.TestCase):
    def test_gauge_passes_the_solid_and_fails_its_x_mirror(self):
        from build123d import extrude
        rec = record()
        solid = extrude(cad_model._face(rec, 'top', SIZE), amount=100, dir=(0, 0, 1))
        vertices, triangles = solid.tessellate(.4)
        vertices = np.asarray([list(v) for v in vertices]) / 1000
        triangles = np.asarray(triangles)
        metrics, failures = drawing_qa.against_drawing(vertices, triangles, rec)
        self.assertGreaterEqual(metrics['views']['bottom']['iou'], .98)
        self.assertEqual(failures, [])
        mirrored = vertices.copy()
        mirrored[:, 0] = .1 - mirrored[:, 0]
        metrics, failures = drawing_qa.against_drawing(mirrored, triangles, rec)
        self.assertLess(metrics['views']['bottom']['iou'], .90)
        self.assertTrue(any(f.startswith('bottom view:') for f in failures), failures)

    def test_top_and_bottom_profiles_build_the_same_cad_face(self):
        rec = record()
        a, b = cad_model._face(rec, 'top', SIZE), cad_model._face(rec, 'bottom', SIZE)
        self.assertAlmostEqual(a.area + b.area - 2 * (a & b).area, 0, places=6)

    def test_gauge_and_drafting_frame_agree_on_bottom_x(self):
        self.assertEqual(drafting.FRAME['bottom'][:2], ('x', +1))
        self.assertFalse(drawing_qa.AXES['bottom'][2])


if __name__ == '__main__':
    unittest.main()
