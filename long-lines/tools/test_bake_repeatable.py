"""Rule R9 guard: the tangent-space normal map is baked in a single-threaded Blender.

Blender 5.2's MikkTSpace tangents vary between calls when computed in parallel; only the
command-line thread count (-t 1) makes them repeatable. Repeat typewriter builds differed in one
normal-map value until the normal bake moved to propkit/bake_normal_worker.py. This test keeps
the bake from silently returning to the multithreaded path. (Proving byte-identical builds needs
Blender and minutes per build; that check is the run's reproducibility gate.)
"""
import ast
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent


class NormalBakeIsRepeatable(unittest.TestCase):
    def test_finish_never_bakes_normals_in_process(self):
        tree = ast.parse((HERE / 'propkit/bake.py').read_text(encoding='utf-8'))
        finish = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'finish')
        for node in ast.walk(finish):
            if isinstance(node, ast.Call) and getattr(node.func, 'attr', '') == 'bake':
                kinds = [k.value.value for k in node.keywords
                         if k.arg == 'type' and isinstance(k.value, ast.Constant)]
                self.assertNotIn('NORMAL', kinds, 'normal bake must go through the single-thread worker')
        calls = [n for n in ast.walk(finish) if isinstance(n, ast.Call)
                 and getattr(n.func, 'id', '') == '_bake_normal_repeatable']
        self.assertTrue(calls)

    def test_worker_runs_single_threaded(self):
        source = (HERE / 'propkit/bake.py').read_text(encoding='utf-8')
        self.assertIn("'-t', '1'", source)
        self.assertTrue((HERE / 'propkit/bake_normal_worker.py').exists())


if __name__ == '__main__':
    unittest.main()
