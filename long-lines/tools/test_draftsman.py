"""The draftsman stage (propkit/draftsman.py): rows of repeated parts and registered texture maps."""
import unittest

import numpy as np

from propkit import draftsman as dm


def _part(x0, x1, y=(0.2, 0.24), z=(0.48, 0.52), colour=(200, 180, 160)):
    return {'box_body': {'x': [x0, x1], 'y': list(y), 'z': list(z)}, 'colour': list(colour), 'views': ['front', 'top']}


class Rows(unittest.TestCase):
    def test_keys_in_a_line_are_a_row(self):
        parts = [_part(0.1 + 0.07 * i, 0.15 + 0.07 * i) for i in range(8)]
        rows = dm.rows(parts)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['along'], 'x')
        self.assertEqual(len(rows[0]['instances']), 8)

    def test_stacked_copies_of_one_place_are_not_a_row(self):
        parts = [_part(0.30, 0.35) for _ in range(6)]
        self.assertEqual(dm.rows(parts), [])

    def test_a_thick_band_is_not_a_row(self):
        parts = [_part(0.1 + 0.07 * i, 0.15 + 0.07 * i, z=(0.2, 0.6)) for i in range(8)]
        self.assertEqual(dm.rows(parts), [])

    def test_unlike_widths_are_not_one_row(self):
        parts = [_part(0.1 + 0.1 * i, 0.12 + 0.1 * i + (0.06 if i % 2 else 0)) for i in range(6)]
        rows = dm.rows(parts)
        self.assertTrue(all(len(r['instances']) < 6 for r in rows))


class TextureMaps(unittest.TestCase):
    def test_reference_views_map_to_themselves(self):
        class F:
            regs = {'x': None, 'z': None}
        res = {'frames': {'front': F()}}
        maps = dm.texture_maps(res)
        xs, ns = maps['front']['x']
        self.assertTrue(np.allclose(xs, ns))


if __name__ == '__main__':
    unittest.main()
