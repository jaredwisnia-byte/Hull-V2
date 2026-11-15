"""Windows path handling for diagnostic images saved inside Blender."""

import ntpath
import os
import unittest
from unittest.mock import patch

from propkit.pathing import (BLENDER_WINDOWS_PATH_LIMIT,
                             _windows_code_units, check_blender_export_paths,
                             io_path)


class IOPathContracts(unittest.TestCase):
    def test_short_path_is_unchanged(self):
        self.assertEqual(io_path('image.png'), 'image.png')

    def test_non_windows_path_is_unchanged(self):
        path = '/hull/' + 'x' * 300 + '.png'
        self.assertEqual(io_path(path, windows=False), path)

    def test_long_absolute_path_uses_extended_prefix(self):
        path = ntpath.join('C:\\hull', 'nested', 'x' * 240 + '.png')
        self.assertGreaterEqual(len(path), 248)
        extended = io_path(path, windows=True)
        self.assertEqual(extended, '\\\\?\\' + path)
        self.assertEqual(io_path(extended, windows=True), extended)
        unc = '\\\\server\\share\\' + 'y' * 250 + '.png'
        self.assertEqual(io_path(unc, windows=True), '\\\\?\\UNC\\' + unc[2:])

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

    def test_non_bmp_characters_consume_two_windows_path_units(self):
        symbol = chr(0x1F4F7)
        self.assertEqual(_windows_code_units('A' + symbol), 3)
        name = symbol * 100
        target = os.path.abspath(os.path.join('C:/hull', name,
                                              name + '_albedo.png'))
        if os.name == 'nt':
            self.assertLess(len(target), BLENDER_WINDOWS_PATH_LIMIT)
        with self.assertRaisesRegex(ValueError, 'UTF-16 code units') as error:
            check_blender_export_paths('C:/hull', name, windows=True)
        self.assertIn(str(_windows_code_units(target)), str(error.exception))

    def test_non_bmp_python_io_path_uses_extended_prefix(self):
        path = ntpath.join('C:\\hull', chr(0x1F4F7) * 130)
        self.assertLess(len(path), 248)
        self.assertGreaterEqual(_windows_code_units(path), 248)
        self.assertTrue(io_path(path, windows=True).startswith('\\\\?\\'))

    def test_short_relative_name_under_long_root_uses_extended_prefix(self):
        absolute = ntpath.normpath(ntpath.join('C:\\', 'x' * 240, 'image.png'))
        self.assertGreaterEqual(_windows_code_units(absolute), 248)
        with patch('propkit.pathing.ntpath.abspath', return_value=absolute):
            self.assertEqual(io_path('image.png', windows=True), '\\\\?\\' + absolute)


if __name__ == '__main__':
    unittest.main()
