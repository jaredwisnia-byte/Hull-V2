"""Run with Blender: shared simplification must reduce geometry within its bound."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import bpy
from propkit.simplification import decimate_to_error, refresh_normals, screen_tolerance
import json

standards = json.loads((Path(__file__).resolve().parents[1] /
                        'factory/standards.json').read_text())
assert screen_tolerance(standards, 'static', 4.0) > screen_tolerance(
    standards, 'static', 1.0)

bpy.ops.mesh.primitive_uv_sphere_add(segments=64, ring_count=32)
obj = bpy.context.object
before = sum(len(face.vertices)-2 for face in obj.data.polygons)
count, error = decimate_to_error(obj, .005)
refresh_normals(obj)
assert count < before, (count, before)
assert 0 < error <= .005, error
assert all(len(face.vertices) >= 3 for face in obj.data.polygons)
print('SIMPLIFICATION PASS:', before, '->', count, 'triangles; measured error', error)
