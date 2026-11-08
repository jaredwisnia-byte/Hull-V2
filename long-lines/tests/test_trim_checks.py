"""Run: python -m unittest discover -s long-lines/tests -p 'test_trim_checks.py'"""
import importlib.util
import os
import tempfile
import unittest

from PIL import Image, ImageDraw

HERE = os.path.dirname(__file__)
path = os.path.join(HERE, "..", "tools", "propkit", "trim_checks.py")
spec = importlib.util.spec_from_file_location("trim_checks", path)
checks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checks)


class TrimChecksTest(unittest.TestCase):
    def paint(self, draw_fn):
        f = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        f.close()
        im = Image.new("RGB", (100, 100), (10, 10, 10))
        draw_fn(ImageDraw.Draw(im))
        im.save(f.name)
        self.addCleanup(lambda: os.unlink(f.name))
        return f.name

    def test_matching_exported_end_cap(self):
        source = self.paint(lambda p: p.rectangle((20, 10, 49, 89), fill="white"))
        verts = [(0, 0, 0), (0, .3, 0), (0, .3, .8), (0, 0, .8),
                 (1.2, 0, 0), (1.2, .3, 0), (1.2, .3, .8), (1.2, 0, .8)]
        result = checks.section_match(source, verts, [(0, 1, 2), (0, 2, 3)])
        self.assertGreater(result[0], .95)
        self.assertLess(result[1], .10)

    def test_wrong_section_rejected(self):
        source = self.paint(lambda p: p.rectangle((20, 10, 49, 89), fill="white"))
        verts = [(0, 0, 0), (0, .1, 0), (0, .1, .8), (0, 0, .8)]
        result = checks.section_match(source, verts, [(0, 1, 2), (0, 2, 3)])
        self.assertGreater(result[1], .5)

    def test_missing_cap_rejected(self):
        source = self.paint(lambda p: p.rectangle((20, 10, 49, 89), fill="white"))
        verts = [(0, 0, 0), (0, .3, 0), (0, 0, .8)]
        self.assertIsNone(checks.section_match(source, verts, []))

    def test_frame_void(self):
        def draw(p):
            p.rectangle((10, 10, 90, 90), fill="white")
            p.rectangle((23, 23, 77, 80), fill=(10, 10, 10))
        source = self.paint(draw)
        result = checks.opening_from_paint(source)
        self.assertIsNotNone(result)
        self.assertLess(result[0], .3)
        self.assertGreater(result[2], .7)

    def test_open_u_frame_retry(self):
        def draw(p):
            p.rectangle((10, 10, 90, 90), fill="white")
            p.rectangle((23, 23, 77, 99), fill=(10, 10, 10))
        source = self.paint(draw)
        self.assertIsNone(checks.opening_from_paint(source))
        self.assertIsNotNone(checks.opening_from_paint(source, "interior"))

    def test_geometry_hash_ignores_vertex_order_but_not_shape(self):
        a = [(0, 0, 0), (1, 2, 3)]
        self.assertEqual(checks.geometry_signature(a), checks.geometry_signature(list(reversed(a))))
        self.assertNotEqual(checks.geometry_signature(a), checks.geometry_signature([(0, 0, 0), (1, 2, 4)]))

    def test_geometry_hash_not_fooled_by_changed_faces(self):
        points = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)]
        a = checks.geometry_signature(points, [(0, 1, 2), (0, 2, 3)])
        b = checks.geometry_signature(points, [(0, 1, 3), (1, 2, 3)])
        self.assertNotEqual(a, b)

    def test_baked_colour_difference(self):
        source = self.paint(lambda p: p.rectangle((20, 10, 49, 89), fill=(120, 90, 70)))
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            output = f.name
        self.addCleanup(lambda: os.unlink(output))
        Image.new("RGB", (32, 32), (125, 91, 72)).save(output)
        self.assertLess(checks.texture_difference(source, output), .05)
        Image.new("RGB", (32, 32), (10, 200, 240)).save(output)
        self.assertGreater(checks.texture_difference(source, output), .35)


if __name__ == "__main__":
    unittest.main()
