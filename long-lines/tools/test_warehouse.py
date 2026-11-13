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
        self.run = w.create(self.root / "runs", self.order)
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

    def test_failed_or_uncertain_candidate_cannot_replace_release(self):
        release = self.root / "approved"
        w.atomic_json(release / "library.json", {"test_asset": {"previous": True}})
        for field, value in [("pass", False), ("inference_warnings", ["uncalibrated"])]:
            result = dict(self.result, **{field: value})
            receipt = w.seal(self.run, self.order, result, self.lib)
            self.assertEqual(receipt["state"], "quarantined")
            with self.assertRaises(ValueError):
                w.promote(self.run / "receipt.json", release)
            self.assertEqual(
                json.loads((release / "library.json").read_text()),
                {"test_asset": {"previous": True}},
            )

    def test_release_is_immutable_and_manifest_resolves_version(self):
        w.seal(self.run, self.order, self.result, self.lib)
        release = self.root / "approved"
        entry = w.promote(self.run / "receipt.json", release)
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
                w.promote(self.run / "receipt.json", release)
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
        entry = w.promote(self.run / "receipt.json", release)
        journal = (self.run / "publication.json").read_bytes()
        self.assertEqual(entry, w.promote(self.run / "receipt.json", release))
        self.assertEqual(journal, (self.run / "publication.json").read_bytes())
        w.rollback(self.run / "receipt.json", release, self.run.name)
        self.assertNotIn(
            "test_asset", json.loads((release / "library.json").read_text())
        )
        self.assertTrue((release / entry["artifact_directory"]).is_dir())

    def test_rollback_rejects_intervening_publication(self):
        w.seal(self.run, self.order, self.result, self.lib)
        release = self.root / "approved"
        w.promote(self.run / "receipt.json", release)
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
            entry = w.promote(self.run / "receipt.json", release)
        self.assertTrue(entry["receipt_update_pending"])
        self.assertTrue(w.verify_release(release, "test_asset")["pass"])
        w.promote(self.run / "receipt.json", release)
        self.assertEqual(
            json.loads((self.run / "receipt.json").read_text())["state"], "released"
        )

    def test_two_versions_remain_available_after_guarded_rollback(self):
        w.seal(self.run, self.order, self.result, self.lib)
        release = self.root / "approved"
        first = w.promote(self.run / "receipt.json", release)
        next_run = w.create(self.root / "runs", self.order)
        w.seal(next_run, self.order, self.result, self.lib)
        second = w.promote(next_run / "receipt.json", release)
        self.assertNotEqual(first["release_id"], second["release_id"])
        w.rollback(next_run / "receipt.json", release, second["release_id"])
        self.assertEqual(
            json.loads((release / "library.json").read_text())["test_asset"], first
        )
        self.assertTrue((release / second["artifact_directory"]).is_dir())
        self.assertTrue(w.verify_release(release, "test_asset")["pass"])


if __name__ == "__main__":
    unittest.main()
