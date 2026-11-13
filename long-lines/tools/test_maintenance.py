"""Operations contracts: coverage, drift, retained evidence and deterministic packaging."""

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from propkit import maintenance as m, warehouse as w

ROOT = Path(__file__).resolve().parents[2]


class MaintenanceTests(unittest.TestCase):
    def test_manifest_has_explicit_native_and_core_coverage(self):
        plan = m.load_plan(ROOT)
        self.assertEqual(
            {c["capability"] for c in plan["checks"]},
            {"core", "blender", "godot", "cad"},
        )
        self.assertTrue(m.repository_audit(ROOT)["pass"])

    def test_change_profiles_do_not_ignore_dependency_configuration_or_loader(self):
        self.assertEqual(m.choose_profiles(["README.md"]), [])
        self.assertEqual(m.choose_profiles(["requirements-core.txt"]), ["core"])
        self.assertEqual(
            m.choose_profiles(["long-lines/factory/standards.json"]), ["core"]
        )
        self.assertEqual(
            m.choose_profiles(["long-lines/tools/propkit/bake.py"]), ["blender", "core"]
        )
        self.assertEqual(
            m.choose_profiles(["long-lines/scripts/world/prop_factory.gd"]), ["godot"]
        )
        self.assertEqual(
            m.choose_profiles(["long-lines/assets/source_textures/new.png"]),
            ["blender", "core"],
        )

    def test_optional_profile_cannot_silently_pass_missing_backend(self):
        with patch.object(
            m.importlib, "import_module", side_effect=ImportError("unavailable")
        ):
            self.assertFalse(m.doctor(ROOT, ["cad"])["pass"])

    def test_required_skips_fail_qualification(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(
            m, "doctor", return_value={"pass": True}
        ), patch.object(
            m, "repository_audit", return_value={"pass": True}
        ), patch.object(
            m,
            "load_plan",
            return_value={
                "checks": [{"id": "probe", "capability": "core", "args": ["probe"]}]
            },
        ), patch.object(
            m.subprocess,
            "run",
            return_value=m.subprocess.CompletedProcess([], 0, "OK (skipped=2)", ""),
        ):
            self.assertFalse(m.run_checks(ROOT, ["core"], folder)["pass"])

    def test_missing_check_profile_is_not_qualified(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(
            m, "doctor", return_value={"pass": True}
        ), patch.object(m, "load_plan", return_value={"checks": []}):
            with self.assertRaises(ValueError):
                m.run_checks(ROOT, ["core"], folder)

    def test_incident_appends_learning_without_rewriting_qa(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "receipt.json"
            w.atomic_json(path, {"run_id": "failed", "qa": {"pass": False}})
            before = path.read_bytes()
            first = m.incident(
                path, "candidate cause", "no improvement", "test alternative"
            )
            second = m.incident(
                path, "new cause", "improved target", "check second fixture"
            )
            self.assertNotEqual(first["path"], second["path"])
            self.assertEqual(before, path.read_bytes())
            self.assertFalse(
                json.loads(Path(first["path"]).read_text())["qa_overridden"]
            )

    def test_regression_comparison_preserves_failure_and_rejects_nan(self):
        path = ROOT / "long-lines/tools/diag/regress_assets.py"
        spec = importlib.util.spec_from_file_location("regress_assets", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        baseline = {"iou_mean": 0.9, "folds_per_1k": 1, "ridge_deg": 2, "tris": 100}
        self.assertEqual(module.compare(dict(baseline), baseline), [])
        self.assertTrue(module.compare(dict(baseline, iou_mean=float("nan")), baseline))
        self.assertTrue(module.compare(dict(baseline, folds_per_1k=4), baseline))

    def test_bundle_is_deterministic_and_uses_committed_bytes(self):
        # A tiny independent git tree exercises staging, ignored data and ZIP reproducibility.
        import subprocess

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            subprocess.run(["git", "init", str(root)], check=True, capture_output=True)
            (root / "hull.py").write_text("original")
            (root / ".gitignore").write_text(".hull-runs/")
            (root / ".github").mkdir()
            (root / ".github/CODEOWNERS").write_text("* @owner")
            (root / "secret.png").write_bytes(b"private")
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(root),
                    "add",
                    "hull.py",
                    "secret.png",
                    ".gitignore",
                    ".github/CODEOWNERS",
                ],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(root),
                    "-c",
                    "user.name=Fixture",
                    "-c",
                    "user.email=fixture@example.invalid",
                    "commit",
                    "-m",
                    "fixture",
                ],
                check=True,
                capture_output=True,
            )
            (root / "hull.py").write_text("dirty")
            (root / "README.md").write_text("staged only")
            subprocess.run(
                ["git", "-C", str(root), "add", "README.md"],
                check=True,
                capture_output=True,
            )
            a = m.package(root, root / "a.zip")
            b = m.package(root, root / "b.zip")
            self.assertEqual(a["sha256"], b["sha256"])
            import zipfile

            with zipfile.ZipFile(root / "a.zip") as z:
                self.assertEqual(z.read("hull.py"), b"original")
                self.assertEqual(z.read(".gitignore"), b".hull-runs/")
                self.assertIn(".github/CODEOWNERS", z.namelist())
                self.assertNotIn("secret.png", z.namelist())
                self.assertNotIn("README.md", z.namelist())


if __name__ == "__main__":
    unittest.main()
