"""Blender integration: clipping an inspection copy cannot mutate the asset."""
import sys
from pathlib import Path
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bpy  # noqa: E402
from propkit.cutaway import export_surface_cutaway  # noqa: E402
from propkit.sectioning import CuttingPlane  # noqa: E402

bpy.ops.mesh.primitive_cube_add()
source = bpy.context.object
coordinates = tuple(tuple(vertex.co) for vertex in source.data.vertices)
original_objects = set(bpy.context.scene.objects)
with tempfile.TemporaryDirectory() as folder:
    output = Path(folder) / 'cutaway.glb'
    export_surface_cutaway([source], CuttingPlane((0,0,0),(1,0,0)), output)
    assert tuple(tuple(vertex.co) for vertex in source.data.vertices) == coordinates
    assert set(bpy.context.scene.objects) == original_objects
    assert source.select_get()
    bpy.ops.import_scene.gltf(filepath=str(output))
    imported = set(bpy.context.scene.objects) - original_objects
    assert imported
    assert all(vertex.co.x <= 1e-6 for obj in imported for vertex in obj.data.vertices)
print('CUTAWAY TEST PASS: clipped half-space, source data and selection preserved')
