"""Register the verified local MatchED-BIPED runtime once, for all future assets.

Third-party source and weights are local artifacts, never committed to Hull.
See factory/TRACING.md for the published download locations and setup example.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from propkit.tracing_backend import MODEL_SHA256, SOURCE_SHA256, digest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python', type=Path, required=True)
    parser.add_argument('--python-path', type=Path,
                        action='append', default=[])
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--checkpoint', type=Path, required=True)
    parser.add_argument('--config', type=Path, default=Path(
        __file__).resolve().parents[2] / '.hull-models/tracing.json')
    args = parser.parse_args()
    for filename, expected in SOURCE_SHA256.items():
        if digest(args.source / filename) != expected:
            raise ValueError(
                'Expected the verified official MatchED source: ' + filename)
    if digest(args.checkpoint) != MODEL_SHA256:
        raise ValueError('Expected the published MatchED BIPED checkpoint')
    environment = os.environ.copy()
    paths = [str(p.resolve()) for p in args.python_path]
    environment['PYTHONPATH'] = os.pathsep.join(paths)
    worker = Path(__file__).parent / 'propkit/tracing_worker.py'
    process = subprocess.run([str(args.python.resolve()), str(worker), '--describe'], env=environment,
                             capture_output=True, text=True,
                             creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if process.returncode:
        raise RuntimeError(
            'Cannot inspect tracing runtime: ' + process.stderr[-1500:])
    runtime = json.loads(process.stdout)
    config_path = args.config.resolve()
    artifacts = config_path.parent / 'matched-biped-2026'
    source = artifacts / 'source'
    for filename in SOURCE_SHA256:
        target = source / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(args.source / filename, target)
    checkpoint = artifacts / 'biped.pth'
    shutil.copyfile(args.checkpoint, checkpoint)
    hashes = {str(source / filename): expected for filename,
              expected in SOURCE_SHA256.items()}
    hashes[str(checkpoint)] = MODEL_SHA256
    hashes.update({filename: digest(filename)
                  for filename in runtime['metadata'].values()})
    configuration = {'schema': 1, 'python': str(args.python.resolve()), 'python_paths': paths,
                     'source': str(source), 'checkpoint': str(checkpoint), 'model_sha256': MODEL_SHA256,
                     'versions': runtime['versions'], 'artifact_hashes': hashes,
                     'cache': str(config_path.parent / 'trace-cache'),
                     'source_commit': 'cf12ad80d0a9f7088964741226a15a0475d37a2d',
                     'physical_geometry_verified': False}
    config_path.write_text(json.dumps(configuration, indent=2))
    print(json.dumps({'configured': str(config_path), 'backend': 'matched_biped_2026',
                      'runtime_llm': False, 'versions': runtime['versions']}))


if __name__ == '__main__':
    main()
