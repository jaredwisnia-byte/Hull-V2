"""Choose a construction method from measured shape, independently of object name.

The profile candidate replaces only the smooth envelope of a supported long
region. The ordinary depth solver still owns its local surface relief. A caller
must compare the complete candidate against the ordinary build before adoption.
"""
import numpy as np
import math


def propose(views, height_m):
    try:
        return _propose(views, height_m)
    except Exception as error:
        # An optional specialist must never prevent the ordinary build.
        return None, {'choice': 'continuous_field',
                      'reason': 'profile evidence unavailable',
                      'planner_error': type(error).__name__ + ': ' + str(error)}


def _propose(views, height_m):
    from . import construction

    stability = {}
    if views:
        from PIL import Image
        from .hull import silhouette
        for name, path in views.items():
            if name not in ('front', 'back', 'left', 'right'):
                continue
            width, height = Image.open(path).size
            masks = []
            for threshold in (20, 45):
                mask, _, box = silhouette(path, thresh=threshold, with_box=True)
                full = np.zeros((height, width), bool)
                full[box[1]:box[3], box[0]:box[2]] = mask
                masks.append(full)
            stability[name] = float(np.logical_and(*masks).sum() /
                                    max(1, np.logical_or(*masks).sum()))
    model = construction.infer(views, height_m)
    if model is None:
        return None, {'choice': 'continuous_field', 'reason': 'no jointly observed elongated profile',
                      'silhouette_stability': stability}
    report = model['report']
    band = report['band']
    span = band[1] - band[0]
    rms = report['camera_axis_fit']['residual_rms']
    stations = np.linspace(*band, 16)
    disagreements = {}
    for a, b in (('front', 'back'), ('right', 'left')):
        if a not in model['profiles'] or b not in model['profiles']:
            continue
        widths = []
        for name in (a, b):
            p = model['profiles'][name]
            widths.append(np.interp(stations, np.arange(len(p['width'])) /
                                    len(p['width']), p['width'] / len(p['width'])))
        disagreements[a + '_' + b] = float(np.max(
            np.abs(widths[0] - widths[1]) / np.maximum(np.mean(widths, axis=0), 1e-6)))
    # A long span and a coherent shared axis are geometric evidence. Grooves
    # are evaluated separately by the depth station, never invented here.
    eligible = (span >= .25 and rms <= .003 and bool(stability) and
                min(stability.values()) >= .97 and
                max(disagreements.values(), default=0.) <= .1)
    return (model if eligible else None), {
        'choice': 'profile_shaft_candidate' if eligible else 'continuous_field',
        'reason': 'long coherent taper and stable outlines' if eligible else 'profile span, axis, or outline uncertainty',
        'band': band, 'span': span, 'axis_residual_rms': rms,
        'paired_width_disagreement': disagreements,
        'silhouette_stability': stability,
        'legacy_channels_detected': len(report['features']),
        'policy': 'candidate only; preserve continuous relief and require complete-build comparison',
    }


def replace_envelope(field, model, dimensions):
    """Blend a fitted taper into a field after the independent depth pass.

    The smooth transition has no mesh part boundary. The output remains one
    continuous field, including all geometry outside the supported region.
    """
    from .construction import shaft_vertices

    field = np.asarray(field)
    width, depth, height = map(float, dimensions)
    shaft_vertices(model, stations=32)
    report = model['report']
    fit = report['spline_profile']
    band = report['band']
    side = 'right' if 'right' in model['profiles'] else 'left'
    source_width = height * model['profiles']['front']['image_width'] / len(model['profiles']['front']['width'])
    source_depth = height * model['profiles'][side]['image_width'] / len(model['profiles'][side]['width'])
    scale_x = width / source_width
    scale_y = depth / source_depth
    rows = np.linspace(band[0], band[1], fit['stations'])
    centers = np.asarray(fit['center_samples_m'])
    rx, ry = np.asarray(fit['radius_samples_m'])
    # The old physical-part prototype intersected opposite boundaries and
    # systematically narrowed the fitted envelope. This candidate uses their
    # mean width while retaining the prototype's smooth spline profile.
    for axis, names in enumerate((('front', 'back'), ('right', 'left'))):
        widths = []
        for name in names:
            if name not in model['profiles']:
                continue
            p = model['profiles'][name]
            widths.append(np.interp(rows, np.arange(len(p['width'])) /
                                    len(p['width']), p['width']) / len(p['width']) * height / 2)
        if widths:
            target = np.mean(widths, axis=0)
            fitted = rx if axis == 0 else ry
            correction = float(np.median(target / np.maximum(fitted, 1e-6)))
            if axis == 0:
                rx = rx * correction
            else:
                ry = ry * correction
    n_x, n_y, n_z = field.shape
    x = ((np.arange(n_x) + .5) / n_x - .5) * width
    y = ((np.arange(n_y) + .5) / n_y - .5) * depth
    output = field.copy()
    transition = min(.035, (band[1] - band[0]) * .15)
    for k in range(n_z):
        v = 1 - (k + .5) / n_z
        if v <= band[0] or v >= band[1]:
            continue
        edge = min(v - band[0], band[1] - v)
        t = np.clip(edge / transition, 0, 1)
        weight = t * t * (3 - 2 * t)
        cx = np.interp(v, rows, centers[0]) * scale_x
        cy = np.interp(v, rows, centers[1]) * scale_y
        a = np.interp(v, rows, rx) * scale_x
        b = np.interp(v, rows, ry) * scale_y
        radial = np.sqrt(((x[:, None] - cx) / a)**2 +
                         ((y[None, :] - cy) / b)**2)
        envelope = (radial - 1) * min(a, b)
        output[:, :, k] = (1 - weight) * field[:, :, k] + weight * envelope
    return output


def preflight_field(base, detailed, model, dimensions):
    """Screen the fitted envelope against the real detailed field before export."""
    from .correction_review import Rejected
    from .implicit import preserve_components

    try:
        fitted = detailed + replace_envelope(base, model, dimensions) - base
        _, topology = preserve_components(base, fitted)
    except Rejected as error:
        return {'accepted': False, 'reason': 'profile conflicts with existing solid topology',
                'topology_review': error.report}
    except Exception as error:
        return {'accepted': False, 'reason': 'profile preflight could not be evaluated',
                'planner_error': type(error).__name__ + ': ' + str(error)}
    return {'accepted': True, 'reason': 'profile preserves existing solid topology',
            'topology': topology}


def compare_exports(baseline, candidate, baseline_measured, candidate_measured):
    """Compare complete exported assets; reject an attractive intermediate fit.

    A simpler candidate may retain the baseline's unresolved failures, but it
    cannot introduce any. Release still depends on the ordinary QA gate.
    """
    old = baseline.get('metrics', {})
    new = candidate.get('metrics', {})
    old_fails = set(baseline.get('fails', ()))
    new_fails = set(candidate.get('fails', ()))
    old_other = {f for f in old_fails if not f.startswith('missing shading depth:')}
    new_other = {f for f in new_fails if not f.startswith('missing shading depth:')}
    old_relief = baseline_measured.get('relief', {})
    new_relief = candidate_measured.get('relief', {})
    old_probes = old_relief.get('probes', ())
    new_probes = new_relief.get('probes', ())

    def failed_locations(result, relief):
        ids = {f.split('missing shading depth: ', 1)[1] for f in result.get('fails', ())
               if f.startswith('missing shading depth: ')}
        records = {p['id']: p for p in relief.get('probes', ())}
        dims = relief.get('dimensions_m')
        if not dims:
            return [], len(ids)
        width, depth, height = dims
        locations = []
        for identifier in ids:
            p = records.get(identifier)
            if not p or not p.get('anchors_m'):
                continue
            x, y, z = p['anchors_m'][0]
            view = p['view']
            if view == 'front':
                u, v = x / width + .5, 1 - z / height
            elif view == 'back':
                u, v = .5 - x / width, 1 - z / height
            elif view == 'right':
                u, v = y / depth + .5, 1 - z / height
            elif view == 'left':
                u, v = .5 - y / depth, 1 - z / height
            else:
                continue
            locations.append((view, np.asarray([u, v])))
        return locations, len(ids)

    old_locations, old_missing = failed_locations(baseline, old_relief)
    new_locations, new_missing = failed_locations(candidate, new_relief)
    unmatched = sum(not any(view == old_view and np.linalg.norm(point - old_point) <= .03
                            for old_view, old_point in old_locations)
                    for view, point in new_locations)
    comparable = (bool(old_probes) and bool(new_probes) and
                  len(new_probes) >= .95 * len(old_probes) and
                  len(old_locations) == old_missing and len(new_locations) == new_missing)
    old_tris = old.get('tris') or 0
    new_tris = new.get('tris') or 0
    old_folds = old.get('extreme_folds', {}).get('per_1k')
    new_folds = new.get('extreme_folds', {}).get('per_1k')
    valid_folds = (isinstance(old_folds, (int, float)) and
                   isinstance(new_folds, (int, float)) and
                   math.isfinite(old_folds) and math.isfinite(new_folds))
    old_outline = old.get('silhouette_iou', {})
    new_outline = new.get('silhouette_iou', {})
    outline_delta = min((new_outline.get(view, -1) - value
                         for view, value in old_outline.items()), default=-1.)
    checks = {
        'no_new_other_failures': not (new_other - old_other),
        'comparable_feature_evidence': comparable,
        'no_new_missing_feature_locations': new_missing <= old_missing and unmatched == 0,
        'one_connected_solid': new.get('geometric_components') == 1,
        'outline_preserved': outline_delta >= -.005,
        'folds_not_worse': valid_folds and new_folds <= old_folds,
        'triangles_not_worse': bool(old_tris and new_tris and new_tris <= old_tris),
        'meaningful_gain': (bool(new_tris) and
                           (len(new_fails) < len(old_fails) or
                            bool(old_tris and new_tris <= old_tris * .85))),
    }
    return {'accepted': all(checks.values()), 'checks': checks,
            'baseline_failures': sorted(old_fails), 'candidate_failures': sorted(new_fails),
            'baseline_feature_probes': len(old_probes), 'candidate_feature_probes': len(new_probes),
            'unmatched_missing_feature_locations': unmatched,
            'baseline_triangles': old_tris, 'candidate_triangles': new_tris,
            'minimum_outline_delta': outline_delta,
            'folds_per_1k': [old_folds, new_folds],
            'decision': 'apply' if all(checks.values()) else 'reject_and_rollback',
            'uses_llm': False}


def dense_gate(baseline_missing, candidate_missing):
    """Stop a candidate before baking when it already loses more local detail."""
    accepted = (isinstance(baseline_missing, int) and
                isinstance(candidate_missing, int) and
                candidate_missing <= baseline_missing)
    return {'accepted': accepted, 'decision': 'continue' if accepted else 'reject_and_rollback',
            'baseline_missing': baseline_missing,
            'candidate_missing': candidate_missing,
            'reasons': [] if accepted else ['dense mesh loses more local details than baseline'],
            'uses_llm': False, 'physical_geometry_verified': False}
