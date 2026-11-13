"""Inspect local reconstruction experience; rerunning a build resumes deferred patches."""
import argparse
import json
from pathlib import Path
from contextlib import closing
from propkit.build_memory import BuildMemory


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, default=Path(
        __file__).resolve().parents[2] / '.hull-memory' / 'reconstruction.sqlite3')
    args = parser.parse_args()
    if not args.database.is_file():
        print(json.dumps({'path': str(args.database),
              'status': 'no memory recorded yet'}))
        return
    with closing(BuildMemory(args.database)) as memory:
        print(json.dumps(memory.summary(), indent=2))


if __name__ == '__main__':
    main()
