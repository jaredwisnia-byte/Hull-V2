"""Windows path handling for diagnostic images saved inside Blender."""

import os
import unittest

from propkit.pathing import io_path


class IOPathContracts(unittest.TestCase):
    def test_short_path_is_unchanged(self):
        self.assertEqual(io_path('image.png'), 'image.png')

    @unittest.skipUnless(os.name == 'nt', 'Windows path contract')
    def test_long_absolute_path_uses_extended_prefix(self):
        path = os.path.join(os.getcwd(), 'nested', 'x' * 220 + '.png')
        self.assertGreaterEqual(len(path), 248)
        self.assertEqual(io_path(path), '\\\\?\\' + path)
        self.assertEqual(io_path(io_path(path)), io_path(path))


if __name__ == '__main__':
    unittest.main()
