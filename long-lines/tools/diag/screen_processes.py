"""Screen image-only construction routes over a folder of orthographic view sets.

Run this before changing routing thresholds. It records every candidate decision,
including ordinary field fallback, rather than counting only a specialist tool.
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from propkit.process_planner import plan_methods, propose


def screen(root):
    cases = {}
    for front in sorted(root.rglob('v_front.png')):
        folder = front.parent
        views = {name: str(folder / f'v_{name}.png')
                 for name in ('front', 'back', 'left', 'right', 'top', 'bottom')
                 if (folder / f'v_{name}.png').is_file()}
        if not ({'left', 'right'} & set(views)):
            continue
        methods, _ = plan_methods(views)
        _, profile = propose(views, 1.0)
        cases[str(folder.relative_to(root)).replace('\\', '/')] = {
            'method': methods, 'profile': profile}
    methods = Counter(case['method']['method'] for case in cases.values())
    return {'case_count': len(cases), 'methods': dict(sorted(methods.items())),
            'profile_candidates': sum(case['profile']['choice'] == 'profile_shaft_candidate'
                                      for case in cases.values()),
            'cases': cases}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = screen(args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False))
    print(json.dumps({key: report[key] for key in
                      ('case_count', 'methods', 'profile_candidates')}))


if __name__ == '__main__':
    main()
