"""Blender contracts and clay fixtures for object-independent implicit detail.

Run with Blender, optionally -- OUTPUT_DIRECTORY to keep the geometry renders.
The detector receives rendered test images, not annotated locations/counts.
"""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import bpy  # noqa: E402
import bmesh  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402
from skimage.measure import marching_cubes  # noqa: E402
from propkit import surface_detail, simplification, local_features, shading  # noqa: E402
from propkit.implicit import bounded_field, pad_field  # noqa: E402
from mathutils import Vector  # noqa: E402


def mesh_field(field, dimensions, name):
    step = np.asarray(dimensions) / field.shape
    vertices, faces, _, _ = marching_cubes(pad_field(field, dimensions), 0)
    vertices = (vertices - 1 + .5) * step + \
        [-dimensions[0] / 2, -dimensions[1] / 2, 0]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces[:, ::-1])
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(mesh)
    bm.free()
    bpy.context.view_layer.update()
    return obj


def sources(undulating=False):
    y, x = np.mgrid[:160, :200]
    if not undulating:
        center = 100 + 24 * np.sin(y / 30)
        height = -4 * np.exp(-.5 * ((x - center) / 7)**2) * \
            np.sin(np.pi * y / 159)**2
    else:
        # An arbitrary undulating terrain, not a classified primitive row.
        height = -3 * (1 + .6 * np.sin(x / 11) * np.cos(y / 17)) * \
            np.sin(np.pi * x / 199)**2 * np.sin(np.pi * y / 159)**2
    light = np.array([-.45, -.55, .8])
    light /= np.linalg.norm(light)
    linear = np.repeat(
        (.45 * shading.illumination(height, light))[..., None], 3, axis=2)
    value = np.where(linear <= .0031308, 12.92 * linear,
                     1.055 * linear**(1 / 2.4) - .055)
    return Image.fromarray(np.uint8(np.clip(value, 0, 1) * 255))


def plan_for(image, dimensions, undulating):
    mask = np.ones((image.height, image.width), bool)
    light = np.array([-.45, -.55, .8])
    light /= np.linalg.norm(light)
    depth, evidence = shading.reconstruct(
        image, mask, np.zeros(mask.shape), 8, light=light)
    assert evidence['accepted'], evidence
    report = {'features': []}
    surface_detail.curvature_probes(depth, mask, 'front', report)
    return {'dimensions': dimensions, 'maps': {'front': depth * dimensions[0] / image.width},
            'report': report}


def render(obj, path):
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    scene.cycles.samples = 16
    scene.cycles.use_denoising = False
    scene.render.resolution_x = scene.render.resolution_y = 640
    material = bpy.data.materials.new('clay')
    material.diffuse_color = (.55, .55, .55, 1)
    obj.data.materials.clear()
    obj.data.materials.append(material)
    for name, location, power in [('raking', (-.4, -.3, .4), 4), ('fill', (.4, -.2, .1), .4)]:
        light = bpy.data.lights.new(name, 'SUN')
        light.energy = power
        lamp = bpy.data.objects.new(name, light)
        scene.collection.objects.link(lamp)
        lamp.rotation_euler = (-Vector(location)
                               ).to_track_quat('-Z', 'Y').to_euler()
    camera = bpy.data.objects.new('camera', bpy.data.cameras.new('camera'))
    scene.collection.objects.link(camera)
    scene.camera = camera
    camera.data.type = 'ORTHO'
    camera.data.ortho_scale = .25
    target = Vector((0, 0, .09))
    camera.location = target + Vector((.12, -.45, .12))
    camera.rotation_euler = (
        target - camera.location).to_track_quat('-Z', 'Y').to_euler()
    world = bpy.data.worlds.new('world')
    world.use_nodes = True
    world.node_tree.nodes['Background'].inputs['Color'].default_value = (
        .2, .2, .2, 1)
    scene.world = world
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)


class SurfaceMeshContracts(unittest.TestCase):
    def setUp(self):
        bpy.ops.wm.read_factory_settings(use_empty=True)

    def case(self, organic=False, undulating=False):
        dimensions = (.2, .07, .18)
        shape = (100, 36, 90)
        axes = [(np.arange(n) + .5) / n * dimension for n,
                dimension in zip(shape, dimensions)]
        x, y, z = np.meshgrid(
            axes[0] - .1, axes[1] - .035, axes[2], indexing='ij')
        original = (np.sqrt((x / .095)**2 + (y / .033)**2 + ((z - .09) / .084)**2) - 1) * .033 if organic else \
            np.maximum.reduce([abs(x) - .1, abs(y) - .035, abs(z - .09) - .09])
        original = bounded_field(original, dimensions)
        plan = plan_for(sources(undulating), dimensions, undulating)
        self.assertGreater(len(plan['report']['features']), 0)
        result = surface_detail.apply_field(original, plan)
        obj = mesh_field(
            result, dimensions, 'organic' if organic else 'terrain' if undulating else 'machined')
        before = len(obj.data.polygons)
        self.assertEqual(local_features.geometry_components(
            [tuple(v.co) for v in obj.data.vertices], [tuple(p.vertices) for p in obj.data.polygons]), 1)
        protected = surface_detail.protected_samples(obj, plan['report'])
        triangles, error = simplification.decimate_to_error(
            obj, .0013, protected=protected)
        simplification.refresh_normals(obj, planar=True)
        check = local_features.check_surface_features([tuple(v.co) for v in obj.data.vertices],
                                                      [tuple(p.vertices) for p in obj.data.polygons], plan['report'])
        self.assertEqual(check['status'], 'pass', check)
        self.assertLess(triangles, before)
        self.assertLess(
            triangles, 2000, 'Simple local features must not retain the dense sampling grid')
        flat = mesh_field(original, dimensions, 'impostor')
        rejected = local_features.check_surface_features([tuple(v.co) for v in flat.data.vertices],
                                                         [tuple(p.vertices) for p in flat.data.polygons], plan['report'])
        self.assertEqual(rejected['status'], 'fail')
        bpy.data.objects.remove(flat, do_unlink=True)
        print('SURFACE_FIXTURE', obj.name, 'triangles', triangles,
              'probes', len(check['probes']), 'global_error_m', error)
        if OUTPUT:
            OUTPUT.mkdir(parents=True, exist_ok=True)
            render(obj, OUTPUT / (obj.name + '.png'))

    def test_machined_curved_groove(self): self.case()
    def test_organic_skin_uses_same_groove_path(self): self.case(organic=True)

    def test_continuous_topography_is_real_geometry(
        self): self.case(undulating=True)

    def test_dense_planar_box_budget_does_not_scale_with_source_grid(self):
        dimensions = (.2, .2, .2)
        field = bounded_field(np.full((100, 100, 100), -1.), dimensions)
        obj = mesh_field(field, dimensions, 'flat_box')
        triangles, error = simplification.decimate_to_error(
            obj, .0005, min_tris=24)
        self.assertLessEqual(triangles, 60)
        self.assertLessEqual(error, .0005)

    def test_uncalibrated_depth_stays_in_qa_without_freezing_reduction(self):
        bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, .5))
        obj = bpy.context.object
        bpy.ops.object.transform_apply(
            location=True, rotation=False, scale=False)
        probe = {'id': 'uncertain', 'view': 'front', 'kind': 'channel', 'axis': 1, 'outward': -1,
                 'anchors_m': [[0, -.5, .5], [-.1, -.5, .5], [.1, -.5, .5]],
                 'target_offsets_m': [-.01, 0, 0], 'tolerance_m': .001,
                 'depth_estimate': {'absolute_depth_supported_under_model': False}}
        report = {'probes': [probe]}
        self.assertIsNone(surface_detail.protected_samples(obj, report))
        self.assertEqual(report['probes'], [probe])
        self.assertTrue(report['depth_review_required'])
        self.assertEqual(report['unverified_depth_probes'], ['uncertain'])

    def test_complete_dense_source_tracks_translated_and_rotated_parts(self):
        from propkit.bake import combine_high_sources
        parts = []
        for name, location, rotation in [('body', (0, 0, 0), 0), ('lever', (3, 1, 2), np.pi / 2)]:
            bpy.ops.mesh.primitive_cube_add(size=1)
            obj = bpy.context.object
            obj.name = name
            surface_detail.capture_high(obj)
            obj.location = location
            obj.rotation_euler.z = rotation
            parts.append(obj)
        # Also cover a procedural part without a dense source of its own.
        bpy.ops.mesh.primitive_cube_add(size=.5, location=(-3, 0, 0))
        parts.append(bpy.context.object)
        bpy.context.view_layer.update()
        expected = np.array([tuple(p.matrix_world @ v.co)
                            for p in parts for v in p.data.vertices])
        source = combine_high_sources(parts, 'assembly')
        actual = np.array([tuple(source.matrix_world @ v.co)
                          for v in source.data.vertices])
        np.testing.assert_allclose(actual.min(0), expected.min(0), atol=1e-6)
        np.testing.assert_allclose(actual.max(0), expected.max(0), atol=1e-6)
        self.assertEqual(len(actual), len(expected))
        self.assertEqual(sum(o.name.endswith('__high')
                         for o in bpy.context.scene.objects), 1)


OUTPUT = Path(sys.argv[sys.argv.index('--') + 1]) if '--' in sys.argv else None
if __name__ == '__main__':
    unittest.main(argv=[sys.argv[0]])
