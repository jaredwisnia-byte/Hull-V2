"""Read-only workspace retention contracts."""

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from propkit import maintenance, retention_manifest


class RetentionManifestContracts(unittest.TestCase):
    def test_inventory_detects_changed_and_unlisted_arrays(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            managed = root / "evidence" / "stages"
            managed.mkdir(parents=True)
            path = managed / "field.npy"
            path.write_bytes(b"source")
            manifest_path = root / "retention.json"
            manifest = {
                "schema": 1, "root": str(root),
                "managed_roots": ["evidence/stages"],
                "budget_logical_bytes": 12,
                "files": [{"path": "evidence/stages/field.npy", "bytes": 6,
                           "sha256": hashlib.sha256(b"source").hexdigest(),
                           "owner": "experiment", "role": "retained input",
                           "decision": "retain for comparison"}],
            }
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            metadata = retention_manifest.verify(manifest_path)
            self.assertTrue(metadata["pass"])
            self.assertFalse(metadata["hashes_checked"])
            self.assertEqual(metadata["files"][0]["status"], "metadata_match")
            self.assertFalse(metadata["collection_authorized"])
            self.assertTrue(retention_manifest.verify(manifest_path, True)["pass"])
            path.write_bytes(b"change")
            changed = retention_manifest.verify(manifest_path, True)
            self.assertFalse(changed["pass"])
            self.assertEqual(changed["files"][0]["status"], "hash_mismatch")
            (managed / "new.npy").write_bytes(b"new")
            unlisted = retention_manifest.verify(manifest_path)
            self.assertEqual(unlisted["unlisted_arrays"],
                             ["evidence/stages/new.npy"])
            self.assertFalse(unlisted["pass"])
            path.unlink()
            missing = retention_manifest.verify(manifest_path)
            self.assertEqual(missing["files"][0]["status"], "missing")
            self.assertFalse(missing["pass"])
            path.write_bytes(b"source")
            manifest["budget_logical_bytes"] = 5
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            self.assertFalse(retention_manifest.verify(manifest_path)["pass"])

    def test_manifest_cannot_escape_root_or_overwrite_itself(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "stages").mkdir()
            path = root / "manifest.json"
            manifest = {"schema": 1, "root": str(root),
                        "managed_roots": ["stages"], "budget_logical_bytes": 1,
                        "files": [{"path": "../outside.npy", "bytes": 0,
                                   "sha256": "0" * 64, "owner": "owner",
                                   "role": "evidence", "decision": "retain"}]}
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(ValueError):
                retention_manifest.verify(path)
            with patch("sys.argv", ["hull.py", "retention-verify", str(path),
                                    "--output", str(path)]):
                self.assertEqual(maintenance.main(root), 1)
            self.assertEqual(json.loads(path.read_text()), manifest)

    def test_cli_refuses_report_inside_managed_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            stages = root / "stages"
            stages.mkdir()
            array = stages / "field.npy"
            array.write_bytes(b"evidence")
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({
                "schema": 1, "root": str(root), "managed_roots": ["stages"],
                "budget_logical_bytes": 8,
                "files": [{"path": "stages/field.npy", "bytes": 8,
                           "sha256": hashlib.sha256(b"evidence").hexdigest(),
                           "owner": "experiment", "role": "input",
                           "decision": "retain"}]}), encoding="utf-8")
            with patch("sys.argv", ["hull.py", "retention-verify", str(manifest),
                                    "--output", str(array)]):
                self.assertEqual(maintenance.main(root), 1)
            self.assertEqual(array.read_bytes(), b"evidence")
            with patch("sys.argv", ["hull.py", "retention-verify", str(manifest),
                                    "--output", str(stages / "report.json")]):
                self.assertEqual(maintenance.main(root), 1)
            self.assertFalse((stages / "report.json").exists())


if __name__ == "__main__":
    unittest.main()
