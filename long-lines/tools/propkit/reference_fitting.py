"""Bounded reference retries, selected on reserved surrounding-surface samples."""
import numpy as np
from scipy import ndimage
from scipy.interpolate import RBFInterpolator


def fit(base, region, valid, tolerance=.5, hints=()):
    y, x = np.indices(base.shape)
    yy, xx = np.nonzero(region)
    if len(xx) < 16:
        return None, {'accepted': False, 'reason': 'insufficient region support', 'attempts': []}
    origin = np.array([xx.mean(), yy.mean()])
    scale = max(float(np.ptp(xx)), float(np.ptp(yy)), 4.)
    u, v = (x - origin[0]) / scale, (y - origin[1]) / scale
    coordinates = np.stack([u, v], axis=2)
    radius = max(3, min(12, int(np.sqrt(len(xx)) * .15)))
    distance = ndimage.distance_transform_edt(~region)
    fold = (x // 3 + 2 * (y // 3)) % 5
    plans = [(kind, multiple) for multiple in (1, 2, 3)
             for kind in ('plane', 'quadratic', 'thin_plate')]
    # Hints reorder work only. All strategies still face the same validation.
    preferred = [item['strategy'] for item in hints]
    plans.sort(key=lambda p: preferred.index(
        f'{p[0]}:{p[1]}') if f'{p[0]}:{p[1]}' in preferred else len(preferred))
    attempts = []
    best = None
    for kind, multiple in plans:
        ring = (distance > 0) & (distance <= radius *
                                 multiple) & valid & np.isfinite(base)
        train = ring & (fold != 0)
        check = ring & (fold == 0)
        record = {'strategy': f'{kind}:{multiple}', 'model': kind, 'ring_radius_px': radius * multiple,
                  'training_samples': int(train.sum()), 'validation_samples': int(check.sum())}
        if train.sum() < 18 or check.sum() < 6:
            attempts.append(dict(
                record, accepted=False, reason='insufficient independent surrounding samples'))
            continue
        try:
            if kind == 'thin_plate':
                xy, target = coordinates[train], base[train]
                pick = np.linspace(
                    0, len(xy) - 1, min(192, len(xy))).astype(int)
                model = RBFInterpolator(
                    xy[pick], target[pick], kernel='thin_plate_spline', smoothing=.005)
                predicted_check = model(coordinates[check])
                def prediction(points): return model(points)
                complexity = 10
                parameters = {}
            else:
                def design(points):
                    a, b = points.T
                    terms = [np.ones(len(a)), a, b]
                    return np.array(terms if kind == 'plane' else terms + [a * a, a * b, b * b]).T
                matrix, target = design(coordinates[train]), base[train]
                weight = np.ones(len(target))
                for _ in range(4):
                    coef, _, rank, singular = np.linalg.lstsq(
                        matrix * weight[:, None], target * weight, rcond=None)
                    residual = matrix @ coef - target
                    noise = max(.05, float(np.median(abs(residual))) * 1.4826)
                    weight = np.sqrt(np.minimum(
                        1., noise / np.maximum(abs(residual), 1e-8)))
                if rank != matrix.shape[1] or singular[0] / max(singular[-1], 1e-12) > 1e5:
                    raise ValueError('ill-conditioned surrounding geometry')
                predicted_check = design(coordinates[check]) @ coef
                def prediction(points): return design(points) @ coef
                complexity = len(coef)
                parameters = {'coefficients': coef.tolist()}
            error = float(np.percentile(
                abs(predicted_check - base[check]), 95))
            if error > tolerance:
                attempts.append(dict(record, accepted=False, ring_error_p95_px=error,
                                reason='reserved surrounding samples disagree'))
                continue
            predicted = prediction(coordinates[region])
            span = max(2., float(np.ptp(base[train])))
            bounded = np.isfinite(predicted).all() and predicted.min(
            ) >= base[train].min() - span and predicted.max() <= base[train].max() + span
            accepted = error <= tolerance and bounded
            record.update(accepted=bool(accepted),
                          ring_error_p95_px=error, **parameters)
            attempts.append(record)
            score = (error + complexity * .002, complexity, kind, multiple)
            if accepted and (best is None or score < best[0]):
                best = (score, predicted.copy(), record.copy())
        except (ValueError, np.linalg.LinAlgError) as error:
            attempts.append(dict(record, accepted=False, reason=str(error)))
    if best is None:
        return None, {'accepted': False, 'reason': 'reference strategies exhausted', 'attempts': attempts}
    result = base.copy()
    feather = np.clip(ndimage.distance_transform_edt(region) / 2, 0, 1)
    result[region] += feather[region] * (best[1] - base[region])
    report = dict(best[2], attempts=attempts, origin_xy=origin.tolist(), coordinate_scale_px=scale,
                  units='analysis pixels', absolute_depth_validated=False)
    return result, report
