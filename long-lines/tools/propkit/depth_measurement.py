"""Metric curvature-contrast estimates with explicit calibration uncertainty."""
import numpy as np
from scipy import ndimage


def estimate(height_px, points_xy, metres_per_pixel, evidence, scale_status='estimated'):
    points = np.asarray(points_xy, float)
    if points.ndim != 2 or points.shape[1] != 2 or len(points) < 3:
        raise ValueError(
            'A centre and at least two surrounding surface samples are required')
    if not np.isfinite(metres_per_pixel) or metres_per_pixel <= 0:
        raise ValueError('Positive physical pixel scale required')
    values = ndimage.map_coordinates(np.asarray(
        height_px, float), points[:, ::-1].T, order=1, mode='nearest')
    contrast = float((values[0] - np.mean(values[1:])) * metres_per_pixel)
    information = evidence.get('depth_information', {})
    interval = information.get(
        'scale_interval_95_conditional', [0., float('inf')])
    metric_interval = sorted(
        [contrast * float(interval[0]), contrast * float(interval[1])])
    calibrated = scale_status == 'calibrated' and information.get(
        'data_only_identifiable', False)
    return {'signed_contrast_m': contrast, 'depth_m': abs(contrast),
            'signed_interval_m_conditional': metric_interval,
            'calibrated_inputs': bool(calibrated),
            'absolute_depth_supported_under_model': bool(calibrated),
            'absolute_depth_validated': False,
            'status': 'calibrated_model_estimate' if calibrated else 'conditional_estimate_not_absolute_measurement',
            'physical_scale_status': scale_status,
            'assumptions': information.get('assumptions', 'lighting/material/scale are not independently calibrated')}
