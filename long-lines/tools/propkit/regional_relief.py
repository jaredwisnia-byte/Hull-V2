"""Local reference surfaces and held-out paint/recess/raised comparisons.

Regions propose computational patches, not physical parts. Geometry is fitted
with the existing spline solver; no dome, circle or channel template is selected.
"""
import numpy as np
from scipy import ndimage


def reference_surface(base, region, valid, tolerance=.5, hints=()):
    """Try bounded reference models without treating extrapolation as depth truth."""
    from .reference_fitting import fit
    return fit(base, region, valid, tolerance, hints)


def _refine(base, initial, material, observed, validation_observed, lighting, labels, valid,
            training, validation, testing, bound, *, maximum_regions=24, envelope=True, memory=None):
    """Choose on validation; accept on independent tests. Preserve deferred regions."""
    from .joint_shading import fit_height, shade
    from .spline_surface import Basis, control_shape
    result = initial.copy()
    result_material = material.copy()
    records = []
    identifiers = sorted(
        np.unique(labels[labels > 0]), key=lambda i: -np.count_nonzero(labels == i))
    from .build_memory import fingerprint, solver_version
    version = solver_version() if memory is not None else None
    solved = processed = cache_hits = 0
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
        descriptor = [float(np.log1p(local.sum()) / 10), float(np.log(local.shape[1] / local.shape[0])),
                      float(np.std(base[sl][local]) / max(bound, 1e-6))]
        key = fingerprint(version, base[sl], initial[sl], material[sl], np.where(train, observed[sl], 0),
                          np.where(val | test, validation_observed[sl], 0), lighting, local, valid[sl], train, val, test, float(bound), envelope)
        record['memory_key'] = key

        def save():
            if memory is not None:
                memory.save(key, version, record, descriptor,
                            result[sl], result_material[sl])
        if memory is not None:
            cached = memory.load(key, version)
            if cached is not None:
                cached_height, cached_material, cached_record = cached
                result[sl][local] = cached_height[local]
                result_material[sl][local] = cached_material[local]
                records.append(dict(cached_record, resumed=True, region_id=int(
                    identifier), analysis_box_xy=record['analysis_box_xy']))
                cache_hits += 1
                continue
        if processed >= maximum_regions or min(train.sum(), val.sum(), test.sum()) < 6:
            record.update(
                status='deferred' if processed >= maximum_regions else 'insufficient_evidence',
                reason='compute budget exhausted' if processed >= maximum_regions else 'insufficient independent pixels')
            records.append(record)
            save()
            continue
        processed += 1
        hints = memory.suggest(
            descriptor, version) if memory is not None else []
        record['strategy_hints'] = hints
        reference, reference_report = reference_surface(
            base[sl], local, valid[sl], hints=hints)
        record['reference'] = reference_report
        if not reference_report['accepted']:
            record['status'] = 'reference_unresolved'
            records.append(record)
            save()
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
        fit_attempts = []
        for kind in ('recess', 'raised'):
            warm = np.zeros(local.shape)
            for spacing, controls, iterations in ((8, 24, 70), (4, 32, 140)):
                basis = Basis(local.shape, control_shape(
                    local.shape, spacing, maximum=controls))
                height, fit, _ = fit_height(
                    reference, warm, basis, paint, target, train, lighting, local, bound, iterations, bounds_mode=kind)
                warm = height
                delta = np.where(local, reference -
                                 coarse + height, initial[sl])
                if envelope:
                    delta = np.minimum(delta, 0.)
                candidate = evaluate(delta, fit)
                fit_attempts.append(
                    dict(kind=kind, validation_error=candidate['validation'], **fit))
                if kind not in candidates or candidate['validation'] < candidates[kind]['validation']:
                    candidates[kind] = candidate
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
        record.update(status='accepted' if accepted else 'preserved_existing', winner=winner, fit_attempts=fit_attempts,
                      acceptance_validation_gain=float(gain), accepted=bool(accepted),
                      validation_errors={key: value['validation']
                                         for key, value in candidates.items()},
                      depth_sign_relative_to='estimated local reference; not absolute measurement')
        records.append(record)
        save()
    return result, result_material, {'method': 'surrounding-surface reference / continuous spline hypotheses / reserved validation pixels',
                                     'regions': records, 'solved_regions': solved, 'maximum_regions': maximum_regions,
                                     'new_regions_processed': processed, 'resumed_regions': cache_hits,
                                     'accepted_regions': sum(r.get('accepted', False) for r in records),
                                     'cross_view_validated': False, 'absolute_depth_validated': False}


def refine(*args, memory_path=None, **kwargs):
    """Optional local experience storage; the geometry solver remains authoritative."""
    if memory_path is None:
        return _refine(*args, **kwargs)
    from contextlib import closing
    from .build_memory import BuildMemory
    with closing(BuildMemory(memory_path)) as memory:
        height, material, report = _refine(*args, memory=memory, **kwargs)
        report['memory'] = memory.summary()
        return height, material, report
