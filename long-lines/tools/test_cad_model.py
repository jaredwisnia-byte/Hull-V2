"""CAD sections and opposed constraints, independent of asset identity or Blender."""
import unittest
import numpy as np
from OCP.BRepCheck import BRepCheck_Analyzer
from propkit import cad_model, drafting, drawing_qa


def drawing(top=None, bottom=None):
    rect = [[0, 0, 0], [100, 0, 0], [100, 100, 0], [0, 100, 0]]
    profiles = {v: {'vertices_px': rect, 'image_px': [100, 100]}
                for v in ('front', 'back', 'right', 'left', 'top', 'bottom')}
    for view, points in (('top', top), ('bottom', bottom)):
        if points is not None:
            profiles[view] = {'vertices_px': points, 'image_px': [100, 100]}
    record = {'profiles': profiles, 'size_m': {'width': .1, 'depth': .1, 'height': .1}}
    masks = {v: drafting.rasterize(np.asarray(p['vertices_px']), (100, 100)) for v, p in profiles.items()}
    return record, masks


class CADModel(unittest.TestCase):
    def test_offset_sections_preserve_the_existing_cell_membership_contract(self):
        from build123d import Face
        from propkit import rounding
        for exponent in (2.0, 3.5, 5.0):
            with self.subTest(exponent=exponent):
                expected = rounding._cells(np.ones(20, bool), np.ones(12, bool), exponent)
                face = Face(cad_model._section_wire('z', 0, 10, 6, 10, 6, exponent, .5, .5))
                observed = np.asarray([[face.is_inside((i + .5, j + .5, 0))
                                        for j in range(12)] for i in range(20)])
                np.testing.assert_array_equal(observed, expected)

    def test_opposed_asymmetric_plan_profiles_share_the_same_cad_frame(self):
        top = [[0, 0, 0], [70, 0, 0], [100, 30, 0], [100, 100, 0], [0, 100, 0]]
        # Drafting.FRAME: both plan views keep X; only their Y direction changes.
        bottom = [[x, 100 - y, b] for x, y, b in top]
        record, _ = drawing(top, bottom)
        size = {'width': 100, 'depth': 100, 'height': 100}
        a = cad_model._face(record, 'top', size)
        b = cad_model._face(record, 'bottom', size)
        self.assertAlmostEqual(a.area + b.area - 2 * (a & b).area, 0, places=6)

    def test_measured_sections_take_priority_over_older_round_end_loft(self):
        points = [[x, y, 0] for x, y in cad_model._superellipse_points(50, 50, 50, 50, 4)]
        record, masks = drawing()
        for view in ('front', 'back'):
            record['profiles'][view]['vertices_px'] = points
            masks[view] = drafting.rasterize(np.asarray(points), (100, 100))
        record['round_sections'] = [{'axis': 'y', 'center_m': [.05, .05], 'radius_m': .05}]
        # Interior rounding removes corner material; the end caps preserve the
        # independently traced end profiles. This must not be a no-effect loft.
        record['roundness'] = {'exponents': {'y': [{'n': 2.6, 'box': [.1, .9, 0, 1, 0, 1],
                                                  'stations': [[t, 0, 1, 0, 1] for t in (.1, .5, .9)]}]}}
        solid, report = cad_model.build_solid(record, masks)
        self.assertTrue(BRepCheck_Analyzer(solid.wrapped).IsValid())
        self.assertEqual(len(solid.solids()), 1)
        self.assertIn('supersede', report['round_lofts'][0]['skipped'])
        self.assertNotIn('skipped', report['round_parts'][0], report)
        self.assertNotIn('failed', report['round_parts'][0], report)
        self.assertGreater(report['round_parts'][0]['volume_removed_mm3'], 0)

    def test_measured_superellipse_keeps_outlines_and_one_valid_solid(self):
        points = [[x, y, 0] for x, y in cad_model._superellipse_points(50, 50, 50, 50, 4)]
        record, masks = drawing(points, points)
        record['roundness'] = {'exponents': {'z': [{'n': 2.6, 'box': [.1, .9, 0, 1, 0, 1],
                                                  'stations': [[t, 0, 1, 0, 1] for t in (.1, .5, .9)]}]}}
        solid, report = cad_model.build_solid(record, masks)
        self.assertTrue(BRepCheck_Analyzer(solid.wrapped).IsValid())
        self.assertEqual(len(solid.solids()), 1)
        self.assertNotIn('skipped', report['round_parts'][0], report)
        self.assertNotIn('failed', report['round_parts'][0], report)
        vertices, triangles = solid.tessellate(.4)
        _, failures = drawing_qa.against_drawing(np.asarray([list(v) for v in vertices]) / 1000,
                                                np.asarray(triangles), record)
        self.assertEqual(failures, [])

    def test_rounded_box_removes_unseen_corner_volume_within_drawing_limits(self):
        record, masks = drawing()
        record['roundness'] = {'exponents': {'z': [{'n': 4, 'box': [.1, .9, 0, 1, 0, 1],
            'stations': [[t, 0, 1, 0, 1] for t in (.1, .5, .9)]}]}}
        solid, report = cad_model.build_solid(record, masks)
        part = report['round_parts'][0]
        self.assertNotIn('skipped', part, part)
        self.assertNotIn('failed', part, part)
        self.assertGreater(part['volume_removed_mm3'], 1000)
        self.assertAlmostEqual(part['volume_removed_mm3'], 100 ** 3 - solid.volume, places=4)
        self.assertEqual(len(solid.solids()), 1)
        for view, values in part['views'].items():
            with self.subTest(view=view):
                self.assertLessEqual(values['after']['outline_p95_mm'], values['limit_mm'])
        section = part['mid_slab_section']
        self.assertAlmostEqual(section['level_mm'], 50)
        self.assertEqual(section['plane_axes'], [0, 1])
        self.assertTrue(section['before'] and section['after'])

    def test_no_effect_round_part_is_not_reported_as_applied(self):
        points = [[x, y, 0] for x, y in cad_model._superellipse_points(50, 50, 50, 50, 4)]
        record, masks = drawing(points, points)
        record['roundness'] = {'exponents': {'z': [{'n': 4, 'box': [0, 1, 0, 1, 0, 1],
            'stations': [[t, 0, 1, 0, 1] for t in (0, .5, 1)]}]}}
        _, report = cad_model.build_solid(record, masks)
        part = report['round_parts'][0]
        self.assertEqual(part['skipped'], 'no measurable volume removed', part)
        self.assertLessEqual(abs(part['volume_removed_mm3']), part['volume_epsilon_mm3'])
        self.assertNotIn('mid_slab_section', part)

    def test_three_mm_outline_displacement_names_view_and_p95(self):
        from build123d import Box, Location
        record, _ = drawing()
        before = Box(100, 100, 100).moved(Location((50, 50, 50)))
        # A 3 mm notch shifts a substantial front outline while the end caps
        # retain the overall bounds: the distance guard, not size, must reject it.
        cutter = Box(3, 110, 60).moved(Location((98.5, 50, 50)))
        accepted, detail = cad_model._replacement_check(before, before - cutter, record)
        self.assertFalse(accepted, detail)
        self.assertIn('front p95', detail['reason'])
        self.assertIn('3.00 mm', detail['reason'])
        self.assertLess(detail['size_change_mm'], 1e-5)

    def test_resolution_floor_uses_coarser_source_axis_in_mm(self):
        record, _ = drawing()
        record['profiles']['front']['image_px'] = [10, 100]
        self.assertEqual(cad_model.drawing_floor_mm(record, 'front'), 15)

    def test_bottom_foot_clearance_is_used_in_its_own_frame(self):
        # A small asymmetric clearance distinguishes the opposed sketch. It must
        # cut the specified corner, not the mirror corner, while keeping the
        # existing outline guard. No unseen height for the foot is invented.
        bottom = [[4, 0, 0], [100, 0, 0], [100, 100, 0], [0, 100, 0], [0, 4, 0]]
        record, masks = drawing(bottom=bottom)
        solid, report = cad_model.build_solid(record, masks)
        self.assertIn('bottom', report['profiles_used'], report)
        self.assertLess(solid.volume, 100 ** 3)
        self.assertEqual(cad_model._to3d('bottom', 7, 11,
                         {'width': 100, 'depth': 100, 'height': 100}), (7, 89, 0))


if __name__ == '__main__':
    unittest.main()
