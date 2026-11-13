"""Versioned reconstruction experience and resumable, integrity-checked patches.

An accepted numerical fit is never labelled verified physical geometry.
"""
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import time
import numpy as np


def fingerprint(*values):
    digest = hashlib.sha256()
    for value in values:
        if isinstance(value, np.ndarray):
            array = np.ascontiguousarray(value)
            digest.update(str((array.shape, array.dtype.str)).encode())
            digest.update(array.tobytes())
        else:
            digest.update(json.dumps(value, sort_keys=True,
                          allow_nan=False).encode())
        digest.update(b'\0')
    return digest.hexdigest()


def solver_version():
    import scipy
    directory = Path(__file__).parent
    from .tracing_backend import identity
    return fingerprint(np.__version__, scipy.__version__, identity(), *[(directory / name).read_text() for name in
                       ('regional_relief.py', 'reference_fitting.py', 'joint_shading.py', 'relief_selection.py', 'feature_regions.py', 'pixel_folds.py', 'tracing_backend.py', 'tracing_worker.py', 'feature_curves.py', 'build_memory.py')])


class BuildMemory:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.artifacts = self.path.parent / 'patches'
        self.artifacts.mkdir(exist_ok=True)
        self.db = sqlite3.connect(self.path, timeout=30)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS patches (
                key TEXT PRIMARY KEY, version TEXT NOT NULL, record TEXT NOT NULL,
                descriptor TEXT NOT NULL, artifact TEXT, digest TEXT, updated REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY, key TEXT NOT NULL, state TEXT NOT NULL,
                detail TEXT NOT NULL, created REAL NOT NULL);
        ''')

    def close(self):
        self.db.close()

    def event(self, key, state, detail):
        with self.db:
            self.db.execute('INSERT INTO events(key,state,detail,created) VALUES(?,?,?,?)',
                            (key, state, json.dumps(detail, sort_keys=True), time.time()))

    def load(self, key, version):
        row = self.db.execute('SELECT record,artifact,digest FROM patches WHERE key=? AND version=?',
                              (key, version)).fetchone()
        if row is None:
            return None
        record = json.loads(row[0])
        if record['status'] == 'deferred':
            return None
        path = self.artifacts / row[1]
        try:
            if hashlib.sha256(path.read_bytes()).hexdigest() != row[2]:
                raise ValueError('checkpoint hash mismatch')
            with np.load(path, allow_pickle=False) as data:
                height, material = data['height'].copy(
                ), data['material'].copy()
        except (OSError, ValueError, KeyError) as error:
            self.event(key, 'checkpoint_invalid', {'error': str(error)})
            return None
        self.event(key, 'resumed', {'status': record['status']})
        return height, material, record

    def save(self, key, version, record, descriptor, height, material):
        # Immutable artifact first, then transactional metadata. Interrupted
        # writes cannot turn a partially written patch into a valid checkpoint.
        with tempfile.NamedTemporaryFile(dir=self.artifacts, suffix='.npz', delete=False) as stream:
            temporary = Path(stream.name)
            np.savez_compressed(stream, height=height, material=material)
        digest = hashlib.sha256(temporary.read_bytes()).hexdigest()
        target = self.artifacts / (key + '-' + digest[:16] + '.npz')
        temporary.replace(target)
        saved = dict(record, physical_geometry_verified=False,
                     evidence='numerical validation only')
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO patches VALUES(?,?,?,?,?,?,?)',
                            (key, version, json.dumps(saved, sort_keys=True), json.dumps(descriptor), target.name, digest, time.time()))
        self.event(key, saved['status'], saved)

    def suggest(self, descriptor, version, limit=3):
        """Retrieve strategy hints; never return a patch as another object's truth."""
        matches = []
        for key, text, features in self.db.execute('SELECT key,record,descriptor FROM patches WHERE version=?', (version,)):
            record = json.loads(text)
            strategy = record.get('reference', {}).get('strategy')
            if strategy is None or not record.get('reference', {}).get('accepted', False):
                continue
            distance = float(np.linalg.norm(np.asarray(
                descriptor) - np.asarray(json.loads(features))))
            if distance <= 1.:
                matches.append({'key': key, 'distance': distance, 'strategy': strategy,
                                'evidence': 'reference approximation passed; physical geometry unverified'})
        return sorted(matches, key=lambda item: (item['distance'], item['key']))[:limit]

    def summary(self):
        statuses = {}
        for (text,) in self.db.execute('SELECT record FROM patches'):
            status = json.loads(text)['status']
            statuses[status] = statuses.get(status, 0) + 1
        return {'path': str(self.path), 'patches': sum(statuses.values()), 'statuses': statuses,
                'events': self.db.execute('SELECT count(*) FROM events').fetchone()[0],
                'physical_geometry_verified': False}

    def retention_inventory(self, verify_hashes=False):
        """Report referenced and unreferenced checkpoints without moving files.

        This is a live observation, not permission to collect an orphan: another
        process may be writing a checkpoint while the directory is scanned.
        """
        rows_before = self.db.execute(
            'SELECT artifact,digest FROM patches WHERE artifact IS NOT NULL ORDER BY artifact'
        ).fetchall()
        referenced = {name: digest for name, digest in rows_before}
        files = sorted(self.artifacts.glob('*.npz'))
        missing_referenced = sorted(set(referenced) - {path.name for path in files})
        groups = {'referenced': [], 'unreferenced': []}
        errors = []
        for path in files:
            try:
                stat_before = path.stat()
                entry = {'name': path.name, 'bytes': stat_before.st_size}
                if verify_hashes:
                    digest = hashlib.sha256()
                    with path.open('rb') as stream:
                        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                            digest.update(chunk)
                    entry['sha256'] = digest.hexdigest()
                    stat_after = path.stat()
                    entry['stable_during_hash'] = (
                        stat_before.st_size == stat_after.st_size and
                        stat_before.st_mtime_ns == stat_after.st_mtime_ns
                    )
                    if path.name in referenced:
                        entry['matches_record'] = entry['sha256'] == referenced[path.name]
                group = 'referenced' if path.name in referenced else 'unreferenced'
                groups[group].append(entry)
            except OSError as error:
                errors.append({'name': path.name, 'error': str(error)})
        rows_after = self.db.execute(
            'SELECT artifact,digest FROM patches WHERE artifact IS NOT NULL ORDER BY artifact'
        ).fetchall()
        return {
            'database': str(self.path),
            'snapshot_consistent': rows_before == rows_after and not errors
                                   and not missing_referenced,
            'collection_authorized': False,
            'scan_errors': errors,
            'missing_referenced': missing_referenced,
            'counts': {kind: len(items) for kind, items in groups.items()},
            'bytes': {kind: sum(item['bytes'] for item in items)
                      for kind, items in groups.items()},
            'files': groups,
        }
