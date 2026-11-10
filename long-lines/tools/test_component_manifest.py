"""Run with ordinary Python; malformed instructions must fail before Blender builds."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from propkit.components import load_manifest, validate_manifest


def example():
    return {"name": "example", "reference": "sheet.png", "triangle_limit": 1000, "parts": [
        {"name": "body", "method": "polygon", "dimensions": [1, .5, 1], "budget": 500,
         "views": {"front": [0, 0, 100, 100], "right": [100, 0, 200, 100]}},
        {"name": "dial", "method": "round", "dimensions": [.1, .1, .02], "budget": 100,
         "views": {"front": [0, 100, 100, 120], "right": [100, 100, 200, 120], "top": [0, 120, 100, 220]},
         "attachment": {"parent": "body", "face": "top"}, "circular_axis": "vertical"}]}


class ManifestTests(unittest.TestCase):
    def test_prototypes_expand_without_inventing_dimensions(self):
        cfg = example()
        template = cfg["parts"].pop()
        cfg["prototypes"] = {"control": template}
        cfg["parts"].append({"name": "control_a", "prototype": "control"})
        result = validate_manifest(cfg)
        self.assertEqual(result["parts"][1]["dimensions"], [.1, .1, .02])
        cfg["parts"][1]["prototype"] = "missing"
        with self.assertRaisesRegex(ValueError, "unknown prototype"):
            validate_manifest(cfg)

    def test_dependencies_are_sorted_without_mutating_input(self):
        original = example()
        original["parts"].reverse()
        cfg = validate_manifest(original)
        self.assertEqual([p["name"] for p in cfg["parts"]], ["body", "dial"])
        self.assertEqual(original["parts"][0]["name"], "dial")

    def test_rejects_entire_assembly_overallocation(self):
        cfg = example()
        cfg["triangle_limit"] = 550
        with self.assertRaisesRegex(ValueError, "sum of component budgets"):
            validate_manifest(cfg)

    def test_prevents_oval_circular_parts(self):
        cfg = example()
        cfg["parts"][1]["dimensions"][1] = .08
        with self.assertRaisesRegex(ValueError, "circular dimensions"):
            validate_manifest(cfg)

    def test_invalid_depth_constraints(self):
        cfg = example()
        del cfg["parts"][0]["views"]["right"]
        with self.assertRaisesRegex(ValueError, "constrain depth"):
            validate_manifest(cfg)

    def test_invalid_inputs(self):
        changes = [lambda c: c["parts"][0].update(dimensions=[0, 1, 1]),
                   lambda c: c.update(triangle_limit=True),
                   lambda c: c["parts"][0].update(contour_tolerance=float("nan")),
                   lambda c: c["parts"][1].update(name="body"),
                   lambda c: c["parts"][1]["attachment"].update(overlap=-1),
                   lambda c: c["parts"][1]["attachment"].update(parent="missing"),
                   lambda c: c["parts"][0].update(views={"front": [1, 0, 0, 4]}),
                   lambda c: c["parts"][0].update(geometry_views=["unknown"])]
        for change in changes:
            with self.subTest(change=change):
                cfg = example()
                change(cfg)
                with self.assertRaises(ValueError):
                    validate_manifest(cfg)

    def test_integer_settings_reject_floats(self):
        for field in ("triangle_limit", "texture", "reconstruction_resolution"):
            cfg = example()
            cfg[field] = 1000.0
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "integer"):
                validate_manifest(cfg)
        cfg = example()
        cfg["parts"][0]["budget"] = 500.0
        with self.assertRaisesRegex(ValueError, "integer"):
            validate_manifest(cfg)

    def test_polygon_requires_independent_view_axes(self):
        for views in (("front", "back"), ("left", "right"), ("front", "front")):
            cfg = example()
            cfg["parts"][0]["views"] = {v: [0, 0, 100, 100] for v in views}
            cfg["parts"][0]["geometry_views"] = list(views)
            with self.subTest(views=views), self.assertRaisesRegex(ValueError, "constrain depth"):
                validate_manifest(cfg)
        for views in (("front", "right"), ("front", "top"), ("left", "top")):
            cfg = example()
            cfg["parts"][0]["views"] = {v: [0, 0, 100, 100] for v in views}
            validate_manifest(cfg)

    def test_cycles_are_rejected(self):
        cfg = example()
        cfg["parts"][0]["parent"] = "dial"
        with self.assertRaisesRegex(ValueError, "cyclic"):
            validate_manifest(cfg)

    def test_loads_utf8_bom_and_legacy_top_mount(self):
        cfg = example()
        del cfg["parts"][1]["attachment"]
        cfg["parts"][1]["mount"] = "top"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text(json.dumps(cfg), encoding="utf-8-sig")
            loaded, root = load_manifest(path)
            self.assertEqual(root, path.parent)
            self.assertEqual(loaded["parts"][1]["attachment"]["parent"], "body")


if __name__ == "__main__":
    unittest.main()
