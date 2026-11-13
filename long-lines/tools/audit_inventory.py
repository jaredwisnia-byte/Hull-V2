"""Regenerate the static code/documentation inventory. Requires Git; never imports builders.

Run: python long-lines/tools/audit_inventory.py
Output: long-lines/docs/CODEBASE_INVENTORY.json (tracked files plus Python tools).
"""
import ast
import hashlib
import json
import re
import subprocess
from pathlib import Path
from collections import Counter
from datetime import date
root = Path(__file__).resolve().parents[2]


def git(*args): return subprocess.check_output(
    ['git', *args], cwd=root, text=True, encoding='utf-8')


tracked = git('ls-files').splitlines()
extensions = Counter(Path(p).suffix.lower() for p in tracked)
sources = set(p for p in tracked if Path(p).suffix.lower() in ('.py', '.gd', '.js', '.mjs',
              '.ts', '.md', '.json', '.yml', '.yaml', '.html', '.css'))
sources.update(p.relative_to(root).as_posix() for p in (
    root / 'long-lines/tools').rglob('*.py') if '__pycache__' not in str(p))
sources.discard('long-lines/docs/CODEBASE_INVENTORY.json')  # Exclude this generated output.
entries = []
errors = []
for path in sorted(sources):
    p = root / path
    if not p.is_file():
        continue
    data = p.read_bytes()
    text = data.decode('utf-8-sig', errors='replace')
    entry = {'path': path, 'lines': len(
        text.splitlines()), 'sha256': hashlib.sha256(data).hexdigest()}
    suffix = p.suffix.lower()
    if suffix == '.py':
        try:
            tree = ast.parse(text)
            entry['description'] = ast.get_docstring(tree) or ''
            entry['imports'] = sorted({ast.unparse(n) for n in ast.walk(
                tree) if isinstance(n, (ast.Import, ast.ImportFrom))})
            entry['definitions'] = [{'name': n.name, 'line': n.lineno, 'kind': type(n).__name__,
                                     'description': ast.get_docstring(n) or ''} for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
            entry['calls'] = sorted(
                {ast.unparse(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)})
            entry['environment_keys'] = sorted(
                set(re.findall(r'(?:getenv|environ.get)\([\"\x27]([^\"\x27]+)', text)))
        except SyntaxError as e:
            errors.append({'path': path, 'error': str(e)})
    elif suffix == '.gd':
        entry['class_names'] = re.findall(r'^class_name\s+(\w+)', text, re.M)
        entry['extends'] = re.findall(r'^extends\s+(.+)', text, re.M)
        entry['functions'] = re.findall(
            r'^(?:static\s+)?func\s+(\w+)', text, re.M)
        entry['description'] = '\n'.join(line for line in text.splitlines()[
                                         :12] if line.startswith('#'))
    elif suffix == '.md':
        entry['headings'] = re.findall(r'^#{1,4}\s+(.+)', text, re.M)
    elif suffix == '.json':
        try:
            obj = json.loads(text)
            entry['root_type'] = type(obj).__name__
            entry['item_count'] = len(obj) if isinstance(
                obj, (list, dict)) else None
            entry['keys'] = list(obj)[:60] if isinstance(obj, dict) else []
        except (ValueError, TypeError) as e:
            errors.append({'path': path, 'error': str(e)})
    else:
        entry['definitions'] = re.findall(
            r'^(?:export\s+)?(?:async\s+)?function\s+(\w+)|^class\s+(\w+)', text, re.M)
    entries.append(entry)
result = {'audit_date': date.today().isoformat(), 'method': 'Static parse and catalog; not proof of runtime correctness',
          'local_head': git('rev-parse', 'HEAD').strip(), 'canonical_dirac': '9d8df082dfbef7d5a508be3578d78d7c488561ab',
          'tracked_files': len(tracked), 'tracked_extensions': dict(extensions),
          'catalogued_files': len(entries), 'python_files': sum(e['path'].endswith('.py') for e in entries),
          'parse_errors': errors, 'files': entries}
out = root / 'long-lines/docs/CODEBASE_INVENTORY.json'
out.write_text(json.dumps(result, indent=2,
               ensure_ascii=False) + '\n', encoding='utf-8')
summary = []
for e in entries:
    if e['path'].endswith('.py'):
        summary.append(e['path'] + ' | ' + e.get('description', '').split('\n')
                       [0] + ' | ' + ', '.join(d['name'] for d in e.get('definitions', [])))

print(json.dumps({k: v for k, v in result.items() if k != 'files'}, indent=2))
