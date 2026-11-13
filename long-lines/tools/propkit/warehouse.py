"""Candidate evidence and immutable releases. Pure Python; never edits geometry.

The library manifest is the publication boundary. Failed and uncertain runs stay
available outside the library; a failed publication cannot replace a good entry.
"""

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import struct
import tempfile
import uuid
import zlib


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def asset_name(name):
    if not isinstance(name, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_-]{0,119}", name
    ):
        raise ValueError("Asset name must be a simple identifier")
    if name.lower() in (
        "releases",
        "library",
        "con",
        "nul",
        "aux",
        "prn",
    ) or re.fullmatch(r"(com|lpt)[1-9]", name.lower()):
        raise ValueError("Reserved asset name")
    return name


def inside(root, relative):
    root = Path(root).resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or path == root:
        raise ValueError("Artifact path escapes its root")
    return path


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, delete=False
        ) as out:
            temporary = Path(out.name)
            json.dump(value, out, indent=2, allow_nan=False)
            out.write("\n")
            out.flush()
            os.fsync(out.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


@contextmanager
def library_lock(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    lock = root / ".hull-promotion.lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as error:
        raise RuntimeError(
            "Library is locked; inspect the previous promotion before clearing its lock"
        ) from error
    try:
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        yield
    finally:
        lock.unlink(missing_ok=True)


def asset_directory(library, name):
    name = asset_name(name)
    library = Path(library)
    manifest = library / "library.json"
    entry = (
        json.loads(manifest.read_text(encoding="utf-8")).get(name, {})
        if manifest.is_file()
        else {}
    )
    return inside(library, entry.get("artifact_directory", name))


def build_record(entries, name, run_id=None):
    """A release's label must not borrow QA from a newer failed build."""
    return next(
        (
            entry
            for entry in reversed(entries)
            if entry.get("op") == "build"
            and entry.get("name") == name
            and (run_id is None or entry.get("run_id") == run_id)
        ),
        {},
    )


def snapshot(folder):
    folder = Path(folder).resolve()
    files = {}
    for path in sorted(folder.rglob("*")):
        if path.is_symlink():
            raise ValueError("Symlinks are not candidate artifacts")
        if path.is_file():
            if path.suffix == ".import":
                continue  # Godot-generated import metadata is not a payload.
            relative = path.relative_to(folder).as_posix()
            inside(folder, relative)
            files[relative] = digest(path)
    return files


def container_triangles(raw):
    if (
        len(raw) < 20
        or raw[:4] != b"glTF"
        or struct.unpack("<II", raw[4:12]) != (2, len(raw))
    ):
        raise ValueError("Invalid GLB header")
    length, kind = struct.unpack("<II", raw[12:20])
    if kind != 0x4E4F534A or length % 4 or 20 + length > len(raw):
        raise ValueError("Invalid GLB JSON chunk")
    doc = json.loads(raw[20 : 20 + length])
    if doc.get("asset", {}).get("version") != "2.0":
        raise ValueError("Unsupported GLB version")
    offset = 20 + length
    if offset + 8 > len(raw):
        raise ValueError("Missing embedded geometry buffer")
    binary_length, binary_kind = struct.unpack("<II", raw[offset : offset + 8])
    if (
        binary_kind != 0x004E4942
        or binary_length % 4
        or offset + 8 + binary_length != len(raw)
    ):
        raise ValueError("Invalid embedded geometry buffer")
    buffers = doc.get("buffers", [])
    if (
        len(buffers) != 1
        or "uri" in buffers[0]
        or not 0 <= binary_length - buffers[0]["byteLength"] <= 3
    ):
        raise ValueError("Geometry buffer declaration differs from payload")
    for view in doc.get("bufferViews", []):
        if (
            view.get("buffer", 0) != 0
            or view.get("byteOffset", 0) < 0
            or view.get("byteOffset", 0) + view["byteLength"] > buffers[0]["byteLength"]
        ):
            raise ValueError("Geometry buffer view is outside the payload")
    total = 0
    for mesh in doc["meshes"]:
        for primitive in mesh["primitives"]:
            if (
                primitive.get("mode", 4) != 4
                or "POSITION" not in primitive["attributes"]
            ):
                raise ValueError("Expected triangle geometry")
            count = doc["accessors"][primitive["indices"]]["count"]
            if count < 3 or count % 3:
                raise ValueError("Invalid triangle index count")
            total += count // 3
    return total


def valid_png(raw):
    if raw[:8] != b"\x89PNG\r\n\x1a\n":
        return False
    offset = 8
    dimensions = False
    image_data = False
    while offset + 12 <= len(raw):
        size = struct.unpack(">I", raw[offset : offset + 4])[0]
        chunk = raw[offset + 4 : offset + 8]
        end = offset + 8 + size
        if (
            end + 4 > len(raw)
            or zlib.crc32(raw[offset + 4 : end])
            != struct.unpack(">I", raw[end : end + 4])[0]
        ):
            return False
        if chunk == b"IHDR":
            dimensions = (
                offset == 8
                and size == 13
                and all(struct.unpack(">II", raw[offset + 8 : offset + 16]))
            )
            if not dimensions:
                return False
        if chunk == b"IDAT":
            image_data = True
        if chunk == b"IEND":
            return dimensions and image_data and size == 0 and end + 4 == len(raw)
        offset = end + 4
    return False


def audit(receipt):
    """Independent storage/format audit; QA remains a separate geometry gauge."""
    fails = []
    name = asset_name(receipt["name"])
    library = Path(receipt["artifact_library_root"])
    folder = inside(library, name)
    try:
        if (
            digest(Path(receipt["run_directory"]) / "input-order.json")
            != receipt["order_sha256"]
        ):
            fails.append("Archived work order changed")
        for path, expected in receipt.get("context", {}).get("file_hashes", {}).items():
            if not Path(path).is_file() or digest(path) != expected:
                fails.append("Qualification input changed: " + path)
        entry = json.loads((library / "library.json").read_text(encoding="utf-8"))[name]
        if entry != receipt["manifest_entry"]:
            fails.append("Candidate manifest entry changed")
        if snapshot(folder) != receipt["artifact_hashes"]:
            fails.append("Artifact inventory changed after qualification")
        for suffix in (".glb", "_albedo.png", "_normal.png", "_orm.png"):
            path = folder / (name + suffix)
            if not path.is_file():
                fails.append("Missing required artifact: " + path.name)
                continue
            raw = path.read_bytes()
            if suffix == ".glb":
                if container_triangles(raw) != receipt["qa"]["metrics"].get("tris"):
                    fails.append("GLB triangle count differs from QA")
            elif not valid_png(raw):
                fails.append("Invalid PNG container: " + path.name)
        qa = receipt["qa"]
        if qa.get("pass") is not True or qa.get("fails"):
            fails.append("Geometry QA did not pass")
        if qa.get("inference_warnings"):
            fails.append("Inference remains uncertain")
        if qa.get("stage_review", {}).get("status") == "needs_review":
            fails.append("Stage review remains unresolved")
        metrics = qa.get("metrics", {})
        if (
            not isinstance(metrics.get("tris"), (int, float))
            or not math.isfinite(metrics["tris"])
            or metrics["tris"] <= 0
        ):
            fails.append("Missing finite triangle measurement")
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        IndexError,
        struct.error,
    ) as error:
        fails.append("Candidate evidence unreadable: " + str(error))
    return {
        "pass": not fails,
        "fails": fails,
        "physical_geometry_verified": False,
        "scope": "artifact identity, required containers and qualification disposition",
    }


def create(root, order, context=None):
    run_id = (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        + "-"
        + uuid.uuid4().hex[:12]
    )
    run = Path(root).resolve() / run_id
    run.mkdir(parents=True)
    atomic_json(run / "input-order.json", order)
    atomic_json(
        run / "run.json",
        {
            "schema": 1,
            "run_id": run_id,
            "name": asset_name(order["name"]),
            "state": "building",
            "context": context or {},
        },
    )
    return run


def seal(run, order, result, library):
    run, library = Path(run), Path(library).resolve()
    folder = inside(library, asset_name(order["name"]))
    receipt = json.loads((run / "run.json").read_text(encoding="utf-8"))
    receipt.update(
        artifact_library_root=str(library),
        qa=result,
        run_directory=str(run.resolve()),
        manifest_entry=(
            json.loads((library / "library.json").read_text(encoding="utf-8")).get(
                order["name"]
            )
            if (library / "library.json").is_file()
            else None
        ),
        artifact_hashes=snapshot(folder) if folder.is_dir() else {},
        order_sha256=digest(run / "input-order.json"),
        state="candidate",
    )
    receipt["audit"] = audit(receipt)
    receipt["state"] = (
        "qualified_candidate" if receipt["audit"]["pass"] else "quarantined"
    )
    atomic_json(run / "receipt.json", receipt)
    return receipt


def promote(receipt_path, library):
    """Publish an immutable version, then atomically select it in the manifest."""
    receipt_path = Path(receipt_path).resolve()
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if (
        receipt.get("state") not in ("qualified_candidate", "released")
        or not audit(receipt)["pass"]
    ):
        raise ValueError("Candidate is not qualified or its evidence changed")
    source_manifest = Path(receipt["artifact_library_root"]) / "library.json"
    entry = json.loads(source_manifest.read_text(encoding="utf-8"))[receipt["name"]]
    name, run_id = asset_name(receipt["name"]), receipt["run_id"]
    if not re.fullmatch(r"[A-Za-z0-9_-]+", run_id):
        raise ValueError("Invalid run identity")
    library = Path(library).resolve()
    relative = Path("releases") / name / run_id
    destination = inside(library, relative)
    with library_lock(library):
        manifest_path = library / "library.json"
        manifest = (
            json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest_path.is_file()
            else {}
        )
        previous = manifest.get(name)
        if destination.exists():
            if snapshot(destination) != receipt["artifact_hashes"]:
                raise ValueError("Immutable release identity collision")
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            staging = inside(
                library, relative.parent / ("_pending_" + uuid.uuid4().hex)
            )
            shutil.copytree(inside(receipt["artifact_library_root"], name), staging)
            if snapshot(staging) != receipt["artifact_hashes"]:
                raise ValueError("Release staging integrity check failed")
            staging.rename(destination)
        if snapshot(destination) != receipt["artifact_hashes"]:
            raise ValueError("Release copy failed integrity audit; manifest unchanged")
        entry = dict(
            entry,
            artifact_directory=relative.as_posix(),
            release_id=run_id,
            qualification="qa_and_artifact_audit",
            artifact_hashes=receipt["artifact_hashes"],
        )
        if previous != entry:
            atomic_json(receipt_path.parent / "previous-release.json", previous)
            atomic_json(
                receipt_path.parent / "publication.json",
                {
                    "library": str(library),
                    "name": name,
                    "before": previous,
                    "after": entry,
                    "state": "prepared",
                },
            )
            manifest[name] = entry
            atomic_json(manifest_path, dict(sorted(manifest.items())))
    # The pointer swap is the commit boundary; keep a recovery journal beforehand.
    receipt.update(state="released", published_library=str(library))
    try:
        atomic_json(receipt_path, receipt)
    except OSError:
        # The manifest already committed. Repeating promotion repairs this receipt.
        return dict(entry, receipt_update_pending=True)
    return entry


def rollback(receipt_path, library, expected_release):
    """Restore the saved pointer only if no newer publication has intervened."""
    receipt_path = Path(receipt_path).resolve()
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    name = asset_name(receipt["name"])
    journal = json.loads(
        (receipt_path.parent / "publication.json").read_text(encoding="utf-8")
    )
    library = Path(library).resolve()
    if (
        str(library) != journal["library"]
        or journal["after"]["release_id"] != expected_release
    ):
        raise ValueError(
            "Recovery library or expected release does not match publication"
        )
    with library_lock(library):
        path = library / "library.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if manifest.get(name) != journal["after"]:
            raise ValueError("Library changed since this publication; rollback refused")
        previous = journal["before"]
        if previous is None:
            manifest.pop(name)
        else:
            folder = inside(library, previous.get("artifact_directory", name))
            if not folder.is_dir():
                raise ValueError("Previous payload unavailable; rollback refused")
            if (
                previous.get("artifact_hashes")
                and snapshot(folder) != previous["artifact_hashes"]
            ):
                raise ValueError("Previous payload changed; rollback refused")
            manifest[name] = previous
        atomic_json(path, manifest)
    atomic_json(
        receipt_path.parent / ("rollback-" + uuid.uuid4().hex + ".json"),
        {
            "name": name,
            "from_release": expected_release,
            "restored": previous,
            "legacy_previous_unqualified": previous is not None
            and not previous.get("artifact_hashes"),
        },
    )
    return {"pass": True, "name": name, "restored": previous, "versions_retained": True}


def verify_release(library, name):
    entry = json.loads((Path(library) / "library.json").read_text(encoding="utf-8"))[
        asset_name(name)
    ]
    if not entry.get("artifact_hashes"):
        return {
            "pass": False,
            "status": "legacy_unqualified",
            "fails": ["No release receipt; legacy asset left unchanged"],
        }
    valid = snapshot(asset_directory(library, name)) == entry["artifact_hashes"]
    return {
        "pass": valid,
        "status": "verified" if valid else "changed",
        "fails": [] if valid else ["Released artifacts changed"],
    }
