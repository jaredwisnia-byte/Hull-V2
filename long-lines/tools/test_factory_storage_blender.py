"""Real bake/export/QA plus fault containment through the factory publication path."""

import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import factory
from propkit import maintenance, warehouse as w


class FactoryStorageContracts(unittest.TestCase):
    def test_native_candidate_promotion_failure_containment_and_recovery(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            approved = root / "approved"
            orders = root / "orders"
            orders.mkdir()
            source = root / "source"
            source.mkdir()
            (source / "reference-note.txt").write_text("original evidence")
            w.atomic_json(approved / "library.json", {"unrelated": {"legacy": True}})

            def cube(order):
                working = Path(order["views_folder"])
                self.assertNotEqual(working, source)
                (working / "reference-note.txt").write_text("prepared reference")
                factory.core.box(
                    (0.5, 0.5, 0.5),
                    loc=(0, 0, 0.25),
                    mat=factory.mats.paint((0.5, 0.3, 0.1)),
                    bevel=0.01,
                )

            order = {
                "name": "storage_fixture",
                "category": "fixture",
                "line": "recipe",
                "class": "medium",
                "tex": 256,
                "views_folder": str(source),
            }
            actual_doctor = maintenance.doctor

            def fixture_doctor(*args, **kwargs):
                evidence = actual_doctor(*args, **kwargs)
                evidence["pass"] = True  # Storage contract fixture, not a qualification.
                return evidence

            with patch.object(maintenance, "doctor", side_effect=fixture_doctor), patch.object(factory, "LIB", str(approved)), patch.object(
                factory, "ORDERS", str(orders)
            ), patch.object(factory, "LEDGER", str(root / "ledger.jsonl")), patch.dict(
                os.environ,
                {"HULL_RUN_ROOT": str(root / "runs"), "HULL_RELEASE_POLICY": "auto",
                 "HULL_QUALIFICATION_PATH": ""},
            ), patch.object(
                factory, "run_line", side_effect=cube
            ):
                candidate = factory.build(copy.deepcopy(order), samples=1)
                self.assertTrue(candidate["pass"], candidate)
                self.assertEqual(
                    (source / "reference-note.txt").read_text(), "original evidence"
                )
                saved = json.loads((orders / (order["name"] + ".json")).read_text())
                self.assertEqual(saved["views_folder"], str(source))
                self.assertNotIn("_input_views_snapshot", saved)
                raw = (
                    Path(saved["last_run"]) / "inputs/original_views/reference-note.txt"
                )
                self.assertEqual(raw.read_text(), "original evidence")
                self.assertEqual(
                    candidate["disposition"], "qualified_candidate", candidate
                )
                self.assertIn("qualification", candidate["release_hold_reason"])
                self.assertNotIn(
                    order["name"], json.loads((approved / "library.json").read_text())
                )
                receipt = Path(candidate["candidate_receipt"])
                context = json.loads(receipt.read_text())["context"]
                required = context["required_capabilities"]
                runtime = context["runtime"]
                qualification = root / "qualification.json"
                w.atomic_json(qualification, {
                    "pass": True,
                    "source_unchanged_during_checks": True,
                    "repository_policy": {"pass": True},
                    "profiles": required,
                    "planned_checks": context["required_checks"],
                    "source_hashes": context["source_hashes"],
                    "runtime": {
                        "pass": True,
                        "python": runtime["python"],
                        "packages": runtime["packages"],
                        "qualified_capabilities": required,
                        "tools": {"blender": {
                            "path": runtime["blender_path"],
                            "version": runtime["blender_version"],
                        }},
                    },
                    "checks": [{"id": check["id"], "capability": check["capability"],
                                "pass": True, "exit_code": 0, "skipped": 0}
                               for check in context["required_checks"]],
                })
                entry = w.promote(receipt, approved, qualification)
                self.assertTrue(w.verify_release(approved, order["name"])["pass"])
                selected = (approved / "library.json").read_bytes()
                # The public QA loader must follow the newly versioned directory.
                self.assertTrue(
                    factory.qa.check(order["name"], library_root=approved)["pass"]
                )
                with patch.object(
                    factory,
                    "run_line",
                    side_effect=ValueError("injected station fault"),
                ):
                    failed = factory.build(copy.deepcopy(order), samples=1)
                self.assertFalse(failed["pass"])
                self.assertEqual(failed["disposition"], "quarantined")
                self.assertEqual(selected, (approved / "library.json").read_bytes())
                self.assertTrue(Path(failed["candidate_receipt"]).is_file())
                self.assertTrue(
                    (Path(failed["candidate_receipt"]).parent / "result.json").is_file()
                )
                recovery = w.rollback(receipt, approved, entry["release_id"])
                self.assertTrue(recovery["pass"])
                self.assertEqual(
                    json.loads((approved / "library.json").read_text()),
                    {"unrelated": {"legacy": True}},
                )
                self.assertTrue((approved / entry["artifact_directory"]).is_dir())


if __name__ == "__main__":
    unittest.main(argv=["test_factory_storage_blender"], exit=True)
