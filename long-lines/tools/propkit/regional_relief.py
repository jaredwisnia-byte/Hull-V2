"""Local reference surfaces and held-out paint/recess/raised comparisons.

Regions propose computational patches, not physical parts. Geometry is fitted
with the existing spline solver; no dome, circle or channel template is selected.
"""
import numpy as np
from scipy import ndimage


def reference_surface(base, region, valid, tolerance=.5):
    """Robust quadratic reference from surrounding coarse-surface samples."""
    y, x = np.indices(base.shape)
    yy, xx = np.nonzero(region)
    if len(xx) < 16:
        return None, {'accepted': False, 'reason': 'insufficient region support'}
    radius = max(3, min(12, int(np.sqrt(len(xx)) * .15)))
    distance = ndimage.distance_transform_edt(~region)
    ring = (distance > 0) & (distance <= radius) & valid & np.isfinite(base)
    if ring.sum() < 18:
        return None, {'accepted': False, 'reason': 'insufficient surrounding reference samples'}
    scale = max(float(np.ptp(xx)), float(np.ptp(yy)), 4.)
    u, v = (x - xx.mean()) / scale, (y - yy.mean()) / scale
    design = np.stack([np.ones_like(u), u, v, u * u, u * v, v * v], axis=2)
    matrix, target = design[ring], base[ring]
    weight = np.ones(len(target))
    for _ in range(4):
        coef, _, rank, singular = np.linalg.lstsq(
            matrix * weight[:, None], target * weight, rcond=None)
        residual = matrix @ coef - target
        noise = max(.05, float(np.median(abs(residual))) * 1.4826)
        weight = np.sqrt(np.minimum(
            1., noise / np.maximum(abs(residual), 1e-8)))
    error = float(np.percentile(abs(residual), 95))
    accepted = rank == 6 and singular[0] / \
        max(singular[-1], 1e-12) < 1e5 and error <= tolerance
    result = base.copy()
    feather = np.clip(ndimage.distance_transform_edt(region) / 2, 0, 1)
    predicted = design @ coef
    result += feather * (predicted - base)
    return result, {'accepted': bool(accepted), 'ring_samples': int(ring.sum()), 'ring_error_p95_px': error,
                    'coefficients': coef.tolist(), 'origin_xy': [float(xx.mean()), float(yy.mean())],
                    'coordinate_scale_px': scale, 'basis': '1,u,v,u*u,u*v,v*v',
                    'units': 'analysis pixels', 'absolute_depth_validated': False}


def refine(base, initial, material, observed, validation_observed, lighting, labels, valid,
           training, validation, testing, bound, *, maximum_regions=24, envelope=True):
    """Choose on validation; accept on independent tests. Preserve deferred regions."""
    from .joint_shading import fit_height, shade
    from .spline_surface import Basis, control_shape
    result = initial.copy()
    result_material = material.copy()
    records = []
    identifiers = sorted(
        np.unique(labels[labels > 0]), key=lambda i: -np.count_nonzero(labels == i))
    solved = 0
    for identifier in identifiers:
        region = (labels == identifier) & valid
        if region.sum() < 36:
            continue
        y, x = np.nonzero(region)
        sl = (slice(max(0, y.min() - 14), min(base.shape[0], y.max() + 15)),
              slice(max(0, x.min() - 14), min(base.shape[1], x.max() + 15)))
        local = region[sl]
        train = training[sl] & local
        val = validation[sl] & local
        test = testing[sl] & local
        record = {'region_id': int(identifier), 'pixels': int(local.sum()),
                  'analysis_box_xy': [int(sl[1].start), int(sl[0].start), int(sl[1].stop), int(sl[0].stop)]}
        if solved >= maximum_regions or min(train.sum(), val.sum(), test.sum()) < 6:
            record.update(
                status='deferred', reason='compute budget or insufficient independent pixels')
            records.append(record)
            continue
        reference, reference_report = reference_surface(
            base[sl], local, valid[sl])
        record['reference'] = reference_report
        if not reference_report['accepted']:
            record['status'] = 'reference_unresolved'
            records.append(record)
            continue
        solved += 1
        coarse = base[sl]
        paint = material[sl]
        target = observed[sl]
        truth = validation_observed[sl]

        def evaluate(delta, fit=None):
            prediction = paint + np.log(shade(coarse + delta, lighting))
            exposure = float(
                np.clip(np.median((target - prediction)[train]), -.2, .2))
            prediction += exposure
            return {'height': delta, 'fit': fit, 'validation': float(np.mean((prediction[val] - truth[val])**2)),
                    'prediction': prediction, 'exposure': exposure}
        candidates = {'existing': evaluate(
            initial[sl]), 'material_only': evaluate(np.zeros(local.shape))}
        basis = Basis(local.shape, control_shape(local.shape, 8, maximum=24))
        for kind in ('recess', 'raised'):
            height, fit, _ = fit_height(reference, np.zeros(local.shape), basis, paint, target, train,
                                        lighting, local, bound, 70, bounds_mode=kind)
            delta = np.where(local, reference - coarse + height, initial[sl])
            if envelope:
                delta = np.minimum(delta, 0.)
            candidates[kind] = evaluate(delta, fit)
        winner = min(candidates, key=lambda key: candidates[key]['validation'])
        choice = candidates[winner]
        baseline = candidates['existing']
        baseline_test = float(
            np.mean((baseline['prediction'][test] - truth[test])**2))
        chosen_test = float(
            np.mean((choice['prediction'][test] - truth[test])**2))
        gain = 1 - chosen_test / max(baseline_test, 1e-12)
        converged = choice['fit'] is None or choice['fit']['converged']
        accepted = winner != 'existing' and gain > .05 and baseline_test > 1e-5 and converged
        if accepted:
            result[sl][local] = choice['height'][local]
            result_material[sl][local] = paint[local] + choice['exposure']
        record.update(status='accepted' if accepted else 'preserved_existing', winner=winner,
                      acceptance_validation_gain=float(gain), accepted=bool(accepted),
                      validation_errors={key: value['validation']
                                         for key, value in candidates.items()},
                      depth_sign_relative_to='estimated local reference; not absolute measurement')
        records.append(record)
    return result, result_material, {'method': 'surrounding-surface reference / continuous spline hypotheses / reserved validation pixels',
                                     'regions': records, 'solved_regions': solved, 'maximum_regions': maximum_regions,
                                     'accepted_regions': sum(r.get('accepted', False) for r in records),
                                     'cross_view_validated': False, 'absolute_depth_validated': False}
