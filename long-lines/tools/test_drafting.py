"""The drawing stage (propkit/drafting.py): orientation, clean profiles, round axes, CAD files."""
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from propkit import drafting


def _sheet(folder, top_turned=True):
    """A synthetic 'hair dryer': a round barrel along depth with a handle below it.
    W = 100, D = 200, H = 240 (px = mm). The top view is drawn turned a quarter, as sheets do."""
    folder = Path(folder)
    bg = (230, 230, 230)
    col = (180, 120, 80)

    def save(name, w, h, draw):
        im = Image.new('RGB', (w + 20, h + 20), bg)
        draw(ImageDraw.Draw(im), 10, 10)
        im.save(folder / ('v_%s.png' % name))
    # front: barrel circle (d=100) on top, handle below
    save('front', 100, 240, lambda d, x, y: (d.ellipse([x, y, x + 100, y + 100], fill=col),
                                             d.rectangle([x + 35, y + 90, x + 65, y + 240], fill=col)))
    save('back', 100, 240, lambda d, x, y: (d.ellipse([x, y, x + 100, y + 100], fill=col),
                                            d.rectangle([x + 35, y + 90, x + 65, y + 240], fill=col)))
    # right: nozzle (narrow) at the front (left), body at the back, handle under the back half
    side = lambda d, x, y: (d.polygon([(x, y + 25), (x + 80, y + 15), (x + 120, y), (x + 200, y),
                                       (x + 200, y + 100), (x + 120, y + 100), (x + 80, y + 85),
                                       (x, y + 75)], fill=col),
                            d.rectangle([x + 120, y + 90, x + 160, y + 240], fill=col))
    save('right', 200, 240, side)
    # top: x across, depth along: narrow nozzle at the front edge
    def top(d, x, y):
        # drawn the 'natural' way first (rows = depth, front at the bottom)...
        d.polygon([(x + 25, y + 200), (x + 75, y + 200), (x + 85, y + 120), (x + 100, y + 80),
                   (x + 100, y), (x, y), (x, y + 80), (x + 15, y + 120)], fill=col)
    save('top', 100, 200, top)
    if top_turned:      # ...then turned a quarter, as the sheet painted it
        im = Image.open(folder / 'v_top.png')
        im.rotate(90, expand=True).save(folder / 'v_top.png')
    return {k: str(folder / ('v_%s.png' % k)) for k in ('front', 'back', 'right', 'top')}


class Drafting(unittest.TestCase):
    def test_turned_top_view_is_turned_back(self):
        with tempfile.TemporaryDirectory() as t:
            views = _sheet(t)
            rec = drafting.prepare(views, Path(t) / 'out', 0.24, name='dryer')
            o = rec['orientation']['top']['chosen']
            self.assertNotEqual(o['turns_ccw'] % 4, 0, rec['orientation'])
            self.assertLess(abs(rec['view_agreement']['top']['off_pct']), 10)
            # the turned view on disk is what the build paints and carves with
            w, h = Image.open(rec['views']['top']).size
            self.assertGreater(h, w)

    def test_profiles_are_lines_and_arcs_within_tolerance(self):
        with tempfile.TemporaryDirectory() as t:
            rec = drafting.prepare(_sheet(t), Path(t) / 'out', 0.24, name='dryer')
            for view, prof in rec['profiles'].items():
                self.assertLessEqual(prof['max_deviation_px'], 2.0, view)
            self.assertGreater(rec['profiles']['front']['arcs'], 0)

    def test_round_end_view_marks_round_sections(self):
        with tempfile.TemporaryDirectory() as t:
            rec = drafting.prepare(_sheet(t), Path(t) / 'out', 0.24, name='dryer')
            axes = [r['axis'] for r in rec['round_sections']]
            self.assertIn('y', axes)
            r = [r for r in rec['round_sections'] if r['axis'] == 'y'][0]
            self.assertAlmostEqual(r['radius_m'] * 2, 0.100, delta=0.008)

    def test_writes_dxf_with_dimensions_in_mm(self):
        import ezdxf
        with tempfile.TemporaryDirectory() as t:
            rec = drafting.prepare(_sheet(t), Path(t) / 'out', 0.24, name='dryer')
            doc = ezdxf.readfile(rec['dxf'])
            dims = [d.get_measurement() for d in doc.modelspace().query('DIMENSION')]
            self.assertTrue(any(abs(d - 240) < 1.5 for d in dims if isinstance(d, float)), dims)
            self.assertTrue(Path(rec['sheet']).exists())
            json.loads((Path(t) / 'out' / 'drawing.json').read_text())

    def test_cad_solid_from_drawing(self):
        try:
            import build123d  # noqa: F401
        except ImportError:
            self.skipTest('build123d not installed')
        from propkit import cad_model
        with tempfile.TemporaryDirectory() as t:
            rec = drafting.prepare(_sheet(t), Path(t) / 'out', 0.24, name='dryer')
            rep = cad_model.export(rec, rec['masks'], Path(t) / 'cad', 'dryer')
            self.assertTrue(Path(rep['step']).exists())
            W, D, H = rep['bounding_box_mm']
            self.assertAlmostEqual(H, 240, delta=4)
            self.assertAlmostEqual(W, 100, delta=4)
            self.assertAlmostEqual(D, 200, delta=6)


if __name__ == '__main__':
    unittest.main()
