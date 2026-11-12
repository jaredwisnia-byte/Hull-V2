"""Optional local MatchED/phase tracing, isolated from Blender's Python runtime.

Models and third-party source live in a gitignored local registry. No network
request, model download, or LLM call occurs during reconstruction.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import zipfile
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
MODEL_SHA256 = 'bb2e6074cc35e04549c2924dc0e3aecb934b52788e319f4596b04dfa9963bbba'

SOURCE_SHA256 = {'network.py': '827046e934c3d0bbe722b89f191002b274221644dcace2023e04ae9ff177282a', 'models/__init__.py': '61e1539d4d859d2d1a789d2565f4a758e853e58ea8751079a8d5b1214cc23c6d', 'models/pidinet.py': '6f68fc47040aca6f6017cab80c5581886328db3fb1b3223a445518d34b9c71b2',
                 'models/ops.py': 'b71294df26463b3caf075f1cc596e9849b2859f35db230346ed7f02f35a4ba34', 'models/config.py': '5790cb9469694f7c3f2e690b8f9964b0fbc5f8e82ac3e18b9d28ad208f01a752', 'models/hed_fps.py': '3e786e471dc70c76e795fd1c896a1bffb540fe103e7274bf478b531f727956ea'}


class Unavailable(RuntimeError):
    pass


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def configuration_path():
    return Path(os.environ.get('HULL_TRACE_CONFIG', ROOT / '.hull-models/tracing.json'))


def configuration():
    path = configuration_path()
    if not path.is_file():
        raise Unavailable('Local structural tracer is not configured')
    data = json.loads(path.read_text(encoding='utf-8'))
    if data.get('schema') != 1 or data.get('model_sha256') != MODEL_SHA256:
        raise ValueError('Unsupported tracing registry or checkpoint identity')
    for filename, expected in data['artifact_hashes'].items():
        if not Path(filename).is_file() or digest(filename) != expected:
            raise ValueError('Tracing artifact checksum mismatch: ' + filename)
    return data


def identity(requested=None):
    # End-to-end retention regressed despite better 2D edges. Keep deployment
    # explicit until the region/geometry handoff also passes common-probe tests.
    policy = requested or os.environ.get('HULL_TRACE_BACKEND', 'classical')
    if policy not in ('auto', 'matched', 'classical'):
        raise ValueError('Unknown tracing backend')
    if policy == 'classical':
        return {'requested': policy, 'selected': 'classical'}
    try:
        data = configuration()
    except Unavailable:
        if policy == 'matched':
            raise
        return {'requested': policy, 'selected': 'classical', 'reason': 'model_not_configured'}
    return {'requested': policy, 'selected': 'matched_biped_2026',
            'model_sha256': data['model_sha256'], 'versions': data['versions'],
            'source_hashes': sorted(data['artifact_hashes'].values()),
            'worker_sha256': digest(Path(__file__).with_name('tracing_worker.py')),
            'adapter_sha256': digest(__file__)}


def srgb_pixels(linear, mask):
    linear = np.clip(np.asarray(linear, float), 0, 1)
    value = np.where(linear <= .0031308, linear * 12.92,
                     1.055 * np.maximum(linear, 0)**(1 / 2.4) - .055)
    pixels = np.uint8(np.rint(np.clip(value, 0, 1) * 255))
    pixels[~mask] = 0
    return pixels


def validate(arrays, mask):
    for key in ('structural', 'fine_candidates', 'structural_score', 'phase_score'):
        value = np.asarray(arrays[key])
        if value.shape != mask.shape or not np.isfinite(value).all():
            raise ValueError('Invalid tracing output frame: ' + key)
        if key in ('structural', 'fine_candidates') and value.dtype != bool:
            raise ValueError('Tracing boundary masks must be Boolean')
        if np.any(value[~mask]):
            raise ValueError('Tracing output extends beyond the foreground')
    if np.any((arrays['structural_score'] < 0) | (arrays['structural_score'] > 1)):
        raise ValueError('Structural scores must be probabilities')
    if np.any(arrays['fine_candidates'] & arrays['structural']):
        raise ValueError(
            'Fine candidates must be separate from structural boundaries')


def predict(linear, mask, requested=None):
    backend = identity(requested)
    if backend['selected'] == 'classical':
        return None, backend
    data = configuration()
    pixels = srgb_pixels(linear, mask)
    # Hash the actual worker input plus all numerical/model/code identities.
    key = hashlib.sha256(pixels.tobytes() + np.ascontiguousarray(mask).tobytes()
                         + str(mask.shape).encode() + json.dumps(backend, sort_keys=True).encode()).hexdigest()
    cache = Path(data['cache'])
    cache.mkdir(parents=True, exist_ok=True)
    packet = cache / (key + '.npz')
    receipt = packet.with_suffix('.json')
    if packet.is_file() and receipt.is_file():
        try:
            record = json.loads(receipt.read_text())
            if record['sha256'] != digest(packet):
                raise ValueError('Corrupt trace cache')
            with np.load(packet, allow_pickle=False) as saved:
                arrays = {k: saved[k].copy() for k in saved.files}
            validate(arrays, mask)
            return arrays, dict(backend, cache_hit=True, seconds=record['seconds'])
        except (OSError, ValueError, KeyError, EOFError, zipfile.BadZipFile):
            # Refitting is safer than trusting an incomplete/corrupt packet.
            pass
    with tempfile.TemporaryDirectory(prefix='trace-', dir=cache) as folder:
        folder = Path(folder)
        source, output = folder / 'input.npz', folder / 'output.npz'
        np.savez_compressed(source, pixels=pixels, mask=mask)
        environment = os.environ.copy()
        environment['PYTHONPATH'] = os.pathsep.join(data['python_paths'])
        environment['OMP_NUM_THREADS'] = '4'
        environment['OPENBLAS_NUM_THREADS'] = '1'
        command = [data['python'], str(Path(__file__).with_name('tracing_worker.py')),
                   '--config', str(configuration_path().resolve()), '--input', str(source), '--output', str(output)]
        process = subprocess.run(command, env=environment, capture_output=True, text=True,
                                 timeout=180, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if process.returncode or not output.is_file():
            raise RuntimeError(
                'Structural tracing worker failed: ' + process.stderr[-1500:])
        report = json.loads(process.stdout)
        if report['versions'] != data['versions']:
            raise ValueError(
                'Tracing runtime changed; rerun configure_tracing.py')
        with np.load(output, allow_pickle=False) as saved:
            arrays = {k: saved[k].copy() for k in saved.files}
        validate(arrays, mask)
        checksum = digest(output)
        os.replace(output, packet)
        temporary = folder / 'receipt.json'
        temporary.write_text(json.dumps(
            {'sha256': checksum, 'seconds': report['seconds']}))
        os.replace(temporary, receipt)
    return arrays, dict(backend, cache_hit=False, seconds=report['seconds'])
