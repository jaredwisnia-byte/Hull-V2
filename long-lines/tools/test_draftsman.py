"""The draftsman stage (propkit/draftsman.py): registered texture maps."""
import unittest

import numpy as np

from propkit import draftsman as dm


class TextureMaps(unittest.TestCase):
    def test_reference_views_map_to_themselves(self):
        class F:
            regs = {'x': None, 'z': None}
        res = {'frames': {'front': F()}}
        maps = dm.texture_maps(res)
        xs, ns = maps['front']['x']
        self.assertTrue(np.allclose(xs, ns))


if __name__ == '__main__':
    unittest.main()


if __name__ == "__main__":
    unittest.main()
