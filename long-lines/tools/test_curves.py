"""Curve tracing contracts: exact curve types, statistical rejection of paint noise, determinism."""
import unittest

import numpy as np

from propkit import curves


def canvas(size=(240, 320), value=40):
    return np.full(size + (3,), value, np.float64)


def disc(img, cx, cy, r, value):
    yy, xx = np.mgrid[:img.shape[0], :img.shape[1]]
    img[(xx - cx) ** 2 + (yy - cy) ** 2 <= r * r] = value


class CurveTypes(unittest.TestCase):
    def test_noisy_line_is_a_line_and_arc_is_a_circle(self):
        rng = np.random.default_rng(3)
        t = np.linspace(0, 100, 120)
        line = np.column_stack([t, 0.4 * t + 7]) + rng.normal(0, 0.3, (120, 2))
        self.assertEqual(curves.classify(line)[0]['type'], 'line')
        a = np.linspace(0.2, 2.6, 150)
        arc = np.column_stack([60 + 40 * np.cos(a), 50 + 40 * np.sin(a)]) + rng.normal(0, 0.3, (150, 2))
        curve, scores = curves.classify(arc)
        self.assertEqual(curve['type'], 'circle', scores)
        self.assertAlmostEqual(curve['radius'], 40, delta=1.0)

    def test_noise_cannot_buy_a_more_complex_curve(self):
        rng = np.random.default_rng(5)
        t = np.linspace(0, 80, 90)
        jagged = np.column_stack([t, 20 + rng.normal(0, 0.45, 90)])
        self.assertEqual(curves.classify(jagged)[0]['type'], 'line')


class PaintedViews(unittest.TestCase):
    def setUp(self):
        img = canvas()
        img[40:200, 60:260] = 200                    # a painted box body
        disc(img, 160, 120, 35, 90)                    # a round dial
        self.box = img

    def test_box_edges_and_dial_are_traced_as_exact_curves(self):
        result = curves.trace(self.box)
        types = [c['type'] for c in result['curves']]
        long_lines = [c for c in result['curves'] if c['type'] == 'line' and c['length_px'] > 100]
        self.assertGreaterEqual(len(long_lines), 4, types)
        round_ = [c for c in result['curves'] if c['type'] in ('circle', 'ellipse')
                  and c['length_px'] > 100]
        self.assertTrue(round_, types)
        r = round_[0].get('radius') or np.mean(round_[0]['axes'])
        self.assertAlmostEqual(r, 35, delta=2.0)

    def test_wear_strokes_are_rejected_while_real_edges_survive(self):
        img = self.box.copy()
        rng = np.random.default_rng(11)
        for _ in range(140):                           # short faint brush strokes inside the body
            x, y = rng.integers(70, 240), rng.integers(50, 190)
            ln, ang = rng.integers(6, 14), rng.uniform(0, np.pi)
            for s in np.linspace(0, ln, ln * 2):
                xi, yi = int(x + s * np.cos(ang)), int(y + s * np.sin(ang))
                img[yi, xi] = 200 + rng.uniform(-35, 35)
        img += rng.normal(0, 4, img.shape)
        result = curves.trace(np.clip(img, 0, 255))
        inside = [s for s in result['segments']
                  if 75 < s['p0'][0] < 245 and 55 < s['p0'][1] < 185 and 75 < s['p1'][0] < 245
                  and 55 < s['p1'][1] < 185 and np.hypot(np.mean([s['p0'][0], s['p1'][0]]) - 160,
                                                         np.mean([s['p0'][1], s['p1'][1]]) - 120) > 45]
        accepted_inside = [s for s in inside if s['accepted']]
        self.assertLessEqual(len(accepted_inside), max(1, len(inside) // 10),
                             [s['reasons'] for s in inside][:10])
        long_lines = [c for c in result['curves'] if c['type'] == 'line' and c['length_px'] > 100]
        self.assertGreaterEqual(len(long_lines), 4)

    def test_symmetric_view_votes_on_mirrored_curves(self):
        result = curves.trace(self.box)
        self.assertTrue(result['symmetry']['symmetric'])
        self.assertAlmostEqual(result['symmetry']['axis_x'], 159.5, delta=1.0)
        verticals = [c for c in result['curves'] if c['type'] == 'line' and c['length_px'] > 100
                     and abs(c['direction'][0]) < 0.1]
        self.assertTrue(verticals and all(c.get('mirrored') for c in verticals))

    def test_trace_is_deterministic(self):
        self.assertEqual(curves.trace(self.box), curves.trace(self.box))


if __name__ == '__main__':
    unittest.main()
