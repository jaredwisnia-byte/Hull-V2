"""Seen first: cross-view agreement on a synthetic object with a known answer.

A box 200 x 100 x 120 (W x D x H, pixels at one scale) with a round boss (radius 25, 20 deep) on
its front face, a groove all round at height 30, and a paint band on the front only.
"""
import unittest

import numpy as np

from propkit import curve_views

W, D, H, R, BOSS = 200, 100, 120, 25, 20
CX, CZ = 100, 60
M = 30
BG, BODY, BOSS_V, GROOVE, PAINT = 40, 200, 150, 110, 170


def _img(w, h):
    return np.full((h + 2 * M, w + 2 * M, 3), BG, np.float64)


def front():
    im = _img(W, H)
    im[M:M + H, M:M + W] = BODY
    im[M:M + H - 100, M:M + W] = PAINT                    # paint band above z = 100 (front only)
    yy, xx = np.mgrid[:im.shape[0], :im.shape[1]]
    im[(xx - (M + CX)) ** 2 + (yy - (M + H - CZ)) ** 2 <= R * R] = BOSS_V
    im[M + H - 30 - 1:M + H - 30 + 1, M:M + W] = GROOVE  # groove at z = 30
    return im


def back():
    im = _img(W, H)
    im[M:M + H, M:M + W] = BODY
    im[M + H - 30 - 1:M + H - 30 + 1, M:M + W] = GROOVE
    return im


def right():                                             # u -> Y from -BOSS (boss front) to D
    im = _img(D + BOSS, H)
    im[M:M + H, M + BOSS:M + BOSS + D] = BODY
    im[M + H - CZ - R:M + H - CZ + R, M:M + BOSS] = BOSS_V
    im[M + H - 30 - 1:M + H - 30 + 1, M + BOSS:M + BOSS + D] = GROOVE
    return im


def top():                                               # v -> 1 - Y: back at the top row
    im = _img(W, D + BOSS)
    im[M:M + D, M:M + W] = BODY
    im[M + D:M + D + BOSS, M + CX - R:M + CX + R] = BOSS_V
    return im


class SeenFirst(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.images = {'front': front(), 'back': back(), 'right': right(), 'top': top()}
        cls.result = curve_views.analyse(cls.images)

    def test_boss_is_a_cylinder_along_the_depth(self):
        cyl = [c for c in self.result['constructions'] if c['construction'] == 'cylinder' and c['axis'] == 'y']
        self.assertTrue(cyl, [c['construction'] for c in self.result['constructions']])
        widths = [c['diameter_x'] for c in cyl if 'diameter_x' in c]
        self.assertTrue(widths, cyl)
        self.assertAlmostEqual(widths[0], 2 * R / W, delta=0.02)

    def test_groove_seen_in_two_views_is_a_plane(self):
        planes = [c for c in self.result['constructions'] if c['construction'] == 'plane' and c['axis'] == 'z']
        self.assertTrue(any(abs(c['at'] - 30 / H) <= 0.03 for c in planes), planes)

    def test_paint_band_on_one_view_is_not_geometry(self):
        band = [c for c in self.result['traces']['front']['curves']
                if c['type'] == 'line' and c['kind'] != 'outline' and c['length_px'] > 100
                and all(abs(p[1] - (M + H - 100)) <= 3 for p in c['points'])]
        self.assertTrue(band)
        self.assertTrue(all(c['tier'] == 'seen_once' for c in band), [c['support'] for c in band])
        decided = {(v, k) for c in self.result['constructions'] for v, k in c['curves']}
        front_curves = self.result['traces']['front']['curves']
        self.assertFalse(any(('front', front_curves.index(c)) in decided for c in band))

    def test_groove_in_front_and_back_runs_through(self):
        through = [c for c in self.result['constructions'] if c['construction'] == 'through']
        self.assertTrue(any(set(c['views']) == {'front', 'back'} for c in through), through)

    def test_tolerance_is_measured_and_small_for_a_registered_sheet(self):
        t = self.result['tolerances']
        self.assertTrue(t)
        self.assertTrue(all(v['tolerance'] <= 0.03 for v in t.values()), t)

    def test_analysis_is_deterministic(self):
        again = curve_views.analyse(self.images)
        self.assertEqual(again['constructions'], self.result['constructions'])
        self.assertEqual(again['tolerances'], self.result['tolerances'])


class Coincidence(unittest.TestCase):
    def test_chance_grows_with_clutter_and_tolerance(self):
        self.assertAlmostEqual(curve_views.chance(1, 0.01), 0.02)
        self.assertEqual(curve_views.chance(60, 0.05), 1.0)
        self.assertLess(curve_views.chance(10, 0.01, ends=2), 0.01)

    def test_unrelated_stripes_in_cluttered_views_are_not_evidence(self):
        rng = np.random.default_rng(7)

        def striped(w, heights):
            im = _img(w, H)
            im[M:M + H, M:M + w] = BODY
            for z in heights:
                im[M + H - z - 1:M + H - z + 1, M + 5:M + w - 5] = GROOVE
            return im
        hf = rng.choice(np.arange(6, H - 6, 2), 35, replace=False)
        hr = rng.choice(np.arange(7, H - 6, 2), 35, replace=False)   # odd heights: never the same
        result = curve_views.analyse({'front': striped(W, hf), 'right': striped(D, hr)})
        interior = [c for v in result['traces'].values() for c in v['curves'] if c['kind'] != 'outline']
        self.assertTrue(interior)
        self.assertFalse([c for c in interior if c['tier'] == 'consistent'])
        self.assertFalse([c for c in result['constructions'] if c['construction'] == 'plane'])


if __name__ == '__main__':
    unittest.main()
