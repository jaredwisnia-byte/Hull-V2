"""Tracer provenance, fallback, cache recovery and connected-curve contracts.

No third-party weights are needed for these protocol tests. Actual neural output
is checked separately by the opt-in --integration run.
"""
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
from propkit import tracing_backend as backend, feature_curves, feature_regions


def packet(mask):
    return dict(structural=np.zeros_like(mask), fine_candidates=np.zeros_like(mask),
                structural_score=np.zeros(mask.shape), phase_score=np.zeros(mask.shape))


class BackendContracts(unittest.TestCase):
    def test_experimental_model_does_not_change_the_default(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(backend.identity()['selected'], 'classical')

    def test_missing_model_is_visible_fallback_but_strict_request_fails(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, HULL_TRACE_CONFIG=folder + '/absent.json'):
            self.assertEqual(backend.identity('auto')[
                             'reason'], 'model_not_configured')
            with self.assertRaises(backend.Unavailable):
                backend.identity('matched')

    def test_changed_artifacts_are_not_silently_accepted(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'config.json'
            artifact = Path(folder) / 'source.py'
            artifact.write_text('original')
            path.write_text(json.dumps(dict(schema=1, model_sha256=backend.MODEL_SHA256,
                                            artifact_hashes={str(artifact): backend.digest(artifact)})))
            artifact.write_text('changed')
            with patch.dict(os.environ, HULL_TRACE_CONFIG=str(path)), self.assertRaises(ValueError):
                backend.identity('auto')

    def test_neutral_background_does_not_modify_foreground(self):
        mask = np.zeros((12, 12), bool)
        mask[3:9, 3:9] = True
        rgb = np.full((12, 12, 3), .4)
        result = backend.srgb_pixels(rgb, mask)
        self.assertFalse(result[~mask].any())
        self.assertTrue((result[mask] == backend.srgb_pixels(
            rgb, np.ones_like(mask))[mask]).all())

    def test_byte_colour_roundtrip_does_not_dark_quantize_input(self):
        rgb = np.arange(256, dtype=float).reshape(16, 16) / 255
        linear = np.where(rgb <= .04045, rgb / 12.92,
                          ((rgb + .055) / 1.055)**2.4)
        result = backend.srgb_pixels(
            np.repeat(linear[..., None], 3, axis=2), np.ones(rgb.shape, bool))
        np.testing.assert_array_equal(
            result[..., 0], np.arange(256).reshape(16, 16))

    def test_diagnostic_export_preserves_new_layers_and_old_records(self):
        from PIL import Image
        from propkit import surface_detail
        mask = np.ones((30, 30), bool)
        traced = feature_regions.trace(
            np.full((30, 30, 3), .4), mask, backend='classical')
        arrays = {k: v for k, v in traced.items() if isinstance(v, np.ndarray)}
        values = dict(mask=mask, hypothesis_height_px=np.zeros(mask.shape),
                      feature_region_json=np.asarray(json.dumps({k: v for k, v in traced.items() if k not in arrays})))
        values.update({'feature_' + key: value for key,
                      value in arrays.items()})
        plan = dict(diagnostics={'front': values}, shading_inputs={
                    'front': {'image': Image.new('RGB', (30, 30))}}, report={})
        with tempfile.TemporaryDirectory() as folder:
            surface_detail.export_maps(plan, folder)
            with np.load(Path(folder) / 'front-feature-regions.npz') as saved:
                np.testing.assert_array_equal(
                    saved['fine_candidates'], traced['fine_candidates'])
            legacy = {k: v for k, v in traced.items() if k not in (
                'fine_candidates', 'structural_score', 'phase_score')}
            feature_regions.export(legacy, Image.new(
                'RGB', (30, 30)), folder, 'legacy')

    def test_packet_rejects_bad_frame_overlap_and_outside_pixels(self):
        mask = np.zeros((12, 12), bool)
        mask[2:-2, 2:-2] = True
        for change in ('outside', 'overlap', 'shape', 'score'):
            values = packet(mask)
            if change == 'outside':
                values['structural'][0, 0] = True
            if change == 'overlap':
                values['structural'][4, 4] = values['fine_candidates'][4, 4] = True
            if change == 'shape':
                values['phase_score'] = np.zeros((3, 3))
            if change == 'score':
                values['structural_score'][4, 4] = 2
            with self.assertRaises(ValueError):
                backend.validate(values, mask)

    def test_cache_is_reused_but_corruption_and_input_changes_refit(self):
        mask = np.ones((20, 20), bool)
        rgb = np.full((20, 20, 3), .4)
        with tempfile.TemporaryDirectory() as folder:
            config = dict(cache=folder, python='unused',
                          python_paths=[], versions={'test': '1'})

            def worker(command, **kwargs):
                np.savez_compressed(command[-1], **packet(mask))
                return SimpleNamespace(returncode=0, stdout=json.dumps(dict(versions=config['versions'], seconds=.1)), stderr='')
            with patch.object(backend, 'identity', return_value={'selected': 'matched_biped_2026'}), patch.object(backend, 'configuration', return_value=config), patch.object(backend.subprocess, 'run', side_effect=worker) as run:
                self.assertFalse(backend.predict(rgb, mask)[1]['cache_hit'])
                self.assertTrue(backend.predict(rgb, mask)[1]['cache_hit'])
                saved = next(Path(folder).glob('*.npz'))
                saved.write_bytes(b'broken')
                self.assertFalse(backend.predict(rgb, mask)[1]['cache_hit'])
                changed = rgb.copy()
                changed[5, 5] = .9
                self.assertFalse(backend.predict(
                    changed, mask)[1]['cache_hit'])
                self.assertEqual(run.call_count, 3)

    def test_fine_candidates_are_not_grouping_barriers(self):
        mask = np.ones((80, 80), bool)
        rgb = np.full((80, 80, 3), .4)
        values = packet(mask)
        values['structural'][15:65, 25] = True
        values['structural'][15:65, 55] = True
        with patch.object(backend, 'predict', return_value=(values, {'selected': 'test'})):
            baseline = feature_regions.trace(rgb, mask)
            values['fine_candidates'][20:60, 40] = True
            fine = feature_regions.trace(rgb, mask)
        np.testing.assert_array_equal(baseline['labels'], fine['labels'])
        self.assertTrue(fine['provisional_fine_paths'])
        self.assertFalse(fine['physical_parts_created'])


class CurveContracts(unittest.TestCase):
    def test_disconnected_paths_are_not_bridged(self):
        edges = np.zeros((80, 80), bool)
        edges[10:30, 20] = True
        edges[45:70, 20] = True
        result = feature_curves.trace(edges)
        self.assertEqual(len(result), 2)
        for curve in result:
            y = np.array(curve['points_xy'])[:, 1]
            self.assertTrue(y.max() < 31 or y.min() > 44)

    def test_u_curve_retains_horizontal_bottom_and_endpoints(self):
        points = np.array([[20, y] for y in range(10, 41)] +
                          [[x, 40] for x in range(21, 51)] +
                          [[50, y] for y in range(39, 9, -1)])
        curve = feature_curves.fit(points)
        sampled = np.array(curve['points_xy'])
        self.assertGreater(sampled[:, 1].max(), 39)
        np.testing.assert_allclose(sampled[[0, -1]], points[[0, -1]], atol=.01)
        if curve['representation'] == 'cubic_B_spline':
            self.assertLessEqual(curve['sampled_max_deviation_px'], .75)


if __name__ == '__main__':
    unittest.main()
