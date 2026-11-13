"""Measured drafting stations must retain source contours and uncertainty."""
import unittest
import tempfile
import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image

from propkit.drawing_traces import (_elevation_section, _end_frame_hypotheses,
                                    _verified_build_to_source_map,
                                    audit_projected_elevations, infer,
                                    infer_sheet_regions, load_construction_masks,
                                    compile_relief_trace, load_relief_trace,
                                    observe)


class SourceSectionContracts(unittest.TestCase):
    def test_compiled_drawing_mask_drives_construction_and_rejects_stale_input(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'front.png'
            pixels = np.zeros((80, 80, 3), np.uint8)
            pixels[10:70, 20:60] = 180
            Image.fromarray(pixels).save(source)
            report = infer({'front': str(source)}, Path(folder) / 'drawing',
                           compile_construction_masks=True)
            masks, use = load_construction_masks(
                Path(folder) / 'drawing' / 'technical-traces.json',
                {'front': str(source)})
            self.assertEqual(masks['front'][0].shape, (60, 40))
            self.assertTrue(masks['front'][0].all())
            valid = masks['front'][0].copy()
            valid[:3] = False
            compiled = compile_relief_trace(
                Path(folder) / 'drawing' / 'technical-traces.json',
                'front', str(source), masks['front'][0], valid,
                masks['front'][1])
            loaded = load_relief_trace(
                Path(folder) / 'drawing' / 'technical-traces.json',
                'front', str(source), masks['front'][0], valid)
            packet = json.loads((Path(folder) / 'drawing' /
                                 'technical-traces.json').read_text())[
                                     'compiled_construction_masks']['front']['relief_trace']
            self.assertTrue(Path(packet['overlay']).is_file())
            self.assertTrue(np.array_equal(compiled['boundaries'],
                                           loaded['boundaries']))
            with self.assertRaisesRegex(ValueError, 'valid region differs'):
                load_relief_trace(
                    Path(folder) / 'drawing' / 'technical-traces.json',
                    'front', str(source), masks['front'][0],
                    masks['front'][0])
            tiny = np.zeros_like(valid)
            tiny[10:12, 10:12] = True
            self.assertIsNone(compile_relief_trace(
                Path(folder) / 'drawing' / 'technical-traces.json',
                'front', str(source), masks['front'][0], tiny,
                masks['front'][1]))
            self.assertEqual(use['front']['build_trace_ids'],
                             [trace['id'] for trace in
                              report['observations']['front']['traces']
                              if trace['kind'] == 'outer_silhouette'])
            original = Path(folder) / 'original.png'
            Image.fromarray(pixels).save(original)
            infer({'front': str(source)}, Path(folder) / 'reconciled',
                  source_views={'front': str(original)},
                  compile_construction_masks=True)
            _, changed_use = load_construction_masks(
                Path(folder) / 'reconciled' / 'technical-traces.json',
                {'front': str(source)})
            self.assertTrue(all(trace_id.startswith('build_input:') for trace_id
                                in changed_use['front']['build_trace_ids']))
            self.assertFalse(changed_use['front']['source_pixel_map_verified'])
            pixels[25, 25] = 90
            Image.fromarray(pixels).save(source)
            with self.assertRaisesRegex(ValueError, 'changed after technical tracing'):
                load_construction_masks(
                    Path(folder) / 'drawing' / 'technical-traces.json',
                    {'front': str(source)})

    def test_original_sheet_crops_keep_absolute_pixel_provenance(self):
        with tempfile.TemporaryDirectory() as folder:
            sheet = Path(folder) / 'sheet.png'
            pixels = np.full((60, 200, 3), 255, np.uint8)
            for left in (0, 70, 140):
                pixels[15:45, left + 12:left + 42] = 10
            Image.fromarray(pixels).save(sheet)
            regions = [{'id': index, 'box': box} for index, box in enumerate(
                ([0, 0, 60, 60], [70, 0, 130, 60], [140, 0, 200, 60]))]
            records = {'assembly': {'views': {'front': 0, 'right': 1}},
                       'component': {'views': {'front': 2, 'right': 2}}}
            drawings = infer_sheet_regions(sheet, records, regions,
                                           Path(folder) / 'drawings')
            assembly = json.loads(Path(drawings['assembly']['traces']).read_text())
            front = assembly['observations']['front']
            self.assertEqual(front['foreground_box_px'], [12, 15, 42, 45])
            self.assertEqual(front['source_sheet_frame']['sheet_xy_from_crop_xy']
                             ['offset_xy'], [0, 0])
            right = assembly['observations']['right']
            self.assertEqual(right['traces'][0]['source_sheet_frame']
                             ['sheet_xy_from_crop_xy']['offset_xy'], [70, 0])
            component = json.loads(
                Path(drawings['component']['traces']).read_text())
            self.assertEqual(component['source_region_reused_for_multiple_view_labels'],
                             [2])
            self.assertEqual(component['paired_elevation_envelopes'], [])
            self.assertEqual(component['unresolved_view_pairs_same_source_region'],
                             [['front', 'right']])
            self.assertEqual(component['observations']['front']['source_sheet_frame']
                             ['view_assignment'], 'automatic_companion_view_hypothesis')

    def test_sheet_dimensions_come_from_source_pixels(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'front.png'
            pixels = np.full((100, 120, 3), 255, np.uint8)
            pixels[15:85, 20:95] = 10
            Image.fromarray(pixels).save(source)
            record = observe('front', source)
        self.assertEqual(record['foreground_box_px'], [20, 15, 95, 85])
        self.assertEqual(record['observed_bbox_dimensions']['width_source_px'], 75)
        self.assertEqual(record['observed_bbox_dimensions']['height_source_px'], 70)
        self.assertEqual(record['observed_bbox_dimensions']['source_trace_ids'],
                         ['front:outer:0'])
        self.assertIn('physical scale unknown',
                      record['observed_bbox_dimensions']['units'])

    def test_rectangle_uses_the_two_contour_crossings(self):
        contour = [[2., 1.], [12., 1.], [12., 21.],
                   [2., 21.], [2., 1.]]
        section = _elevation_section([contour], 11., .5)
        self.assertEqual(section['outer_envelope_x_source_px'], [2., 12.])
        self.assertEqual({p['source_trace_id'] for p in section['crossings']},
                         {'outer:0'})
        self.assertTrue(section['crossing_parity_valid'])
        self.assertEqual(section['physical_cross_section_shape'], 'unobserved')

    def test_nonconvex_outline_preserves_all_crossings(self):
        # At this height the source has two separated lobes. A fitted ellipse
        # would erase that gap; the drawing records all four observed edges.
        contour = [[0., 0.], [10., 0.], [10., 20.], [7., 20.],
                   [7., 5.], [3., 5.], [3., 20.], [0., 20.], [0., 0.]]
        section = _elevation_section([contour], 10., .5)
        self.assertEqual([p['x_source_px'] for p in section['crossings']],
                         [0., 3., 7., 10.])
        self.assertEqual(section['outer_envelope_x_source_px'], [0., 10.])
        self.assertTrue(section['crossing_parity_valid'])

    def test_open_or_missing_contour_is_not_called_a_physical_section(self):
        section = _elevation_section([[[0., 0.], [0., 20.]]], 10., .5)
        self.assertIsNone(section['outer_envelope_x_source_px'])
        self.assertFalse(section['crossing_parity_valid'])
        self.assertEqual(section['physical_cross_section_shape'], 'unobserved')

    def test_odd_crossings_do_not_produce_a_measured_envelope(self):
        lines = [[[x, 0.], [x, 20.]] for x in (0., 5., 10.)]
        section = _elevation_section(lines, 10., .5)
        self.assertEqual(len(section['crossings']), 3)
        self.assertIsNone(section['outer_envelope_x_source_px'])
        self.assertFalse(section['crossing_parity_valid'])

    def test_preflight_conflict_is_distinct_from_actual_construction_use(self):
        def observed(view, path, *unused):
            return {'source_size_px': [20, 20], 'foreground_box_px': [2, 2, 18, 18],
                    'observed_elevation_sections': [], 'traces': [],
                    'outer_path_count': 0, 'internal_path_count': 0,
                    'opposed_mask_opening_count': 0}

        with tempfile.TemporaryDirectory() as folder, patch(
                'propkit.drawing_traces.observe', side_effect=observed):
            views = {'front': 'front.png', 'top': 'top.png'}
            preflight = {'paint_only': ['top'], 'views': {'top': {'off_pct': 184.1}}}
            used = infer(views, Path(folder) / 'used',
                         view_consistency=preflight, geometry_views=views)
            held = infer(views, Path(folder) / 'held',
                         view_consistency=preflight, geometry_views={'front': 'front.png'})
        self.assertEqual(used['view_conflicts_in_use'], ['top'])
        self.assertEqual(used['view_construction_use']['top']['preflight_proportion_off_pct'],
                         184.1)
        self.assertFalse(held['view_conflicts_in_use'])
        self.assertFalse(held['view_construction_use']['top']['used_for_geometry'])

    def test_end_frame_evidence_does_not_choose_a_rotation(self):
        observations = {'front': {'foreground_box_px': [0, 0, 40, 100]},
                        'right': {'foreground_box_px': [0, 0, 80, 100]},
                        'top': {'foreground_box_px': [0, 0, 100, 50]}}
        top = _end_frame_hypotheses(observations)['top']
        self.assertAlmostEqual(top['axis_residual_log']['90_or_270_degrees'], 0)
        self.assertGreater(top['axis_residual_log']['0_or_180_degrees'], 1)
        self.assertIn('unresolved', top['status'])
        self.assertEqual(top['construction_use'], 'diagnostic_only')

    def test_reconciled_build_pixels_do_not_masquerade_as_original_traces(self):
        def observed(view, path, *unused):
            opening = 'build' in str(path)
            return {'source_path': str(path), 'source_size_px': [20, 20],
                    'foreground_box_px': [2, 2, 18, 18],
                    'observed_elevation_sections': [],
                    'traces': ([{'id': 'front:opening:1', 'kind': 'opposed_mask_opening',
                                'cross_view_witness': 'back', 'area_source_px': 12,
                                'appearance_median_rgb': [0, 0, 0],
                                'appearance_std_rgb': [0, 0, 0]}] if opening else []),
                    'outer_path_count': 0, 'internal_path_count': 0,
                    'opposed_mask_opening_count': int(opening)}

        with tempfile.TemporaryDirectory() as folder, patch(
                'propkit.drawing_traces.observe', side_effect=observed), patch(
                'propkit.drawing_traces._verified_build_to_source_map', return_value=None):
            report = infer({'front': 'build.png'}, folder,
                           source_views={'front': 'original.png'})
        self.assertEqual(report['observations']['front']['source_path'], 'original.png')
        self.assertEqual(report['reconciled_build_input_observations']['front']['source_path'],
                         'build.png')
        self.assertEqual(report['reconciled_views_without_source_pixel_map'], ['front'])
        candidate = report['build_constraints'][0]
        self.assertIsNone(candidate['source_trace_id'])
        self.assertEqual(candidate['build_input_trace_id'], 'build_input:front:opening:1')
        self.assertIsNone(candidate['area_source_px'])
        self.assertEqual(candidate['area_build_input_px'], 12)

    def test_verified_flip_maps_contour_centers_back_to_original_pixels(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'source.png'
            built = Path(folder) / 'built.png'
            pixels = np.arange(3 * 4 * 3, dtype=np.uint8).reshape(3, 4, 3)
            Image.fromarray(pixels).save(source)
            Image.fromarray(pixels[:, ::-1]).save(built)
            frame = {'source_size_px': [4, 3],
                     'build_to_source_xy': {'scale_xy': [-1, 1],
                                            'offset_xy': [3, 0]},
                     'appearance_modifications': []}
            self.assertEqual(_verified_build_to_source_map(source, built, frame),
                             frame['build_to_source_xy'])
            def observed(view, path, *unused):
                is_build = str(path) == str(built)
                return {'source_path': str(path), 'source_size_px': [4, 3],
                        'foreground_box_px': [0, 0, 4, 3],
                        'observed_elevation_sections': [],
                        'traces': ([{'id': 'front:opening:1',
                                    'kind': 'opposed_mask_opening',
                                    'points_source_xy': [[0, 0], [1, 1]],
                                    'cross_view_witness': 'back',
                                    'area_source_px': 2,
                                    'appearance_median_rgb': [0, 0, 0],
                                    'appearance_std_rgb': [0, 0, 0]}]
                                   if is_build else []),
                        'outer_path_count': 0, 'internal_path_count': 0,
                        'opposed_mask_opening_count': int(is_build)}
            with patch('propkit.drawing_traces.observe', side_effect=observed):
                report = infer({'front': str(built)}, Path(folder) / 'sheet',
                               source_views={'front': str(source)},
                               view_consistency={'pixel_frames': {'front': frame}})
            self.assertEqual(report['reconciled_views_with_verified_source_pixel_map'],
                             ['front'])
            self.assertFalse(report['reconciled_views_without_source_pixel_map'])
            self.assertEqual(report['build_constraints'][0]['mapped_original_source_xy'],
                             [[3, 0], [2, 1]])
            frame['appearance_modifications'] = [{'kind': 'background_erasure'}]
            self.assertIsNone(_verified_build_to_source_map(source, built, frame))

    def test_lossless_flip_maps_build_opening_candidate_to_original_frame(self):
        def observed(view, path, *unused):
            build = str(path).endswith('built.png')
            return {'source_path': str(path), 'source_size_px': [4, 3],
                    'foreground_box_px': [0, 0, 4, 3],
                    'observed_elevation_sections': [],
                    'traces': ([{'id': 'front:opening:1', 'kind': 'opposed_mask_opening',
                                'cross_view_witness': 'back', 'area_source_px': 2,
                                'points_source_xy': [[0.5, 1.0], [1.5, 1.0]],
                                'appearance_median_rgb': [0, 0, 0],
                                'appearance_std_rgb': [0, 0, 0]}] if build else []),
                    'outer_path_count': 0, 'internal_path_count': 0,
                    'opposed_mask_opening_count': int(build)}

        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'source.png'
            built = Path(folder) / 'built.png'
            pixels = np.arange(3 * 4 * 3, dtype=np.uint8).reshape(3, 4, 3)
            Image.fromarray(pixels).save(source)
            Image.fromarray(pixels[:, ::-1]).save(built)
            frame = {'source_size_px': [4, 3],
                     'build_to_source_xy': {'scale_xy': [-1, 1],
                                            'offset_xy': [3, 0]},
                     'appearance_modifications': []}
            with patch('propkit.drawing_traces.observe', side_effect=observed):
                report = infer({'front': str(built)}, Path(folder) / 'report',
                               source_views={'front': str(source)},
                               view_consistency={'pixel_frames': {'front': frame}})
        self.assertEqual(report['reconciled_views_without_source_pixel_map'], [])
        self.assertEqual(report['reconciled_views_with_verified_source_pixel_map'],
                         ['front'])
        self.assertEqual(report['reconciliation_pixel_frames']['front'], frame)
        self.assertEqual(report['build_constraints'][0]['mapped_original_source_xy'],
                         [[2.5, 1.0], [1.5, 1.0]])

    def test_export_audit_compares_measured_sections_not_global_overlap(self):
        sections = [{
            'height_fraction_from_top': fraction,
            'outer_envelope_x_source_px': [25., 75.],
            'crossing_parity_valid': True,
            'crossings': [{'source_trace_id': 'front:outer:0'}],
        } for fraction in (.25, .5, .75)]
        drawing = {'observations': {'front': {
            'foreground_box_px': [0, 0, 100, 100],
            'observed_elevation_sections': sections}},
            'view_construction_use': {'front': {'used_for_geometry': True}}}
        matched = np.zeros((100, 100), bool)
        matched[:, 25:75] = True
        narrower = np.zeros_like(matched)
        narrower[:, 35:65] = True
        good = audit_projected_elevations(drawing, {'front': matched}, [1, 1, 1])
        bad = audit_projected_elevations(drawing, {'front': narrower}, [1, 1, 1])
        self.assertEqual(good['views']['front']['outside_tolerance_count'], 0)
        self.assertEqual(bad['views']['front']['outside_tolerance_count'], 3)
        self.assertEqual(bad['views']['front']['severe_outlier_count'], 3)
        self.assertEqual(bad['views']['front']['samples'][0]['source_trace_ids'],
                         ['front:outer:0'])
        drawing['reconciled_views_without_source_pixel_map'] = ['front']
        unresolved = audit_projected_elevations(drawing, {'front': narrower}, [1, 1, 1])
        self.assertEqual(unresolved['status'], 'no_comparable_elevation_views')


if __name__ == '__main__':
    unittest.main()
