"""Class-independent physical-instance association across orthographic views.

Captions are optional identifiers, not a fixed vocabulary of object roles.
Correspondences, projection consistency and assignment margins own identity.
Ambiguous observations stay unresolved rather than manufacturing extra parts.
"""
import re
import numpy as np
from scipy.optimize import linear_sum_assignment

AXES = {'front': (0, False, 2, True), 'back': (0, True, 2, True),
        'right': (1, False, 2, True), 'left': (1, True, 2, True),
        'top': (0, False, 1, True), 'bottom': (0, False, 1, False)}


def label(value, fallback):
    value = re.sub(r'\s+', ' ', str(value or '').strip().casefold())
    return value if value and value not in ('part', 'unknown', 'unassigned') else f'anonymous_{fallback}'


def volume(box, view):
    """Lift image rectangle fractions into a bounded orthographic ray volume."""
    if view not in AXES:
        raise ValueError('Orthographic view required')
    a, flip_a, b, flip_b = AXES[view]
    result = np.array([[0., 1.]] * 3)
    for axis, lower, upper, flip in ((a, box[0], box[2], flip_a), (b, box[1], box[3], flip_b)):
        result[axis] = [1 - upper, 1 - lower] if flip else [lower, upper]
    return result, {a, b}


def overlap(a, b):
    intersection = max(0, min(a[2], b[2]) - max(a[0], b[0])) * \
        max(0, min(a[3], b[3]) - max(a[1], b[1]))
    area_a = max(1e-12, (a[2] - a[0]) * (a[3] - a[1]))
    area_b = max(1e-12, (b[2] - b[0]) * (b[3] - b[1]))
    return intersection / max(1e-12, area_a + area_b - intersection)


def compatibility(node, observation):
    bounds, axes = volume(observation['box_unit'], observation['view'])
    shared = axes & set(node['_axes'])
    if not shared:
        return 0.
    score = 1.
    for axis in shared:
        a, b = node['_bounds'][axis], bounds[axis]
        length = min(a[1], b[1]) - max(a[0], b[0])
        if length <= 0:
            return 0.
        score *= length / max(1e-8, min(a[1] - a[0], b[1] - b[0]))
    return float(score * observation['confidence'])


def associate(observations, minimum_confidence=.25, margin=.08):
    """Global per-view assignment, with explicit ambiguity and no role grammar."""
    observations = [dict(o) for o in observations]
    anonymous = {}
    for item in observations:
        if not item.get('label') or str(item['label']).casefold() in ('part', 'unknown', 'unassigned'):
            anonymous.setdefault(
                item.get('source_region', item['id']), []).append(item)
    parent = {key: key for key in anonymous}

    def root(key):
        while parent[key] != key:
            key = parent[key]
        return key
    keys = list(anonymous)
    for i, a in enumerate(keys):
        for b in keys[:i]:
            shared = {x['view'] for x in anonymous[a] for y in anonymous[b]
                      if x['view'] == y['view'] and min(x.get('confidence', 0), y.get('confidence', 0)) >= minimum_confidence
                      and overlap(x['box_unit'], y['box_unit']) > .65}
            if len(shared) >= 2:
                parent[root(a)] = root(b)
    for key, items in anonymous.items():
        for item in items:
            item['label'] = f'anonymous_{root(key)}'
    groups = {}
    rejected = []
    for observation in observations:
        if observation.get('view') not in AXES or observation.get('confidence', 0) < minimum_confidence:
            rejected.append(observation.get('id'))
            continue
        groups.setdefault(label(observation.get('label'),
                          observation['id']), []).append(observation)
    nodes, ambiguous = [], []
    for caption, items in sorted(groups.items()):
        views = {}
        for item in sorted(items, key=lambda value: -value['confidence']):
            peers = views.setdefault(item['view'], [])
            duplicate = next((p for p in peers if overlap(
                p['box_unit'], item['box_unit']) > .5), None)
            if duplicate is None:
                peers.append(dict(item, duplicate_observations=[]))
            else:
                duplicate['duplicate_observations'].append(item['id'])
        anchor = max(views, key=lambda v: sum(
            o['confidence'] for o in views[v]))
        current = []
        for observation in sorted(views[anchor], key=lambda o: (o['box_unit'][0], o['box_unit'][1])):
            bounds, axes = volume(observation['box_unit'], anchor)
            current.append({'id': f'physical_{len(nodes) + len(current):04d}', 'label': caption,
                            'observations': [observation], '_bounds': bounds, '_axes': axes})
        for view, others in views.items():
            if view == anchor:
                continue
            scores = np.array([[compatibility(node, item)
                              for item in others] for node in current])
            rows, cols = linear_sum_assignment(-scores)
            assigned = set()
            for row, col in zip(rows, cols):
                score = scores[row, col]
                competitors = np.delete(scores[:, col], row)
                runner = float(competitors.max()) if len(competitors) else 0.
                if score < minimum_confidence or score - runner < margin:
                    continue
                node, item = current[row], others[col]
                bounds, axes = volume(item['box_unit'], view)
                for axis in axes:
                    if axis in node['_axes']:
                        node['_bounds'][axis] = [max(node['_bounds'][axis, 0], bounds[axis, 0]),
                                                 min(node['_bounds'][axis, 1], bounds[axis, 1])]
                    else:
                        node['_bounds'][axis] = bounds[axis]
                node['_axes'] |= axes
                node['observations'].append(item)
                assigned.add(col)
            for col, item in enumerate(others):
                if col not in assigned:
                    ambiguous.append({'observation': item['id'], 'label': caption, 'view': view,
                                      'candidate_physical_ids': [node['id'] for i, node in enumerate(current) if scores[i, col] >= minimum_confidence],
                                      'reason': 'projection does not uniquely determine physical instance'})
        nodes.extend(current)
    for node in nodes:
        node['bounds_unit_xyz'] = node.pop('_bounds').tolist()
        node['bounded_axes'] = sorted(node.pop('_axes'))
        node['spatially_constrained'] = len(node['bounded_axes']) == 3
        node['cross_view_support'] = len(
            set(o['view'] for o in node['observations']))
    return {'version': 1, 'method': 'class-independent correspondence / projection / assignment graph',
            'parts': nodes, 'ambiguous_observations': ambiguous, 'rejected_observations': rejected,
            'needs_review': bool(ambiguous or rejected or any(not n['spatially_constrained'] for n in nodes))}


def ownership(claims, foreground, margin=.08):
    """Per-pixel physical ownership; conflicts remain unknown, never body paint."""
    foreground = np.asarray(foreground, bool)
    best = np.zeros(foreground.shape)
    second = np.zeros_like(best)
    owners = np.full(foreground.shape, -1, np.int32)
    for identifier, mask, confidence in claims:
        candidate = np.asarray(mask, bool) & foreground
        score = np.where(candidate, float(confidence), 0.)
        replace = score > best
        second = np.where(replace, best, np.maximum(second, score))
        owners[replace] = identifier
        best = np.maximum(best, score)
    conflict = foreground & (second > 0) & (best - second < margin)
    owners[conflict] = -2
    return owners, {'assigned_pixels': int((owners >= 0).sum()), 'conflicting_pixels': int(conflict.sum()),
                    'unclaimed_foreground_pixels': int((foreground & (best == 0)).sum())}


def from_report(report):
    """Reuse existing dense visual correspondences for any caption vocabulary."""
    assembly = {r['id']: r for r in report['regions']
                if r['part'] == 'assembly'}
    observations = []
    for region in report['regions']:
        if region['part'] == 'assembly':
            continue
        for index, match in enumerate(region.get('dense_matches', [])):
            target = assembly.get(match['assembly_region'])
            if target is None or match['view'] not in AXES:
                continue
            width, height = target['box'][2] - \
                target['box'][0], target['box'][3] - target['box'][1]
            # Coverage and inlier fraction are correlated support measures,
            # not independent probabilities. Their geometric mean avoids
            # penalizing the same correspondence support twice.
            confidence = min(1, match.get('inliers', 0) / 12) * np.sqrt(
                max(0, match.get('source_coverage', 0) * match.get('inlier_fraction', 0))) * match.get('mean_similarity', 0)
            box = (np.asarray(match['box']) / [width,
                   height, width, height]).clip(0, 1).tolist()
            observations.append({'id': f'{region["id"]}:{index}', 'label': region['part'],
                                 'source_region': region['id'], 'assembly_region': target['id'], 'view': match['view'],
                                 'box_unit': box, 'confidence': float(confidence), 'affine_2d': match.get('affine_2d')})
    result = associate(observations)
    candidates = []
    for region in report['regions']:
        if region['part'] == 'assembly':
            continue
        supported = [node for node in result['parts']
                     if any(item['source_region'] == region['id']
                            for item in node['observations'])]
        candidates.append({
            'source_region': region['id'], 'label': region['part'],
            'matched_physical_ids': [node['id'] for node in supported],
            'status': ('spatially_constrained' if any(node['spatially_constrained']
                                                     for node in supported) else
                       'single_axis_or_insufficient_correspondence' if supported else
                       'insufficient_correspondence')})
    result['candidate_regions'] = candidates
    result['needs_review'] = result['needs_review'] or any(
        item['status'] != 'spatially_constrained' for item in candidates)
    result['source'] = 'existing learned dense correspondences; no object-role vocabulary'
    result['confidence_kind'] = 'heuristic support score; not calibrated probability'
    return result


def export_ownership(report, image, background, destination):
    """Warp observed companion masks into their exact assembly-image frames.

    Unclaimed pixels are unknown, not automatically the body. These maps are
    evidence for downstream source selection, not new manufactured geometry.
    """
    from pathlib import Path
    import cv2
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    regions = {item['id']: item for item in report['regions']}
    graph = report['physical_part_graph']
    identifiers = [node['id'] for node in graph['parts']]
    claims = {}
    for identifier, node in enumerate(graph['parts']):
        for observation in node['observations']:
            affine = observation.get('affine_2d')
            if affine is None:
                continue
            source = regions[observation['source_region']]
            target = regions[observation['assembly_region']]
            pixels = np.asarray(image.crop(
                source['box']).convert('RGB'), float)
            foreground = np.abs(pixels - np.asarray(background)).sum(2) > 32
            width, height = target['box'][2] - \
                target['box'][0], target['box'][3] - target['box'][1]
            matrix = np.asarray(affine, float)
            if matrix.shape != (2, 3) or not np.isfinite(matrix).all():
                raise ValueError(
                    'Finite source-to-assembly affine transform required')
            warped = cv2.warpAffine(foreground.astype(np.uint8), matrix, (width, height),
                                    flags=cv2.INTER_NEAREST, borderMode=cv2.BORDER_CONSTANT) > 0
            claims.setdefault(target['id'], []).append(
                (identifier, warped, observation['confidence']))
    outputs = {}
    for key, items in claims.items():
        target = regions[key]
        pixels = np.asarray(image.crop(target['box']).convert('RGB'), float)
        foreground = np.abs(pixels - np.asarray(background)).sum(2) > 32
        owners, statistics = ownership(items, foreground)
        path = destination / f'assembly-{key}-owners.npz'
        np.savez_compressed(path, owners=owners, foreground=foreground,
                            physical_ids=np.asarray(identifiers), sheet_box=np.asarray(target['box']))
        outputs[str(key)] = {'path': str(path), 'view': target['view'],
                             'coordinate_frame': 'uncropped assembly region; pixel centres',
                             'sheet_box': target['box'], **statistics}
    return {'sources': outputs, 'physical_ids': identifiers,
            'unknown': -1, 'conflict': -2, 'used_for_geometry': False,
            'used_for_texture_projection': False}
