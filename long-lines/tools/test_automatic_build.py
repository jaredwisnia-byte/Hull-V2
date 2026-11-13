"""Run under Blender; optional -- RESULT.json verifies a complete real run."""
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sheet_blobs  # noqa: E402
import factory  # noqa: E402


class BuildGuards(unittest.TestCase):
    def test_single_body_constructor_consumes_prebuild_drawing_masks(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for view in ('front', 'right'):
                pixels = np.zeros((80, 80, 3), np.uint8)
                pixels[10:70, 16:64] = 150
                Image.fromarray(pixels).save(root / f'v_{view}.png')
            order = {'name': 'drawing_contract_probe', 'line': 'hull',
                     'views_folder': str(root), 'views': ['front', 'right'],
                     'height_m': .2, 'hull': {'relief': True},
                     'automatic_depth': True, 'run_directory': str(root / 'run'),
                     'measured': {}}
            from propkit import process_planner, surface_detail
            with patch.object(factory, 'SRC', str(root)), \
                    patch.object(process_planner, 'plan_methods',
                                 return_value=({'method': 'continuous_field'}, None)), \
                    patch.object(process_planner, 'propose',
                                 return_value=(None, {})), \
                    patch.object(surface_detail, 'analyse', return_value={}), \
                    patch('propkit.hull.hull_prop', return_value=object()) as builder:
                factory.run_line(order)
            supplied = builder.call_args.kwargs['sil_override']
            drawing = order['measured']['source_drawing']
            receipt = drawing['construction_receipt']
            self.assertEqual(set(supplied), {'front', 'right'})
            self.assertEqual(receipt['status'], 'supplied_to_hull_constructor')
            self.assertTrue(Path(drawing['section_envelopes']).is_file())
            self.assertEqual(hashlib.sha256(Path(
                drawing['construction_contract']).read_bytes()).hexdigest(),
                receipt['drawing_sha256'])
            evolving = Path(drawing['traces'])
            evolving.write_text(evolving.read_text() + '\n')
            self.assertEqual(hashlib.sha256(Path(
                drawing['construction_contract']).read_bytes()).hexdigest(),
                receipt['drawing_sha256'])
            self.assertEqual(drawing['opening_candidates'], [])
            for view in supplied:
                self.assertTrue(receipt['views'][view]['build_trace_ids'])
                self.assertTrue(supplied[view][0].any())

    def test_handbook_parts_receive_prebuild_drawings(self):
        from propkit import handbook
        order_path = (Path(__file__).resolve().parents[1] / 'factory' /
                      'orders' / 'wallphone_rotary.json')
        order = json.loads(order_path.read_text())
        order['measured'] = {}
        with tempfile.TemporaryDirectory() as folder:
            order['run_directory'] = folder
            with patch('propkit.hull_assembly.build', return_value={'parts': {}}):
                factory.run_line(order)
            expected = {spec['views'] for spec in
                        handbook.entry(order['handbook'])['assembly']
                        if spec.get('views')}
            self.assertTrue(expected <= set(order['construction_drawings']))
            self.assertTrue(expected <= set(
                order['measured']['source_drawing']['part_drawings']))

    def test_part_geometry_receives_compiled_drawing_mask(self):
        from propkit import parts_layout
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            pixels = np.zeros((90, 90, 3), np.uint8)
            pixels[15:75, 20:70] = 140
            for view in ('front', 'right'):
                Image.fromarray(pixels).save(root / f'v_{view}.png')
            views = {view: str(root / f'v_{view}.png')
                     for view in ('front', 'right')}
            from propkit.drawing_traces import infer, load_construction_masks
            infer(views, root / 'drawing', compile_construction_masks=True)
            masks, _ = load_construction_masks(
                root / 'drawing' / 'technical-traces.json', views)
            with patch.object(parts_layout, 'hull_prop', return_value=object()) as builder:
                parts_layout.build_part(views, .1, .1, .2, 'generic_part', str(root),
                                        cut_holes=False, defer=[], drawing_masks=masks)
            self.assertIs(builder.call_args.kwargs['sil_override']['front'][0],
                          masks['front'][0])
            from propkit import surface_detail
            drawing_path = root / 'drawing' / 'technical-traces.json'
            with patch.object(parts_layout, 'hull_prop', return_value=object()), \
                    patch.object(surface_detail, 'analyse', return_value={}) as analyse:
                parts_layout.build_part(views, .1, .1, .2, 'generic_detail', str(root),
                                        cut_holes=False, defer=[], automatic_depth=True,
                                        drawing_masks=masks, drawing_path=drawing_path)
            self.assertEqual(analyse.call_args.kwargs['drawing_path'], drawing_path)

    def test_parts_line_draws_supplied_views_before_geometry(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in ('assembly', 'body'):
                part = root / 'source' / name
                part.mkdir(parents=True)
                pixels = np.full((90, 90, 3), 255, np.uint8)
                pixels[15:75, 20:70] = 10
                Image.fromarray(pixels).save(part / 'v_front.png')
            order = {'line': 'hull_parts', 'layout': 'parts', 'name': 'test',
                     'views_folder': 'source', 'assembly': 'assembly',
                     'parts': [{'name': 'body', 'views': 'body', 'root': True}],
                     'run_directory': str(root / 'run')}
            def build(candidate, unused_root):
                drawing = candidate['measured']['source_drawing']
                self.assertEqual(drawing['stage'], 'before_geometry')
                self.assertTrue(Path(drawing['traces']).is_file())
                self.assertIn('body', drawing['part_drawings'])
                from propkit.drawing_traces import load_construction_masks
                masks, use = load_construction_masks(
                    candidate['construction_drawings']['body'],
                    {'front': str(root / 'source' / 'body' / 'v_front.png')})
                self.assertTrue(masks['front'][0].any())
                self.assertTrue(use['front']['build_trace_ids'])
                return {'parts': {'body': {}}}
            with patch.object(factory, 'SRC', str(root)), \
                    patch('propkit.hull_assembly.build', side_effect=build):
                factory.run_line(order)
            self.assertIn('parts', order['measured'])
            self.assertIn('source_drawing', order['measured'])

    def test_station_exception_is_saved_as_a_reviewable_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'input.png'
            source.write_bytes(b'input')
            destination = Path(folder) / 'output'
            with patch.object(sheet_blobs, 'automatic', side_effect=ValueError('bad source views')):
                result = factory.automatic_build(source, destination)
            self.assertEqual(result['status'], 'needs_review')
            self.assertIn('bad source views', result['pipeline_failure'])
            self.assertTrue((destination / 'result.json').is_file())
            self.assertTrue(Path(result['error_log']).is_file())

    def test_assembly_references_are_compared_for_parts_orders(self):
        order = {'layout': 'parts',
                 'views_folder': 'example', 'assembly': 'whole'}
        self.assertEqual(factory.reference_views(order),
                         os.path.join(factory.SRC, 'example', 'whole'))
        self.assertEqual(factory.reference_views(
            {'views_folder': 'example'}), os.path.join(factory.SRC, 'example'))
        self.assertIsNone(factory.reference_views({}))

    def test_failed_build_does_not_package_previous_model(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            image = root/'image.png'
            image.write_bytes(b'input')
            order = root/'order.json'
            order.write_text(json.dumps({'name': 'old', 'assumptions': []}))
            old = root/'old'/'old.glb'
            old.parent.mkdir()
            old.write_bytes(b'old model')
            os.utime(old, (1, 1))
            report = {'status': 'ready_to_build', 'work_order': str(order)}
            with patch.object(sheet_blobs, 'automatic', return_value=report), \
                    patch.object(factory, 'LIB', str(root)), \
            patch.object(factory, 'build', return_value={'pass': False, 'fails': ['manufacturing failed'], 'metrics': {}}), \
                    patch.object(factory.bake, 'export_textured') as export:
                result = factory.automatic_build(image, root/'output')
            export.assert_not_called()
            self.assertEqual(result['status'], 'needs_review')
            self.assertNotIn('model', result)

    def test_unresolved_generic_parts_prevent_complete_status(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            image = root/'image.png'
            image.write_bytes(b'input')
            order = root/'order.json'
            order.write_text(json.dumps({
                'name': 'body_only', 'assumptions': [],
                'unresolved_component_regions': [7, 8]}))
            report = {'status': 'ready_to_build', 'work_order': str(order)}
            with patch.object(sheet_blobs, 'automatic', return_value=report), \
                    patch.object(factory, 'LIB', str(root)), \
                    patch.object(factory, 'build', return_value={
                        'pass': True, 'fails': [], 'metrics': {}}):
                result = factory.automatic_build(image, root/'output')
            self.assertIn('unresolved_companion_parts', result['inference_warnings'])
            self.assertEqual(result['status'], 'needs_review')


def artifact_acceptance(path):
    result = json.loads(path.read_text())
    expected_status = 'needs_review' if result.get(
        'inference_warnings') else 'complete'
    assert result['status'] == expected_status and result['qa']['pass'], result
    assert not result['runtime_llm']
    assert hashlib.sha256(
        Path(result['input_image']).read_bytes()).hexdigest() == result['input_sha256']
    metrics = result['qa']['metrics']
    assert {'front', 'back', 'left', 'right',
            'top'} <= set(metrics['silhouette_iou'])
    assert metrics['normal_disagreement'] == 0
    for key in ('model', 'blend', 'render'):
        assert Path(result[key]).is_file(), key
    raw = Path(result['model']).read_bytes()
    assert raw[:4] == b'glTF'
    size = struct.unpack('<I', raw[12:16])[0]
    document = json.loads(raw[20:20+size])
    triangles = sum(document['accessors'][p['indices']]['count']//3
                    for mesh in document['meshes'] for p in mesh['primitives'])
    assert triangles == metrics['tris'], (triangles, metrics['tris'])
    assert len(document.get('images', [])) >= 3
    assert all('bufferView' in im for im in document['images'])
    order = json.loads(
        (path.parent/'intake/manufacture/work-order.json').read_text())
    measured = factory.load_order(order['name'])['measured']
    assert len(measured['gaps_mm']) == len(order['parts'])-1
    assert all(g['gap_mm'] is not None and g['gap_mm'] <=
               4 and g['touching'] >= .4 for g in measured['gaps_mm'])
    # A complete artifact must be rejected if its reference comparisons disappear.
    with tempfile.TemporaryDirectory() as empty:
        missing = factory.qa.check(
            order['name'], empty, order['class'], trim_order=order)
    assert not missing['pass']
    assert any('reference comparison missing' in f for f in missing['fails'])
    print('ARTIFACT ACCEPTANCE PASS:', triangles,
          'triangles, embedded maps, all attachments, five reference comparisons')


if __name__ == '__main__':
    args = sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(BuildGuards)
    passed = unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful()
    if passed and args:
        artifact_acceptance(Path(args[0]).resolve())
    sys.exit(0 if passed else 1)
