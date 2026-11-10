"""Blender integration regressions: contour ridges, placement, identity, budgets, atlas export."""
import json
import os
import sys
import tempfile
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
from propkit import core, mats
from propkit.hull import polygon_hull
from propkit.components.pipeline import build
from propkit.components.export import exported_triangles
from propkit.components.placement import place
from propkit.components import validate_manifest

directory = Path(tempfile.mkdtemp(prefix="hull-components-test-"))
front = np.ones((100, 100), dtype=bool)
side = np.zeros((100, 80), dtype=bool)
for row in range(100):
    side[row, 3 + row % 3:76 - row % 3] = True
core.reset()
mats.reset()
body = polygon_hull({"front": front, "right": side}, 1, .5, 1, tolerance=4, bevel_frac=0)
tree = BVHTree.FromPolygons([v.co for v in body.data.vertices], [p.vertices for p in body.data.polygons])
samples = [(z, tree.ray_cast(Vector((.2, 1, z)), Vector((0, -1, 0)), 2)[0].y) for z in np.linspace(.15, .85, 60)]
a = np.array(samples)
residual = np.max(np.abs(a[:, 1] - np.polyval(np.polyfit(a[:, 0], a[:, 1], 1), a[:, 0])))
assert residual < .00005, ("striped flat panel", residual)

# Real export with a non-first named attachment parent and a separate hierarchy.
sheet = Image.new("RGB", (240, 100), "white")
draw = ImageDraw.Draw(sheet)
draw.rectangle((8, 8, 90, 90), fill=(80, 90, 100))
draw.rectangle((108, 8, 190, 90), fill=(100, 80, 60))
sheet.save(directory / "sheet.png")
part = {"name": "housing", "method": "polygon", "reference": "sheet.png", "dimensions": [.2, .1, .2],
        "position": [.4, 0, 0], "budget": 100, "bevel_fraction": 0,
        "views": {"front": [0, 0, 100, 100], "right": [100, 0, 200, 100]}}
child = {**part, "name": "button", "dimensions": [.02, .02, .02], "position": [.4, 0, 0], "budget": 100,
         "attachment": {"parent": "housing", "face": "top", "overlap": .001}, "parent": "housing"}
cfg = {"name": "fixture", "texture": 128, "triangle_limit": 300, "pad_paint": True,
       "prototypes": {"control": child},
       "parts": [{"name": "button", "prototype": "control"},
                 {"name": "button_b", "prototype": "control", "position": [.44, 0, 0]}, part]}
path = directory / "manifest.json"
path.write_text(json.dumps(cfg))
result = build(path, directory / "out")
assert set(result["components"]) == {"housing", "button", "button_b"}
assert next(p for p in result["parts"] if p["name"] == "button_b")["reused_prototype"] == "control"
assert bpy.data.objects["button"].data is not bpy.data.objects["button_b"].data
assert bpy.data.objects["button"].parent == bpy.data.objects["housing"]
bpy.context.view_layer.update()
h = bpy.data.objects["housing"]
c = bpy.data.objects["button"]
parent_points = [h.matrix_world @ v.co for v in h.data.vertices]
parent_tree = BVHTree.FromPolygons(parent_points, [p.vertices for p in h.data.polygons])
child_points = [c.matrix_world @ v.co for v in c.data.vertices]
cx = (min(v.x for v in child_points) + max(v.x for v in child_points)) / 2
cy = (min(v.y for v in child_points) + max(v.y for v in child_points)) / 2
top = parent_tree.ray_cast(Vector((cx, cy, 1)), Vector((0, 0, -1)), 2)[0].z
bottom = min((c.matrix_world @ v.co).z for v in c.data.vertices)
assert abs(top - bottom - .001) < .00001, ("floating attachment", top, bottom)
assert result["exported_triangles"] == exported_triangles(directory / "out" / "fixture" / "fixture.glb")
assert result["exported_triangles"] <= 300
assert (directory / "out" / "fixture" / "fixture.blend").exists()
import factory
core.reset()
mats.reset()
order = {"name": "fixture", "line": "components", "manifest": str(path)}
factory.run_line(order)
assert order["measured"]["geometry_triangles"] <= 300
assert len(core.PARTS) == 3
print("COMPONENT INTEGRATION PASS", directory)
