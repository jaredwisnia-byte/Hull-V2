"""Inspect dense-mesh depth failures against the image evidence that produced them.

This station records evidence and proposes retry regions. It never turns a
failed source hypothesis into geometry or changes the final QA threshold.
"""

import json
from pathlib import Path

import numpy as np


def image_uv(anchor, view, dimensions):
    """Project a model-space probe anchor into its orthographic source chart."""
    w, d, h = dimensions
    x, y, z = anchor
    if view in ('front', 'back'):
        u, v = x / w + .5, 1 - z / h
    elif view in ('left', 'right'):
        u, v = y / d + .5, 1 - z / h
    elif view == 'top':
        u, v = x / w + .5, .5 - y / d
    else:
        u, v = x / w + .5, y / d + .5
    if view in ('back', 'left'):
        u = 1 - u
    return float(u), float(v)


def stage_contrasts(arrays, probe, dimensions):
    """Sample the same three anchors in accepted and shared image-space depth."""
    needed = {'accepted_height_px', 'coarse_height_px',
              'final_shared_height_px', 'metres_per_pixel'}
    if not needed <= set(arrays.files) or len(probe['anchors_m']) != 3:
        return None
    from scipy.ndimage import map_coordinates
    view = probe['view']
    accepted = arrays['accepted_height_px']
    shared = arrays['final_shared_height_px'] - arrays['coarse_height_px']
    if accepted.shape != shared.shape or accepted.ndim != 2:
        return None
    height, width = accepted.shape
    uv = np.asarray([image_uv(anchor, view, dimensions)
                     for anchor in probe['anchors_m']])
    if not np.isfinite(uv).all() or (uv < 0).any() or (uv > 1).any():
        return None
    pixels = np.vstack((uv[:, 1] * height - .5, uv[:, 0] * width - .5))
    pixel_m = float(arrays['metres_per_pixel'])
    if not np.isfinite(pixel_m) or pixel_m <= 0:
        return None

    def contrast(values):
        samples = map_coordinates(values, pixels, order=1, mode='nearest')
        return float((samples[0] - samples[1:].mean()) * pixel_m)

    return {'accepted_m': contrast(accepted), 'shared_field_m': contrast(shared)}


def first_observed_loss(expected, dense, contrasts):
    """Locate the first measured loss without treating source depth as truth."""
    if expected is None or not contrasts or abs(expected) < 1e-9:
        return 'unresolved'
    accepted = contrasts['accepted_m']
    shared = contrasts['shared_field_m']
    if accepted * expected <= 0 or abs(accepted) < .5 * abs(expected):
        return 'accepted_height'
    if shared * expected <= 0 or abs(shared) < .5 * abs(expected):
        return 'shared_field_or_repair'
    if dense is None or dense * expected <= 0 or abs(dense) < .5 * abs(expected):
        return 'mesh_or_probe_intersection'
    return 'unresolved'


def classify(report, dimensions, diagnostic_folder):
    """Pair every unmet dense probe with its source region and held-out evidence."""
    failed = set(report.get('unmet_before_reduction', ()))
    probes = {item['id']: item for item in report.get('probes', ())}
    measured = {item['id']: item for item in report.get(
        'pre_reduction_validation', {}).get('probes', ())}
    selection = {view: {item['region_id']: item for item in data.get(
        'relief_selection', {}).get('regions', ())}
        for view, data in report.get('views', {}).items()}
    cross = {(item['view'], item['region_id']): item for item in report.get(
        'cross_view_relief', {}).get('regions', ())}
    folder = Path(diagnostic_folder)
    records = []
    for identifier in sorted(failed):
        probe = probes.get(identifier)
        if probe is None:
            continue
        view = probe['view']
        uv = image_uv(probe['anchors_m'][0], view, dimensions)
        region_id = 0
        contrasts = None
        path = folder / (view + '.npz')
        if path.is_file():
            with np.load(path, allow_pickle=False) as arrays:
                if 'feature_labels' in arrays.files:
                    labels = arrays['feature_labels']
                    row = int(np.clip(uv[1] * labels.shape[0], 0, labels.shape[0] - 1))
                    col = int(np.clip(uv[0] * labels.shape[1], 0, labels.shape[1] - 1))
                    region_id = int(labels[row, col])
                contrasts = stage_contrasts(arrays, probe, dimensions)
        source = selection.get(view, {}).get(region_id, {})
        matched = cross.get((view, region_id), {})
        supported = bool(source.get('initially_supported') and source.get('applied')
                         and (source.get('final_test_gain') or 0) > 0)
        status = ('supported_unmet' if supported else
                  'unsupported_source' if source else 'unclassified')
        dense = measured.get(identifier, {})
        expected = dense.get('expected_contrast_m')
        measured_contrast = dense.get('measured_contrast_m')
        records.append({'id': identifier, 'view': view, 'center_uv': list(uv),
                        'region_id': region_id, 'status': status,
                        'selection_gain': source.get('selection_gain'),
                        'acceptance_gain': source.get('acceptance_gain'),
                        'final_test_gain': source.get('final_test_gain'),
                        'cross_view_status': matched.get('status', 'unknown'),
                        'expected_contrast_m': expected,
                        'dense_contrast_m': measured_contrast,
                        'stage_contrasts_m': contrasts,
                        'first_observed_loss': first_observed_loss(
                            expected, measured_contrast, contrasts),
                        'anchors_m': probe['anchors_m'],
                        'target_offsets_m': probe['target_offsets_m']})
    return records


def _height_image(values, limit):
    from PIL import Image
    scaled = np.clip(values / max(limit, 1e-9), -1, 1)
    negative = np.clip(-scaled, 0, 1)
    positive = np.clip(scaled, 0, 1)
    rgb = np.stack([1 - .75 * negative, 1 - .72 * abs(scaled),
                    1 - .8 * positive], axis=2)
    return Image.fromarray(np.uint8(np.clip(rgb, 0, 1) * 255))


def _crop(source, uv, size=128):
    from PIL import Image
    width, height = source.size
    cx = int(uv[0] * width)
    cy = int(uv[1] * height)
    radius = min(size // 2, width // 2, height // 2)
    box = (cx - radius, cy - radius, cx + radius, cy + radius)
    return source.crop(box).resize((256, 256), Image.Resampling.NEAREST)


def _mesh_section(obj, probe, tree):
    """Measure the three probe anchors on the dense mesh, in metres."""
    from mathutils import Vector
    direction = np.zeros(3)
    direction[probe['axis']] = probe['outward']
    reach = max(obj.dimensions) * 2
    offsets = []
    for anchor in probe['anchors_m']:
        point = np.asarray(anchor)
        location, _, _, _ = tree.ray_cast(
            Vector(point + direction * reach), Vector(-direction), reach * 2)
        offsets.append(None if location is None else float(
            (np.asarray(location) - point) @ direction))
    return offsets


def _section_panel(draw, item, y):
    """Show the expected flank/center/flank against the built section."""
    expected = item['target_offsets_m']
    built = item.get('dense_offsets_m', [])
    draw.text((8, y), 'Cross-section (relative offset, mm): source proposal / dense mesh',
              fill='#1b2a38')
    if len(built) != 3 or any(value is None for value in built):
        draw.text((8, y + 28), 'Dense section unavailable', fill='#a13929')
        return
    baseline = .5 * (expected[1] + expected[2])
    baseline_built = .5 * (built[1] + built[2])
    ex = [(value - baseline) * 1000 for value in expected]
    ob = [(value - baseline_built) * 1000 for value in built]
    magnitude = max(max(abs(v) for v in ex + ob), .1)
    xs = [100, 512, 924]
    center = y + 74
    scale = 45 / magnitude
    draw.line([(100, center), (924, center)], fill='#a8b1b8', width=1)
    for values, color in ((ex, '#3468c0'), (ob, '#b14b2e')):
        points = [(x, center - value * scale) for x, value in zip(xs, values)]
        draw.line(points, fill=color, width=3)
        for x, yy in points:
            draw.ellipse((x - 3, yy - 3, x + 3, yy + 3), fill=color)
    draw.text((8, y + 126), 'Blue: proposal   Orange: actual dense mesh   Scale: +/- %.2f mm' % magnitude,
              fill='#1b2a38')


def write(report, dimensions, source_views=None, obj=None, tree=None):
    """Write source/height/mesh comparisons for unmet dense probes, plus JSON."""
    from PIL import Image, ImageDraw
    folder = report.get('diagnostic_folder')
    if not folder:
        return None
    records = classify(report, dimensions, folder)
    if not records:
        return None
    target = Path(folder).parent / 'probe_review'
    target.mkdir(parents=True, exist_ok=True)
    for item in records:
        if obj is not None and tree is not None:
            probe = next((p for p in report.get('probes', ()) if p['id'] == item['id']), None)
            if probe is not None:
                item['dense_offsets_m'] = _mesh_section(obj, probe, tree)
        path = Path(folder) / (item['view'] + '.npz')
        if not path.is_file():
            continue
        with np.load(path, allow_pickle=False) as arrays:
            needed = {'hypothesis_height_px', 'accepted_height_px',
                      'coarse_height_px', 'final_shared_height_px'}
            if not needed <= set(arrays.files):
                continue
            proposal = arrays['hypothesis_height_px']
            accepted = arrays['accepted_height_px']
            applied = arrays['final_shared_height_px'] - arrays['coarse_height_px']
            source_path = (source_views or {}).get(item['view'])
            if source_path and Path(source_path).is_file():
                source = Image.open(source_path).convert('RGB')
            else:
                luminance = arrays['observed_log_luminance']
                gray = np.uint8(np.clip(np.exp(luminance), 0, 1) * 255)
                source = Image.fromarray(gray).convert('RGB')
            limit = max(float(np.percentile(abs(proposal), 99)), 1)
            panels = [source, _height_image(proposal, limit),
                      _height_image(accepted, limit), _height_image(applied, limit)]
            canvas = Image.new('RGB', (4 * 256, 450), '#e9edf1')
            draw = ImageDraw.Draw(canvas)
            for index, (label, panel) in enumerate(zip(
                    ('Source', 'Proposed', 'Accepted', 'Shared field'), panels)):
                canvas.paste(_crop(panel, item['center_uv']), (index * 256, 34))
                draw.text((index * 256 + 8, 9), label, fill='#1b2a38')
            draw.text((8, 292), 'First measured loss: ' + item['first_observed_loss'],
                      fill='#1b2a38')
            _section_panel(draw, item, 305)
            image_path = target / (item['id'] + '.png')
            canvas.save(image_path)
            item['image'] = str(image_path)
    summary = {'method': 'deterministic dense-probe and image-region audit',
               'uses_llm': False, 'physical_depth_verified': False,
               'failures': len(records),
               'supported_unmet': sum(item['status'] == 'supported_unmet' for item in records),
               'unsupported_source': sum(item['status'] == 'unsupported_source' for item in records),
               'probes': records}
    summary['supported_first_loss_counts'] = {
        stage: sum(item['status'] == 'supported_unmet' and
                   item['first_observed_loss'] == stage for item in records)
        for stage in ('accepted_height', 'shared_field_or_repair',
                      'mesh_or_probe_intersection', 'unresolved')}
    illustrated = [item for item in records if item.get('image')]
    if illustrated:
        rows = (len(illustrated) + 1) // 2
        sheet = Image.new('RGB', (1536, 54 + rows * 378), '#e9edf1')
        heading = ImageDraw.Draw(sheet)
        heading.text((12, 12), 'Dense detail failures: source / proposal / accepted / shared field / mesh',
                     fill='#1b2a38')
        for index, item in enumerate(illustrated):
            left = (index % 2) * 768
            top = 54 + (index // 2) * 378
            heading.text((left + 10, top + 2),
                         item['id'] + '  ' + item['status'], fill='#1b2a38')
            panel = Image.open(item['image']).convert('RGB')
            sheet.paste(panel.resize((768, 338)), (left, top + 25))
        overview = target / 'probe-review-overview.png'
        sheet.save(overview)
        summary['overview_image'] = str(overview)
    path = target / 'probe-review.json'
    path.write_text(json.dumps(summary, indent=2), encoding='utf-8')
    summary['path'] = str(path)
    report['probe_diagnostics'] = summary
    return summary
