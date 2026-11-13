"""Native displacement contract, separated from pure numerical inference tests."""

import sys
from pathlib import Path
import unittest
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))


class DisplacementTests(unittest.TestCase):
    def test_selected_signed_depth_changes_geometry_and_obeys_cap(self):
        import bpy
        from propkit import relief
        from unittest.mock import patch

        with patch.object(
            relief, "shared_light", return_value=np.array([-0.7, -0.7])
        ), patch.object(relief, "view_relief", return_value=(np.zeros((16, 16)), {})):
            for sign in (-1, 1):
                mesh = bpy.data.meshes.new("test")
                mesh.from_pydata(
                    [(-0.5, 0, 0), (0.5, 0, 0), (0.5, 0, 1), (-0.5, 0, 1)],
                    [],
                    [(0, 1, 2, 3)],
                )
                obj = bpy.data.objects.new("test", mesh)
                bpy.context.scene.collection.objects.link(obj)
                report = {}
                hook = relief.hook(
                    {"front": "unused"},
                    1,
                    1,
                    1,
                    report,
                    maps_override={"front": np.full((16, 16), sign * 20.0)},
                    keep_high=False,
                    cap_share=0.02,
                )
                hook(obj)
                self.assertTrue(
                    all(abs(v.co.y + sign * 0.02) < 1e-6 for v in mesh.vertices)
                )
                bpy.data.objects.remove(obj, do_unlink=True)


if __name__ == "__main__":
    unittest.main(argv=["depth_displacement"], exit=True)
