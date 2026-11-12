"""Bounded, evidence-gated repair of details lost while fusing camera views.

This station does not infer new detail. It can restore an already accepted
single-view hypothesis near its own visible skin. Every trial is checked
against all source-derived cross-section probes before it can be kept.
"""

import numpy as np
from scipy import ndimage


def _contrast(field, probe, dimensions):
    from .surface_detail import VIEWS
    axis, reverse = VIEWS[probe['view']]
    transverse = [i for i in range(3) if i != axis]
    bounds = [(-dimensions[0] / 2, dimensions[0] / 2),
              (-dimensions[1] / 2, dimensions[1] / 2), (0, dimensions[2])]
    n = field.shape[axis]
    offsets = []
    for anchor in probe['anchors_m']:
        index = [(anchor[i] - bounds[i][0]) / dimensions[i] * field.shape[i] - .5
                 for i in transverse]
        coordinates = np.empty((3, n), float)
        for i in range(3):
            coordinates[i] = np.arange(n) if i == axis else index[transverse.index(i)]
        line = ndimage.map_coordinates(field, coordinates, order=1, mode='nearest')
        if reverse:
            line = line[::-1]
        occupied = np.flatnonzero(line < 0)
        if not len(occupied):
            return None
        first = int(occupied[0])
        previous = max(0, first - 1)
        a, b = float(line[previous]), float(line[first])
        fraction = np.clip(a / max(a - b, 1e-12), 0, 1)
        depth = (previous + fraction + .5) * dimensions[axis] / n if first else 0.
        actual = bounds[axis][1] - depth if reverse else bounds[axis][0] + depth
        offsets.append((actual - anchor[axis]) * probe['outward'])
    return float(offsets[0] - np.mean(offsets[1:]))


def _failures(field, probes, dimensions):
    failed = set()
    for probe in probes:
        target = probe['target_offsets_m']
        expected = target[0] - np.mean(target[1:])
        measured = _contrast(field, probe, dimensions)
        if measured is None or measured * expected <= 0 or abs(measured) < abs(expected) * .5:
            failed.add(probe['id'])
    return failed


def _source_supported(plan, probe):
    from .probe_review import image_uv
    view = probe['view']
    data = plan.get('diagnostics', {}).get(view, {})
    labels = data.get('feature_labels')
    if labels is None:
        return False
    u, v = image_uv(probe['anchors_m'][0], view, plan['dimensions'])
    row = int(np.clip(v * labels.shape[0], 0, labels.shape[0] - 1))
    col = int(np.clip(u * labels.shape[1], 0, labels.shape[1] - 1))
    region_id = int(labels[row, col])
    regions = plan['report']['views'].get(view, {}).get('relief_selection', {}).get('regions', ())
    source = next((r for r in regions if r['region_id'] == region_id), None)
    return bool(source and source.get('initially_supported') and source.get('applied')
                and source.get('final_test_gain', 0) > 0)


def _skin_weight(field, view, dimensions):
    from .surface_detail import VIEWS, visible_root
    axis, reverse = VIEWS[view]
    root, _, _, valid = visible_root(field, axis, reverse, dimensions[axis])
    if axis == 0:
        root, valid = root[None, :, :], valid[None, :, :]
    elif axis == 1:
        root, valid = root[:, None, :], valid[:, None, :]
    else:
        root, valid = root[:, :, None], valid[:, :, None]
    n = field.shape[axis]
    distance = (np.arange(n) + .5) * dimensions[axis] / n
    if reverse:
        distance = dimensions[axis] - distance
    shape = [1, 1, 1]
    shape[axis] = n
    # A local skin band avoids changing the opposite visible face.
    band = max(3 * dimensions[axis] / n, .004)
    return np.exp(-((distance.reshape(shape) - root) / band)**4) * valid


def attempt(base, fused, plan, targets):
    """Return a candidate only if supported details improve without probe regressions.

    The final extracted mesh and quality gate are still authoritative. This
    field-level gate only decides whether a second build is worth attempting.
    """
    from . import surface_detail
    from .implicit import preserve_components
    from .probe_review import image_uv
    dimensions = plan['dimensions']
    probes = plan['report'].get('probes', ())
    baseline = _failures(fused, probes, dimensions)
    current = np.array(fused, copy=True)
    failures = set(baseline)
    accepted = []
    single_views = {}
    skin_weights = {}
    for target in targets:
        if target.get('status') != 'supported_unmet':
            continue
        view = target['view']
        candidates = [p for p in probes if p['view'] == view]
        if not candidates or view not in plan['maps']:
            continue
        probe = min(candidates, key=lambda p: np.linalg.norm(
            np.asarray(image_uv(p['anchors_m'][0], view, dimensions)) -
            np.asarray(target['center_uv'])))
        if np.linalg.norm(np.asarray(image_uv(probe['anchors_m'][0], view, dimensions)) -
                          np.asarray(target['center_uv'])) > .025:
            continue
        if probe['id'] not in failures or not _source_supported(plan, probe):
            continue
        if view not in single_views:
            single_views[view] = surface_detail.apply_field(base, {
                'maps': {view: plan['maps'][view]}, 'dimensions': dimensions,
                'report': {'features': []},
                # Isolated evidence has no other camera to restrain its far
                # side. Suppress very weak skin weights in this proposal only.
                'fusion_weight_floor': .05})
            skin_weights[view] = _skin_weight(base, view, dimensions)
        axis, _ = surface_detail.VIEWS[view]
        u, v = surface_detail._mapping(view, dimensions, base.shape)
        height, width = plan['maps'][view].shape
        center = image_uv(probe['anchors_m'][0], view, dimensions)
        radius_squared = ((u - center[0]) * width)**2 + ((v - center[1]) * height)**2
        difference = single_views[view] - fused
        best = None
        for sigma in (3, 4, 5, 6, 8, 10, 12, 16, 20):
            mask = np.exp(-radius_squared / (2 * sigma * sigma))
            if axis == 0:
                mask = mask[None, :, :]
            elif axis == 1:
                mask = mask[:, None, :]
            else:
                mask = mask[:, :, None]
            delta = mask * skin_weights[view] * difference
            for strength in (.5, .75, 1., 1.25):
                trial = current + strength * delta
                failed = _failures(trial, probes, dimensions)
                repaired = failures - failed
                introduced = failed - failures
                if probe['id'] not in repaired or introduced:
                    continue
                expected = abs(probe['target_offsets_m'][0] -
                               np.mean(probe['target_offsets_m'][1:]))
                margin = abs(_contrast(trial, probe, dimensions)) / max(expected, 1e-9)
                # Mesh extraction can erase a contrast that only barely
                # clears the 50% final threshold. Keep some field headroom.
                if margin < .65:
                    continue
                # Once the safety margin is met, prefer the smallest patch.
                key = (len(repaired), -sigma, -strength)
                if best is None or key > best[0]:
                    best = (key, trial, failed, sigma, strength, repaired, margin)
        if best is not None:
            _, current, failures, sigma, strength, repaired, margin = best
            accepted.append({'probe': probe['id'], 'view': view, 'sigma_px': sigma,
                             'strength': strength, 'field_retention_fraction': margin,
                             'repaired': sorted(repaired)})
    audit = {'method': 'supported single-view local skin retry; all-probe regression gate',
             'uses_llm': False, 'requested': len(targets), 'accepted': accepted,
             'baseline_field_failures': len(baseline)}
    if not accepted:
        audit.update(applied=False, reason='No non-regressing local proposal')
        return fused, audit
    from .correction_review import Rejected
    try:
        candidate, topology = preserve_components(base, current)
    except Rejected as error:
        audit.update(applied=False, reason='Component preservation rejected candidate',
                     topology_review=error.report)
        return fused, audit
    final_failures = _failures(candidate, probes, dimensions)
    probes_by_id = {probe['id']: probe for probe in probes}
    final_margins = {}
    for record in accepted:
        probe = probes_by_id[record['probe']]
        expected = abs(probe['target_offsets_m'][0] -
                       np.mean(probe['target_offsets_m'][1:]))
        actual = _contrast(candidate, probe, dimensions)
        final_margins[probe['id']] = (abs(actual) / max(expected, 1e-9)
                                      if actual is not None else 0.)
    # A retry may alter local relief, but cannot lose an already matched
    # projected outline or introduce a newly missing source-derived feature.
    silhouette_changes = [int(np.count_nonzero(
        np.any(candidate < 0, axis=axis) != np.any(fused < 0, axis=axis)))
        for axis in range(3)]
    projected_pixels = [int(np.any(fused < 0, axis=axis).size) for axis in range(3)]
    outline_fraction = max(c / max(p, 1) for c, p in zip(silhouette_changes, projected_pixels))
    audit.update(candidate_field_failures=len(final_failures),
                 introduced_failures=sorted(final_failures - baseline),
                 repaired_failures=sorted(baseline - final_failures),
                 final_target_retention=final_margins,
                 outline_changed_pixels=silhouette_changes,
                 outline_change_fraction=outline_fraction,
                 topology=topology)
    # At this grid resolution, changing a few tangent cells can alter a
    # projection without moving the visible contour by a whole source pixel.
    # The exported silhouette IoU remains an independent, stricter build gate.
    audit['outline_change_limit'] = .002
    audit['applied'] = bool(len(final_failures) < len(baseline)
                            and not final_failures - baseline
                            and all(value >= .65 for value in final_margins.values())
                            and outline_fraction <= audit['outline_change_limit'])
    if not audit['applied']:
        audit['reason'] = 'Field regression, topology or outline gate rejected candidate'
    return (candidate if audit['applied'] else fused), audit
