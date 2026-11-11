"""Real Blender mesh/UV/export regressions for physical and texel ownership."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import bpy  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402
from propkit import ownership, pixel_bake  # noqa: E402


class OwnershipContracts(unittest.TestCase):
    def test_different_names_cannot_hide_duplicate_geometry(self):
        parts = []
        for name in ('handle', 'second_handle'):
            bpy.ops.mesh.primitive_cube_add()
            parts.append(bpy.context.object)
            parts[-1].name = name
        with self.assertRaisesRegex(ValueError, 'Duplicate geometry'):
            ownership.tag_parts(parts)

    def test_local_gate_detects_missing_channel_on_matching_silhouette(self):
        from propkit.local_features import check_channels
        angles = np.linspace(0, 2 * np.pi, 129)[:-1]
        vertices = np.array([[np.cos(a) * .1, np.sin(a) * .1, z]
                            for z in (0, 1) for a in angles])
        faces = [(i, (i + 1) % 128, (i + 1) % 128 + 128, i + 128)
                 for i in range(128)]
        construction = {'height_m': 1, 'band': [0, 1],
                        'spline_profile': {'stations': 24, 'radius_samples_m': [[.1] * 24, [.1] * 24],
                                           'center_samples_m': [[0] * 24, [0] * 24]},
                        'features': [{'id': 'groove', 'angle': 0, 'depth_fraction': .03, 'uncertain': False}]}
        result = check_channels(vertices, faces, construction)
        self.assertEqual(result['status'], 'fail')
        vertices[[0, 128], 0] -= .006
        result = check_channels(vertices, faces, construction)
        self.assertEqual(result['status'], 'pass')

    def setUp(self):
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete(use_global=False)

    def test_standalone_round_trip_restores_named_parts(self):
        parts = []
        for name, x in [('capital', 0), ('shaft', 2)]:
            bpy.ops.mesh.primitive_cube_add(size=1, location=(x, 0, 0))
            part = bpy.context.object
            part.name = name
            part['physical_region_id'] = name
            parts.append(part)
        owners = ownership.tag_parts(parts)
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.join()
        obj = bpy.context.object
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            document = ownership.save_mesh_ownership(
                obj, owners, folder / 'parts.json')
            bpy.ops.export_scene.gltf(filepath=str(
                folder / 'test.glb'), export_format='GLB', use_selection=True)
            bpy.ops.object.delete(use_global=False)
            bpy.ops.import_scene.gltf(filepath=str(folder / 'test.glb'))
            obj = next(o for o in bpy.context.scene.objects if o.type == 'MESH')
            restored = ownership.split_standalone(obj, document)
            self.assertEqual({p['physical_part_id']
                             for p in restored}, set(owners))
            self.assertEqual(sum(len(p.data.polygons) for p in restored), 24)

    def test_child_pixels_cannot_be_painted_on_occluded_body(self):
        mesh = bpy.data.meshes.new('assembly')
        mesh.from_pydata([(-.5, 0, 0), (.5, 0, 0), (.5, 0, 1), (-.5, 0, 1),
                          (-.2, -.1, .3), (.2, -.1, .3), (.2, -.1, .7), (-.2, -.1, .7)], [],
                         [(0, 1, 2, 3), (4, 5, 6, 7)])
        obj = bpy.data.objects.new('assembly', mesh)
        bpy.context.scene.collection.objects.link(obj)
        attribute = mesh.attributes.new('hull_owner', 'INT', 'FACE')
        attribute.data[0].value = 0
        attribute.data[1].value = 1
        atlas = mesh.uv_layers.new()
        for index, point in enumerate([(0, 0), (1, 0), (1, 1), (0, 1), (.05, .05), (.2, .05), (.2, .2), (.05, .2)]):
            atlas.data[index].uv = point
        material = bpy.data.materials.new('projected')
        mesh.materials.append(material)
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            source = np.full((64, 64, 3), 240, np.uint8)
            source[19:45, 19:45] = [240, 0, 0]
            Image.fromarray(source).save(folder / 'front.png')
            output = folder / 'test_albedo.png'
            Image.new('RGB', (64, 64), (90, 90, 90)).save(output)
            sources = {material.name: {'world_to_source': np.eye(4), 'views': {'front': str(folder / 'front.png')},
                                       'dimensions': (1, 1, 1)}}
            report = pixel_bake.refine_albedo(obj, sources, output)
            result = np.asarray(Image.open(output))
            self.assertGreater(result[32, 32].min(), 200)
            self.assertGreater(
                report['unseen_pixels_filled_from_same_owner'], 0)
            self.assertGreater(result[8, 32].mean(), 200)


if __name__ == '__main__':
    unittest.main(argv=[sys.argv[0]])
