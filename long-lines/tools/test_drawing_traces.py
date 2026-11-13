"""Measured drafting stations must retain source contours and uncertainty."""
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from propkit.drawing_traces import _elevation_section, _end_frame_hypotheses, infer


class SourceSectionContracts(unittest.TestCase):
    def test_rectangle_uses_the_two_contour_crossings(self):
        contour = [[2., 1.], [12., 1.], [12., 21.],
                   [2., 21.], [2., 1.]]
        section = _elevation_section([contour], 11., .5)
        self.assertEqual(section['outer_envelope_x_source_px'], [2., 12.])
        self.assertEqual({p['source_trace_id'] for p in section['crossings']},
                         {'outer:0'})
        self.assertTrue(section['crossing_parity_valid'])
        self.assertEqual(section['physical_cross_section_shape'], 'unobserved')

    def test_nonconvex_outline_preserves_all_crossings(self):
        # At this height the source has two separated lobes. A fitted ellipse
        # would erase that gap; the drawing records all four observed edges.
        contour = [[0., 0.], [10., 0.], [10., 20.], [7., 20.],
                   [7., 5.], [3., 5.], [3., 20.], [0., 20.], [0., 0.]]
        section = _elevation_section([contour], 10., .5)
        self.assertEqual([p['x_source_px'] for p in section['crossings']],
                         [0., 3., 7., 10.])
        self.assertEqual(section['outer_envelope_x_source_px'], [0., 10.])
        self.assertTrue(section['crossing_parity_valid'])

    def test_open_or_missing_contour_is_not_called_a_physical_section(self):
        section = _elevation_section([[[0., 0.], [0., 20.]]], 10., .5)
        self.assertIsNone(section['outer_envelope_x_source_px'])
        self.assertFalse(section['crossing_parity_valid'])
        self.assertEqual(section['physical_cross_section_shape'], 'unobserved')

    def test_odd_crossings_do_not_produce_a_measured_envelope(self):
        lines = [[[x, 0.], [x, 20.]] for x in (0., 5., 10.)]
        section = _elevation_section(lines, 10., .5)
        self.assertEqual(len(section['crossings']), 3)
        self.assertIsNone(section['outer_envelope_x_source_px'])
        self.assertFalse(section['crossing_parity_valid'])

    def test_preflight_conflict_is_distinct_from_actual_construction_use(self):
        def observed(view, path, *unused):
            return {'source_size_px': [20, 20], 'foreground_box_px': [2, 2, 18, 18],
                    'observed_elevation_sections': [], 'traces': [],
                    'outer_path_count': 0, 'internal_path_count': 0,
                    'opposed_mask_opening_count': 0}

        with tempfile.TemporaryDirectory() as folder, patch(
                'propkit.drawing_traces.observe', side_effect=observed):
            views = {'front': 'front.png', 'top': 'top.png'}
            preflight = {'paint_only': ['top'], 'views': {'top': {'off_pct': 184.1}}}
            used = infer(views, Path(folder) / 'used',
                         view_consistency=preflight, geometry_views=views)
            held = infer(views, Path(folder) / 'held',
                         view_consistency=preflight, geometry_views={'front': 'front.png'})
        self.assertEqual(used['view_conflicts_in_use'], ['top'])
        self.assertEqual(used['view_construction_use']['top']['preflight_proportion_off_pct'],
                         184.1)
        self.assertFalse(held['view_conflicts_in_use'])
        self.assertFalse(held['view_construction_use']['top']['used_for_geometry'])

    def test_end_frame_evidence_does_not_choose_a_rotation(self):
        observations = {'front': {'foreground_box_px': [0, 0, 40, 100]},
                        'right': {'foreground_box_px': [0, 0, 80, 100]},
                        'top': {'foreground_box_px': [0, 0, 100, 50]}}
        top = _end_frame_hypotheses(observations)['top']
        self.assertAlmostEqual(top['axis_residual_log']['90_or_270_degrees'], 0)
        self.assertGreater(top['axis_residual_log']['0_or_180_degrees'], 1)
        self.assertIn('unresolved', top['status'])
        self.assertEqual(top['construction_use'], 'diagnostic_only')


if __name__ == '__main__':
    unittest.main()
