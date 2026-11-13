"""Reproject independently fitted surface regions between orthographic views."""
import numpy as np
from scipy import ndimage


def project(points, view, dimensions):
    from .surface_detail import chart_frame
    origin, u, v, normal = map(np.asarray, chart_frame(view, dimensions))
    relative = np.asarray(points) - origin
    return np.c_[relative @ u / (u @ u), relative @ v / (v @ v)], relative @ normal


def compare(charts, dimensions, samples=48):
    from .surface_detail import chart_frame
    records = []
    active = {view: data for view,
              data in charts.items() if data.get('accepted', False)}
    for view, data in active.items():
        origin, u, v, normal = map(np.asarray, chart_frame(view, dimensions))
        hh, ww = data['labels'].shape
        for identifier in np.unique(data['labels'][data['labels'] > 0]):
            yy, xx = np.nonzero((data['labels'] == identifier) & data['mask'])
            if not len(xx):
                continue
            pick = np.linspace(
                0, len(xx) - 1, min(samples, len(xx))).astype(int)
            yy, xx = yy[pick], xx[pick]
            depth = data['height'][yy, xx] - data['root'][yy, xx]
            points = origin + (xx[:, None] + .5) / ww * u + \
                (yy[:, None] + .5) / hh * v + depth[:, None] * normal
            matches = []
            for other, target in active.items():
                if other == view:
                    continue
                _, _, _, target_normal = map(
                    np.asarray, chart_frame(other, dimensions))
                if normal @ target_normal < -.5:
                    continue
                uv, predicted = project(points, other, dimensions)
                th, tw = target['labels'].shape
                coords = np.array([uv[:, 1] * th - .5, uv[:, 0] * tw - .5])
                inside = (uv >= 0).all(1) & (uv <= 1).all(1)
                observed = ndimage.map_coordinates(
                    target['height'] - target['root'], coords, order=1, mode='constant', cval=np.nan)
                owners = ndimage.map_coordinates(
                    target['labels'], coords, order=0, mode='constant', cval=0)
                visible = ndimage.map_coordinates(target['mask'].astype(
                    float), coords, order=0, mode='constant', cval=0) > .5
                tolerance = max(data['pixel_m'], target['pixel_m']) * 2
                for owner in np.unique(owners[owners > 0]):
                    keep = inside & visible & (owners == owner)
                    errors = abs(predicted[keep] - observed[keep])
                    support = int(np.count_nonzero(errors <= tolerance))
                    if support >= 3 and support / len(xx) >= .25:
                        matches.append({'view': other, 'region_id': int(owner), 'support_samples': support,
                                        'median_depth_error_m': float(np.median(errors)), 'tolerance_m': float(tolerance)})
            records.append({'view': view, 'region_id': int(
                identifier), 'matches': matches})
    supported = []
    for record in records:
        reciprocal = [match for match in record['matches'] if any(
            r['view'] == match['view'] and r['region_id'] == match['region_id'] and any(
                m['view'] == record['view'] and m['region_id'] == record['region_id'] for m in r['matches']) for r in records)]
        supported.append(dict(record, matches=reciprocal,
                         status='reciprocal_surface_support' if reciprocal else 'unresolved'))
    return {'regions': supported, 'supported_regions': sum(bool(r['matches']) for r in supported),
            'needs_review': not supported or any(not r['matches'] for r in supported),
            'method': 'independent surface-depth reprojection and reciprocal region support',
            'camera_model': 'supplied orthographic charts; no general perspective calibration',
            'absolute_depth_validated': False}
