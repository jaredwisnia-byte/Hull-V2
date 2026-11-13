"""Operations contracts: coverage, drift, retained evidence and deterministic packaging."""

import importlib.util
from contextlib import closing
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from propkit import maintenance as m, warehouse as w
from propkit import workspace_inventory
from propkit.build_memory import BuildMemory
import numpy as np

ROOT = Path(__file__).resolve().parents[2]


class MaintenanceTests(unittest.TestCase):
    def test_workspace_inventory_growth_and_unclassified_review(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            evidence = root / "Hull-trial"
            evidence.mkdir()
            (evidence / "result.bin").write_bytes(b"first")
            (root / "Hull-helper.py").write_text("pass")
            first = workspace_inventory.scan(root)
            self.assertEqual(first["review_candidates"], ["Hull-trial"])
            self.assertIsNone(first["top_level"]["Hull-trial"]["delta_bytes"])
            (evidence / "result.bin").write_bytes(b"first and second")
            second = workspace_inventory.scan(root, {"Hull-trial": "experiment evidence"}, first)
            self.assertEqual(second["top_level"]["Hull-trial"]["delta_bytes"], 11)
            self.assertEqual(second["review_candidates"], [])
            self.assertEqual(second["top_level"]["Hull-trial"]["role"],
                             "experiment evidence")
            self.assertEqual(second["no_longer_at_root"], [])
            (root / "Hull-helper.py").rename(root / "helper-archived.py")
            moved = workspace_inventory.scan(root, previous=second)
            self.assertEqual(moved["no_longer_at_root"], [
                {"name": "Hull-helper.py", "prior_bytes": 4,
                 "prior_role": None, "prior_partial": False}])
            self.assertIn("helper-archived.py", moved["top_level"])
            with self.assertRaises(ValueError):
                workspace_inventory.scan(root, previous=dict(first, root="elsewhere"))

    def test_workspace_inventory_does_not_report_growth_for_unreadable_subtree(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            denied = root / "Hull-denied"
            good = root / "Hull-good"
            denied.mkdir()
            good.mkdir()
            (denied / "evidence.bin").write_bytes(b"old")
            (good / "evidence.bin").write_bytes(b"old")
            first = workspace_inventory.scan(root)
            (good / "evidence.bin").write_bytes(b"new data")
            actual_scandir = workspace_inventory.os.scandir

            def intermittently_denied(path):
                if Path(path) == denied:
                    raise PermissionError("no access")
                return actual_scandir(path)

            with patch.object(workspace_inventory.os, "scandir", intermittently_denied):
                second = workspace_inventory.scan(root, previous=first)
            self.assertTrue(second["partial"])
            self.assertIsNone(second["top_level"]["Hull-denied"]["delta_bytes"])
            self.assertEqual(second["top_level"]["Hull-good"]["delta_bytes"], 5)

            with patch.object(workspace_inventory.os, "scandir", side_effect=PermissionError("root unreadable")):
                unknown = workspace_inventory.scan(root, previous=first)
            self.assertTrue(unknown["partial"])
            self.assertIsNone(unknown["no_longer_at_root"])

    def test_workspace_inventory_can_measure_allocation_without_confusing_logical_size(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            payload = root / 'Hull-evidence' / 'field.npy'
            payload.parent.mkdir()
            payload.write_bytes(b'0123456789')
            with patch.object(workspace_inventory, 'allocated_size', return_value=4):
                first = workspace_inventory.scan(root, include_allocated=True)
            self.assertEqual(first['total_bytes'], 10)
            self.assertEqual(first['allocated_bytes_observed'], 4)
            self.assertFalse(first['allocated_partial'])
            self.assertEqual(first['top_level']['Hull-evidence']['allocated_bytes'], 4)
            with patch.object(workspace_inventory, 'allocated_size', return_value=6):
                second = workspace_inventory.scan(root, previous=first,
                                                  include_allocated=True)
            self.assertEqual(second['top_level']['Hull-evidence']['delta_bytes'], 0)
            self.assertEqual(second['top_level']['Hull-evidence']['delta_allocated_bytes'], 2)
            with patch.object(workspace_inventory, 'allocated_size',
                              side_effect=OSError('allocation unavailable')):
                incomplete = workspace_inventory.scan(root, include_allocated=True)
            self.assertFalse(incomplete['partial'])
            self.assertTrue(incomplete['allocated_partial'])
            self.assertEqual(incomplete['total_bytes'], 10)

    def test_memory_inventory_command_writes_report_without_collecting(self):
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / 'memory.sqlite3'
            output = Path(folder) / 'inventory.json'
            with closing(BuildMemory(database)) as memory:
                memory.save('key', 'v1', {'status': 'accepted'}, [1],
                            np.ones((2, 2)), np.zeros((2, 2)))
            with patch.object(sys, 'argv', ['hull.py', 'memory-inventory',
                                            str(database), '--output', str(output),
                                            '--verify-hashes']):
                self.assertEqual(m.main(ROOT), 0)
            report = json.loads(output.read_text())
            self.assertEqual(report['counts']['referenced'], 1)
            self.assertTrue(report['files']['referenced'][0]['matches_record'])
            self.assertEqual(len(list((Path(folder) / 'patches').glob('*.npz'))), 1)

    def test_memory_quarantine_commands_restore_reviewed_orphan(self):
        with tempfile.TemporaryDirectory() as folder:
            database = Path(folder) / 'memory.sqlite3'
            report = Path(folder) / 'review.json'
            with closing(BuildMemory(database)) as memory:
                for scale in (1, 2):
                    memory.save('key', 'v1', {'status': 'accepted'}, [1],
                                np.ones((2, 2)) * scale, np.zeros((2, 2)))
            with patch.object(sys, 'argv', ['hull.py', 'memory-inventory',
                                            str(database), '--output', str(report),
                                            '--verify-hashes']):
                self.assertEqual(m.main(ROOT), 0)
            with patch.object(sys, 'argv', ['hull.py', 'memory-quarantine',
                                            str(database), '--reviewed-report',
                                            str(report), '--confirm-idle']):
                self.assertEqual(m.main(ROOT), 0)
            batch = next((Path(folder) / 'patches-quarantine').iterdir())
            self.assertEqual(len(list((Path(folder) / 'patches').glob('*.npz'))), 1)
            with patch.object(sys, 'argv', ['hull.py', 'memory-restore',
                                            str(database), str(batch)]):
                self.assertEqual(m.main(ROOT), 0)
            self.assertEqual(len(list((Path(folder) / 'patches').glob('*.npz'))), 2)

    def test_manifest_has_explicit_native_and_core_coverage(self):
        plan = m.load_plan(ROOT)
        self.assertEqual(
            {c["capability"] for c in plan["checks"]},
            {"core", "blender", "cad", "vision"},
        )
        registered = {c.get("script"): c["capability"] for c in plan["checks"]}
        for name in ("companion_captions", "local_retry", "observed_openings",
                     "probe_review", "process_planner"):
            self.assertEqual(registered[f"long-lines/tools/test_{name}.py"], "core")
        self.assertEqual(registered["long-lines/tools/test_retry_review.py"],
                         "blender")
        self.assertTrue(m.repository_audit(ROOT)["pass"])

    def test_change_profiles_do_not_ignore_dependency_configuration_or_loader(self):
        self.assertEqual(m.choose_profiles(["README.md"]), [])
        self.assertEqual(m.choose_profiles(["requirements-core.txt"]), ["core"])
        self.assertEqual(m.choose_profiles(["requirements-vision.txt"]),
                         ["blender", "core", "vision"])
        self.assertEqual(
            m.choose_profiles(["long-lines/factory/standards.json"]), ["core"]
        )
        self.assertEqual(
            m.choose_profiles(["long-lines/tools/propkit/bake.py"]), ["blender", "core"]
        )
        self.assertEqual(
            m.choose_profiles(["long-lines/tests/test_trim_checks.py"]), ["core"]
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
