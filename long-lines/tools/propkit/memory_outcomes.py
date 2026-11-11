"""Record final QA separately from local-fit experience and physical verification."""
from contextlib import closing
from pathlib import Path
import sqlite3
from .build_memory import BuildMemory, fingerprint


def record(outcome, context=None, path=None):
    path = Path(path) if path is not None else Path(
        __file__).resolve().parents[3] / '.hull-memory' / 'reconstruction.sqlite3'
    context = context or {}
    try:
        key = fingerprint(context.get('asset'), context.get(
            'source'), outcome.get('input_sha256'))
        with closing(BuildMemory(path)) as memory:
            memory.event(key, 'build_outcome', {'context': context, 'outcome': outcome,
                                                'physical_geometry_verified': False})
        return {'status': 'recorded', 'path': str(path)}
    except (OSError, sqlite3.Error, ValueError) as error:
        return {'status': 'memory_failed', 'path': str(path), 'error': str(error)}
