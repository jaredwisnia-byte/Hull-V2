"""Windows path handling for diagnostic images saved inside Blender."""

import os
import unittest

from propkit.pathing import (BLENDER_WINDOWS_PATH_LIMIT,
                             check_blender_export_paths, io_path)


class IOPathContracts(unittest.TestCase):
    def test_short_path_is_unchanged(self):
        self.assertEqual(io_path('image.png'), 'image.png')

    @unittest.skipUnless(os.name == 'nt', 'Windows path contract')
    def test_long_absolute_path_uses_extended_prefix(self):
        path = os.path.join(os.getcwd(), 'nested', 'x' * 220 + '.png')
        self.assertGreaterEqual(len(path), 248)
        self.assertEqual(io_path(path), '\\\\?\\' + path)
        self.assertEqual(io_path(io_path(path)), io_path(path))

    def test_long_asset_name_fails_before_creating_output(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as folder:
            name = 'camera_' + 'x' * 150
            target = Path(folder) / name
            with self.assertRaisesRegex(ValueError, 'Shorten the run root or asset name') as error:
                check_blender_export_paths(folder, name, windows=True)
            self.assertIn(str(target), str(error.exception))
            self.assertFalse(target.exists())

    def test_nested_run_root_is_budgeted_with_repeated_asset_name(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / ('nested_' + 'a' * 70) / ('run_' + 'b' * 70) / 'attempt-001' / 'library'
            name = 'camera_' + 'c' * 40
            with self.assertRaises(ValueError) as error:
                check_blender_export_paths(root, name, windows=True)
            longest = root / name / (name + '_albedo.png')
            self.assertGreater(len(str(longest)), BLENDER_WINDOWS_PATH_LIMIT)
            self.assertIn(str(len(str(longest))), str(error.exception))

    def test_short_export_path_is_accepted(self):
        check_blender_export_paths('C:/hull/runs', 'camera', windows=True)


if __name__ == '__main__':
    unittest.main()
