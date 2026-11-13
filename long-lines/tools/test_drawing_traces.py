"""Measured drafting stations must retain source contours and uncertainty."""
import unittest

from propkit.drawing_traces import _elevation_section


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


if __name__ == '__main__':
    unittest.main()
