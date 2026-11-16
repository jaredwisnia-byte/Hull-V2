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
    def test_section_basis_is_shared_across_sizes_and_keeps_measured_points(self):
        from OCP.BRepAdaptor import BRepAdaptor_Curve
        from OCP.GeomAbs import GeomAbs_BSplineCurve
        for exponent in (2, 3.7, 8):
            for axis in ('x', 'y', 'z'):
                with self.subTest(exponent=exponent, axis=axis):
                    bases = []
                    for ra, rb in ((40, 10), (10, 40)):
                        wire = cad_model._section_wire(axis, 7, 12, 19, ra, rb, exponent, 1, 1)
                        curves = [BRepAdaptor_Curve(edge.wrapped) for edge in wire.edges()
                                  if BRepAdaptor_Curve(edge.wrapped).GetType() == GeomAbs_BSplineCurve]
                        bases.append([[(curve.BSpline().Knot(i), curve.BSpline().Multiplicity(i))
                                       for i in range(1, curve.BSpline().NbKnots() + 1)] for curve in curves])
                        # The first quadrant still interpolates every source
                        # point at its prescribed parameter in physical mm.
                        parameters = cad_model._section_parameters(exponent)
                        for t, parameter in zip(np.linspace(0, np.pi / 2, 21), parameters):
                            c, s = np.cos(t), np.sin(t)
                            c = 0 if abs(c) < 1e-12 else c
                            s = 0 if abs(s) < 1e-12 else s
                            a, b = 13 + ra*c**(2/exponent), 20 + rb*s**(2/exponent)
                            expected = {'x': (7, a, b), 'y': (a, 7, b), 'z': (a, b, 7)}[axis]
                            np.testing.assert_allclose(tuple(curves[0].Value(parameter).Coord()), expected, atol=1e-6)
                    self.assertEqual(bases[0], bases[1])

    def test_hundred_station_loft_has_compact_control_nets_without_folds(self):
        from OCP.BRepAdaptor import BRepAdaptor_Surface
        from OCP.GeomAbs import GeomAbs_BSplineSurface
        from propkit import cad_mesh
        from propkit.mesh_health import folded_edges
        stations = [[t, .1 + .015*np.sin(2*np.pi*t) + (-1)**i*.003,
                     .9 + .015*np.sin(2*np.pi*t) - (-1)**i*.003,
                     .2 + .02*t, .8 - .01*t] for i, t in enumerate(np.linspace(.1, .9, 100))]
        for axis in ('x', 'y', 'z'):
            with self.subTest(axis=axis):
                _, loft, _ = cad_model._round_part(axis, dict(n=3.7, box=[.09,.91,0,1,0,1], stations=stations),
                                                  dict(width=100, depth=100, height=100),
                                                  dict(width=2, depth=2, height=2))
                self.assertTrue(BRepCheck_Analyzer(loft.wrapped).IsValid())
                for face in loft.faces():
                    surface = BRepAdaptor_Surface(face.wrapped)
                    if surface.GetType() == GeomAbs_BSplineSurface:
                        self.assertLessEqual(surface.BSpline().NbUPoles(), 32)
                mesh = cad_mesh.tessellate(loft, dict(width=.1, depth=.1, height=.1), .0004)
                self.assertEqual(folded_edges(mesh['vertices'], mesh['triangles'])['count'], 0)

    def test_sparse_loft_checks_all_measured_curved_sections_on_every_axis(self):
        from propkit import cad_mesh
        from propkit.mesh_health import folded_edges
        stations = [[.1 + i * .008, .15 + .08 * (i / 99)**2 + (-1)**i * .002,
                     .85 - .08 * (i / 99)**2 - (-1)**i * .002, .2, .8]
                    for i in range(100)]
        span, slack = (100, 100, 100), (1, 1, 1)
        fair = cad_model._fair_stations(stations, span, slack)
        for axis in ('x', 'y', 'z'):
            with self.subTest(axis=axis):
                solid, _, kept = cad_model._measured_loft(axis, fair, span, slack, 3.7)
                self.assertLess(len(kept), 30)
                self.assertEqual(kept, sorted(set(kept)))
                self.assertEqual((kept[0], kept[-1]), (0, 99))
                self.assertTrue(BRepCheck_Analyzer(solid.wrapped).IsValid())
                for station in fair:
                    self.assertLessEqual(cad_model._section_error(solid, axis, station, span, slack), 1.0000001)
                mesh = cad_mesh.tessellate(solid, dict(width=.1, depth=.1, height=.1), .0004)
                self.assertEqual(folded_edges(mesh['vertices'], mesh['triangles'])['count'], 0)
        # With no measured uncertainty, a nonlinear station cannot be discarded
        # merely because the bounding box fits. Constant sections still reduce.
        self.assertEqual(cad_model._station_subset(
            [[.1, .1, .9, .2, .8], [.5, .2, .8, .2, .8], [.9, .1, .9, .2, .8]],
            span, (0, 0, 0)), [0, 1, 2])

    def test_round_cell_support_has_no_unrounded_end_rims(self):
        from build123d import Box, Location
        from propkit import cad_mesh
        from propkit.mesh_health import folded_edges
        size = dict(width=100, depth=100, height=100)
        part = {'n': 4, 'box': [0, 1, 0, 1, 0, 1],
                'stations': [[t, 0, 1, 0, 1] for t in (.1, .5, .9)]}
        for axis in ('x', 'y', 'z'):
            with self.subTest(axis=axis):
                cell = dict(width=2, depth=2, height=2)
                cell[{'x': 'width', 'y': 'depth', 'z': 'height'}[axis]] = 20
                slab, loft, _ = cad_model._round_part(axis, part, size, cell)
                cube = Box(100, 100, 100).moved(Location((50, 50, 50)))
                result = ((cube - slab) + (cube & slab & loft)).clean()
                self.assertTrue(BRepCheck_Analyzer(result.wrapped).IsValid())
                self.assertEqual(len(result.solids()), 1)
                body = result.solids()[0]
                # A uniform measured section must stay round in the end cells,
                # rather than returning to square below/above station centres.
                for along in (5, 50, 95):
                    corner = {'x': (along, 5, 5), 'y': (5, along, 5),
                              'z': (5, 5, along)}[axis]
                    centre = {'x': (along, 50, 50), 'y': (50, along, 50),
                              'z': (50, 50, along)}[axis]
                    self.assertFalse(body.is_inside(corner), (axis, along))
                    self.assertTrue(body.is_inside(centre), (axis, along))
                mesh = cad_mesh.tessellate(result, dict(width=.1, depth=.1, height=.1), .0004)
                self.assertEqual(folded_edges(mesh['vertices'], mesh['triangles'])['count'], 0)

    def test_jittered_section_loft_has_no_extreme_joins(self):
        from propkit import cad_mesh
        from propkit.mesh_health import folded_edges
        size = dict(width=100, depth=100, height=100)
        cell = dict(width=2, depth=2, height=2)
        # Sub-cell radius jitter at closely spaced stations would create a row
        # of very acute ruled ridges on an otherwise smooth manufactured shaft.
        stations = [[.4 + i * .002, .1 + (-1)**i * .004,
                     .9 - (-1)**i * .004, .1, .9] for i in range(11)]
        for axis in ('x', 'y', 'z'):
            with self.subTest(axis=axis):
                part = {'n': 2, 'box': [.4, .42, 0, 1, 0, 1], 'stations': stations}
                _, solid, _ = cad_model._round_part(axis, part, size, cell)
                self.assertTrue(BRepCheck_Analyzer(solid.wrapped).IsValid())
                mesh = cad_mesh.tessellate(solid, dict(width=.1, depth=.1, height=.1), .0004)
                folds = folded_edges(mesh['vertices'], mesh['triangles'])
                self.assertEqual(folds['count'], 0, folds)
        fair = np.asarray(cad_model._fair_stations(stations, (100, 100, 100), (1, 1, 1)))
        np.testing.assert_array_equal(fair[:, 0], np.asarray(stations)[:, 0])
        self.assertLessEqual(float(np.max(np.abs(fair[:, 1:] - np.asarray(stations)[:, 1:]))), .01)


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
