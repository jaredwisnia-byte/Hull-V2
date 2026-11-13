"""Release boundaries, fault injection and quarantine, without Blender."""

import json
from pathlib import Path
import struct
import tempfile
import unittest
import zlib
from unittest.mock import patch
from propkit import warehouse as w


class WarehouseTests(unittest.TestCase):
    def test_render_labels_follow_release_identity_not_latest_failed_build(self):
        rows = [
            {"op": "build", "name": "asset", "run_id": "old", "pass": True},
            {"op": "build", "name": "asset", "run_id": "new", "pass": False},
        ]
        self.assertTrue(w.build_record(rows, "asset", "old")["pass"])
        self.assertFalse(w.build_record(rows, "asset")["pass"])
        self.assertEqual(w.build_record(rows, "asset", "missing"), {})

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.order = {"name": "test_asset"}
        self.source_file = self.root / "hull.py"
        self.source_file.write_text("original code", encoding="utf-8")
        self.context = {
            "source_hashes": {"hull.py": w.digest(self.source_file)},
            "file_hashes": {str(self.source_file): w.digest(self.source_file)},
            "required_capabilities": ["core", "blender", "godot"],
            "runtime": {"python": "3.13.13", "packages": {"numpy": "2.5.4"},
                        "blender_path": str(self.root / "blender.exe"),
                        "blender_version": "5.2.3"},
        }
        self.qualification = self.root / "qualification.json"
        w.atomic_json(self.qualification, {
            "pass": True, "source_unchanged_during_checks": True,
            "repository_policy": {"pass": True},
            "profiles": ["core", "blender", "godot"],
            "source_hashes": self.context["source_hashes"],
            "runtime": {"pass": True, "python": "3.13.13",
                        "packages": {"numpy": "2.5.4"},
                        "qualified_capabilities": ["core", "blender", "godot"],
                        "tools": {"blender": {"path": str(self.root / "blender.exe"),
                                              "version": "Blender 5.2.3 LTS"}}},
            "checks": [{"id": name, "capability": name, "pass": True,
                        "exit_code": 0, "skipped": 0} for name in ("core", "blender", "godot")],
        })
        self.run = w.create(self.root / "runs", self.order, self.context)
        self.lib = self.run / "attempt-001/library"
        folder = self.lib / "test_asset"
        folder.mkdir(parents=True)
        binary = struct.pack("<9f3H", 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 1, 2)
        binary += b"\0" * ((-len(binary)) % 4)
        doc = json.dumps(
            {
                "asset": {"version": "2.0"},
                "meshes": [
                    {"primitives": [{"attributes": {"POSITION": 0}, "indices": 1}]}
                ],
                "buffers": [{"byteLength": 42}],
                "bufferViews": [
                    {"buffer": 0, "byteOffset": 0, "byteLength": 36},
                    {"buffer": 0, "byteOffset": 36, "byteLength": 6},
                ],
                "accessors": [
                    {
                        "count": 3,
                        "componentType": 5126,
                        "type": "VEC3",
                        "bufferView": 0,
                    },
                    {
                        "count": 3,
                        "componentType": 5123,
                        "type": "SCALAR",
                        "bufferView": 1,
                    },
                ],
            }
        ).encode()
        doc += b" " * ((-len(doc)) % 4)
        (folder / "test_asset.glb").write_bytes(
            b"glTF"
            + struct.pack("<II", 2, 28 + len(doc) + len(binary))
            + struct.pack("<II", len(doc), 0x4E4F534A)
            + doc
            + struct.pack("<II", len(binary), 0x004E4942)
            + binary
        )

        def chunk(name, data):
            return (
                struct.pack(">I", len(data))
                + name
                + data
                + struct.pack(">I", zlib.crc32(name + data))
            )

        png = (
            b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\0\0\0\0"))
            + chunk(b"IEND", b"")
        )
        for kind in ("albedo", "normal", "orm"):
            (folder / f"test_asset_{kind}.png").write_bytes(png)
        w.atomic_json(self.lib / "library.json", {"test_asset": {"tris": 1}})
        self.result = {
            "pass": True,
            "fails": [],
            "metrics": {"tris": 1},
            "inference_warnings": [],
        }

    def promote(self, receipt, release):
        return w.promote(receipt, release, self.qualification)

    def test_missing_stale_or_incomplete_qualification_cannot_publish(self):
        w.seal(self.run, self.order, self.result, self.lib)
        receipt = self.run / "receipt.json"
        release = self.root / "approved"
        w.atomic_json(release / "library.json", {"other": {"previous": True}})
        with self.assertRaisesRegex(ValueError, "qualification is required"):
            w.promote(receipt, release)
        original = json.loads(self.qualification.read_text())
        for change in (
            lambda q: q["source_hashes"].update({"hull.py": "other-source"}),
            lambda q: q["runtime"].update(python="3.12.0"),
            lambda q: q.update(profiles=["core"]),
            lambda q: q["checks"][1].update({"pass": False}),
        ):
            trial = json.loads(json.dumps(original))
            change(trial)
            w.atomic_json(self.qualification, trial)
            with self.assertRaisesRegex(ValueError, "qualification mismatch"):
                self.promote(receipt, release)
            self.assertEqual(json.loads((release / "library.json").read_text()),
                             {"other": {"previous": True}})
        w.atomic_json(self.qualification, original)
        candidate = json.loads(receipt.read_text())
        candidate["context"]["required_capabilities"].append("vision")
        w.atomic_json(receipt, candidate)
        with self.assertRaisesRegex(ValueError, "capability requirements"):
            self.promote(receipt, release)

    def test_source_change_after_build_blocks_publication(self):
        w.seal(self.run, self.order, self.result, self.lib)
        self.source_file.write_text("changed code", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "evidence changed"):
            self.promote(self.run / "receipt.json", self.root / "approved")
        self.assertFalse((self.root / "approved/library.json").exists())

    def test_failed_or_uncertain_candidate_cannot_replace_release(self):
        release = self.root / "approved"
        w.atomic_json(release / "library.json", {"test_asset": {"previous": True}})
        for field, value in [("pass", False), ("inference_warnings", ["uncalibrated"])]:
            result = dict(self.result, **{field: value})
            receipt = w.seal(self.run, self.order, result, self.lib)
            self.assertEqual(receipt["state"], "quarantined")
            with self.assertRaises(ValueError):
                self.promote(self.run / "receipt.json", release)
            self.assertEqual(
                json.loads((release / "library.json").read_text()),
                {"test_asset": {"previous": True}},
            )

    def test_release_is_immutable_and_manifest_resolves_version(self):
        w.seal(self.run, self.order, self.result, self.lib)
        release = self.root / "approved"
        entry = self.promote(self.run / "receipt.json", release)
        self.assertEqual(entry["release_id"], self.run.name)
        self.assertTrue(
            (w.asset_directory(release, "test_asset") / "test_asset.glb").is_file()
        )
        self.assertTrue(w.verify_release(release, "test_asset")["pass"])
        # Godot import sidecars do not mutate the payload identity.
        (w.asset_directory(release, "test_asset") / "test_asset.glb.import").write_text(
            "cache"
        )
        self.assertTrue(w.verify_release(release, "test_asset")["pass"])

    def test_corrupt_payload_and_manifest_are_detected(self):
        receipt = w.seal(self.run, self.order, self.result, self.lib)
        (self.lib / "test_asset/test_asset.glb").write_bytes(b"corrupt")
        self.assertFalse(w.audit(receipt)["pass"])
        w.atomic_json(self.lib / "library.json", {"test_asset": {"tris": 999}})
        self.assertIn("Candidate manifest entry changed", w.audit(receipt)["fails"])

    def test_changed_source_and_archived_order_block_promotion(self):
        source = self.root / "source.png"
        source.write_bytes(b"original")
        context = {"file_hashes": {str(source): w.digest(source)}}
        data = json.loads((self.run / "run.json").read_text())
        data["context"] = context
        w.atomic_json(self.run / "run.json", data)
        receipt = w.seal(self.run, self.order, self.result, self.lib)
        source.write_bytes(b"changed")
        self.assertFalse(w.audit(receipt)["pass"])
        (self.run / "input-order.json").write_text("{}")
        self.assertIn("Archived work order changed", w.audit(receipt)["fails"])

    def test_failed_copy_cannot_change_manifest(self):
        w.seal(self.run, self.order, self.result, self.lib)
        release = self.root / "approved"
        w.atomic_json(release / "library.json", {"other": {"old": True}})
        with patch.object(w.shutil, "copytree", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.promote(self.run / "receipt.json", release)
        self.assertEqual(
            json.loads((release / "library.json").read_text()), {"other": {"old": True}}
        )

    def test_existing_writer_lock_and_unsafe_paths_fail_closed(self):
        release = self.root / "approved"
        release.mkdir()
        (release / ".hull-promotion.lock").write_text("other writer")
        with self.assertRaises(RuntimeError):
            with w.library_lock(release):
                pass
        self.assertTrue((release / ".hull-promotion.lock").exists())
        for name in ("../escape", "C:/escape", "a/b", "releases"):
            with self.assertRaises(ValueError):
                w.asset_name(name)
        with self.assertRaises(ValueError):
            w.inside(release, "../escape")

    def test_atomic_json_failure_keeps_previous_and_cleans_temporary(self):
        path = self.root / "state.json"
        w.atomic_json(path, {"old": True})
        before = set(self.root.iterdir())
        with self.assertRaises(ValueError):
            w.atomic_json(path, {"bad": float("nan")})
        self.assertEqual(json.loads(path.read_text()), {"old": True})
        self.assertEqual(set(self.root.iterdir()), before)

    def test_idempotent_publication_retains_original_rollback_journal(self):
        w.seal(self.run, self.order, self.result, self.lib)
        release = self.root / "approved"
        entry = self.promote(self.run / "receipt.json", release)
        journal = (self.run / "publication.json").read_bytes()
        self.assertEqual(entry, self.promote(self.run / "receipt.json", release))
        self.assertEqual(journal, (self.run / "publication.json").read_bytes())
        w.rollback(self.run / "receipt.json", release, self.run.name)
        self.assertNotIn(
            "test_asset", json.loads((release / "library.json").read_text())
        )
        self.assertTrue((release / entry["artifact_directory"]).is_dir())

    def test_rollback_rejects_intervening_publication(self):
        w.seal(self.run, self.order, self.result, self.lib)
        release = self.root / "approved"
        self.promote(self.run / "receipt.json", release)
        manifest = json.loads((release / "library.json").read_text())
        manifest["test_asset"]["release_id"] = "newer"
        w.atomic_json(release / "library.json", manifest)
        with self.assertRaisesRegex(ValueError, "changed"):
            w.rollback(self.run / "receipt.json", release, self.run.name)
        self.assertEqual(json.loads((release / "library.json").read_text()), manifest)

    def test_receipt_write_failure_after_commit_is_recoverable(self):
        w.seal(self.run, self.order, self.result, self.lib)
        release = self.root / "approved"
        original = w.atomic_json

        def fail_receipt(path, value):
            if Path(path) == self.run / "receipt.json":
                raise OSError("disk full")
            original(path, value)

        with patch.object(w, "atomic_json", side_effect=fail_receipt):
            entry = self.promote(self.run / "receipt.json", release)
        self.assertTrue(entry["receipt_update_pending"])
        self.assertTrue(w.verify_release(release, "test_asset")["pass"])
        self.promote(self.run / "receipt.json", release)
        self.assertEqual(
            json.loads((self.run / "receipt.json").read_text())["state"], "released"
        )

    def test_two_versions_remain_available_after_guarded_rollback(self):
        w.seal(self.run, self.order, self.result, self.lib)
        release = self.root / "approved"
        first = self.promote(self.run / "receipt.json", release)
        next_run = w.create(self.root / "runs", self.order, self.context)
        w.seal(next_run, self.order, self.result, self.lib)
        second = self.promote(next_run / "receipt.json", release)
        self.assertNotEqual(first["release_id"], second["release_id"])
        w.rollback(next_run / "receipt.json", release, second["release_id"])
        self.assertEqual(
            json.loads((release / "library.json").read_text())["test_asset"], first
        )
        self.assertTrue((release / second["artifact_directory"]).is_dir())
        self.assertTrue(w.verify_release(release, "test_asset")["pass"])


if __name__ == "__main__":
    unittest.main()
