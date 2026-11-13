"""Review the structured evidence behind a factory slideshow; no LLM needed."""
import argparse
import json
from pathlib import Path
from propkit import stage_review


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('result', type=Path)
    parser.add_argument('--order', type=Path)
    parser.add_argument('--diagnostics', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    data = json.loads(args.result.read_text())
    order = json.loads(args.order.read_text()) if args.order else {}
    report = stage_review.inspect(data.get('qa', data), data.get(
        'measured', order.get('measured', {})), args.diagnostics)
    stage_review.write(report, args.output)
    print(json.dumps({'status': report['status'], 'findings': len(
        report['findings']), 'output': str(args.output)}))


if __name__ == '__main__':
    main()
