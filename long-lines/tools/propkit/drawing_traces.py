"""Prebuild drafting evidence: only paths traced in the supplied views.

This deliberately does not create solids, fit circles, or infer depth. A later
cross-view solver may consume these paths, but must record its own inferences.
"""

import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage
from skimage.measure import find_contours

from .feature_curves import paths
from .feature_regions import trace
from .silhouette import silhouette


def _linear_rgb(pixels):
    color = np.asarray(pixels, np.float32) / 255.0
    return np.where(color <= .04045, color / 12.92,
                    ((color + .055) / 1.055) ** 2.4)


def _elevation_section(outer, row, height_fraction):
    """Intersect observed contour segments with one horizontal source-pixel row."""
    crossings = []
    for trace_index, contour in enumerate(outer):
        for segment_index, (start, end) in enumerate(zip(contour, contour[1:])):
            x0, y0 = start
            x1, y1 = end
            if (y0 <= row < y1) or (y1 <= row < y0):
                x = x0 + (row - y0) * (x1 - x0) / (y1 - y0)
                crossings.append({'x_source_px': float(x),
                                  'source_trace_id': f'outer:{trace_index}',
                                  'source_segment_index': segment_index})
    crossings.sort(key=lambda item: item['x_source_px'])
    parity_valid = len(crossings) % 2 == 0
    return {
        'height_fraction_from_top': float(height_fraction),
        'y_source_px': float(row), 'crossings': crossings,
        'outer_envelope_x_source_px': (
            [crossings[0]['x_source_px'], crossings[-1]['x_source_px']]
            if len(crossings) >= 2 and parity_valid else None),
        'crossing_parity_valid': parity_valid,
        'physical_cross_section_shape': 'unobserved',
    }


def observe(view, path, construction_mask=None, opening_witness=None):
    """Return source-pixel paths and their provenance, without geometric fitting."""
    image = Image.open(path).convert('RGB')
    cropped, _, box = silhouette(path, with_box=True)
    mask = np.zeros((image.height, image.width), bool)
    mask[box[1]:box[3], box[0]:box[2]] = cropped
    traced = trace(_linear_rgb(image), mask, backend='classical')
    _, internal = paths(traced['boundaries'])
    outer = [[[float(x), float(y)] for y, x in contour]
             for contour in find_contours(mask.astype(np.float32), .5)
             if len(contour) >= 8]
    sections = []
    if view in ('front', 'back', 'left', 'right'):
        for fraction in np.linspace(.05, .95, 19):
            row = box[1] + fraction * (box[3] - box[1])
            section = _elevation_section(outer, row, fraction)
            for crossing in section['crossings']:
                crossing['source_trace_id'] = f"{view}:{crossing['source_trace_id']}"
            sections.append(section)
    records = []
    for index, points in enumerate(outer):
        records.append({'id': f'{view}:outer:{index}', 'kind': 'outer_silhouette',
                        'source_view': view, 'source_path': str(path),
                        'method': 'foreground mask 0.5 isocontour in source pixels',
                        'points_source_xy': points,
                        'physical_interpretation': 'external boundary'})
    for index, points in enumerate(internal):
        if len(points) < 8:
            continue
        records.append({'id': f'{view}:internal:{index}',
                        'kind': 'internal_intensity_boundary',
                        'source_view': view, 'source_path': str(path),
                        'method': traced['method'] + ' / connected pixel path',
                        'points_source_xy': points,
                        'physical_interpretation': 'unresolved: relief, paint, shadow or part seam'})
    if construction_mask is not None:
        accepted = np.asarray(construction_mask, bool)
        if accepted.shape != cropped.shape or np.any(accepted & ~cropped):
            raise ValueError('Construction opening mask differs from source silhouette')
        openings = cropped & ~accepted
        if openings.any() and opening_witness is None:
            raise ValueError('Source opening lacks an opposite-view witness')
        labels, count = ndimage.label(openings)
        source_pixels = np.asarray(image)[box[1]:box[3], box[0]:box[2]]
        for index in range(1, count + 1):
            region = labels == index
            contours = find_contours(region.astype(np.float32), .5)
            if not contours:
                continue
            contour = max(contours, key=len)
            if len(contour) < 8:
                continue
            points = [[float(x + box[0]), float(y + box[1])]
                      for y, x in contour]
            colors = source_pixels[region]
            records.append({
                'id': f'{view}:opening:{index}', 'kind': 'opposed_mask_opening',
                'source_view': view, 'source_path': str(path),
                'method': 'accepted source opening-mask isocontour',
                'points_source_xy': points,
                'cross_view_witness': opening_witness,
                'area_source_px': int(region.sum()),
                'appearance_median_rgb': np.median(colors, axis=0).tolist(),
                'appearance_std_rgb': np.std(colors, axis=0).tolist(),
                'physical_interpretation':
                'opposing masks agree; physical through-opening unverified'})
    return {'view': view, 'source_path': str(path),
            'source_size_px': [image.width, image.height],
            'foreground_box_px': list(map(int, box)),
            'trace_backend': traced['tracing_backend'],
            'traces': records,
            'observed_elevation_sections': sections,
            'outer_path_count': len(outer),
            'internal_path_count': sum(r['kind'] == 'internal_intensity_boundary'
                                       for r in records),
            'opposed_mask_opening_count': sum(r['kind'] == 'opposed_mask_opening'
                                           for r in records)}


def infer(views, destination, construction_masks=None, opening_report=None):
    """Create the first-station drawing and JSON from arbitrary labelled views."""
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    selected = [name for name in ('front', 'right', 'left', 'back', 'top', 'bottom')
                if name in views]
    if not selected:
        raise ValueError('At least one labelled source view is required')
    construction_masks = construction_masks or {}
    opening_report = opening_report or {}
    opposites = {'front': 'back', 'back': 'front',
                 'left': 'right', 'right': 'left'}
    observations = {
        name: observe(name, views[name],
                      construction_masks[name][0] if name in construction_masks else None,
                      opposites.get(name) if opening_report.get('accepted', {}).get(name, 0)
                      else None)
        for name in selected}
    constraints = [
        {'id': item['id'], 'kind': 'opposed_mask_opening',
         'source_view': name, 'cross_view_witness': item['cross_view_witness'],
         'source_trace_id': item['id'],
         'area_source_px': item['area_source_px'],
         'appearance_median_rgb': item['appearance_median_rgb'],
         'appearance_std_rgb': item['appearance_std_rgb'],
         'status': 'construction_candidate_in_use_physical_hole_unverified'}
        for name, observed in observations.items() for item in observed['traces']
        if item['kind'] == 'opposed_mask_opening']
    side = 'right' if 'right' in observations else 'left'
    paired_sections = []
    if 'front' in observations and side in observations:
        front = observations['front']
        other = observations[side]
        for front_section, side_section in zip(
                front['observed_elevation_sections'],
                other['observed_elevation_sections']):
            front_span = front_section['outer_envelope_x_source_px']
            side_span = side_section['outer_envelope_x_source_px']
            if front_span is None or side_span is None:
                continue
            front_height = front['foreground_box_px'][3] - front['foreground_box_px'][1]
            side_height = other['foreground_box_px'][3] - other['foreground_box_px'][1]
            paired_sections.append({
                'height_fraction_from_top': front_section['height_fraction_from_top'],
                'front_trace_crossings': front_section['crossings'],
                'side_view': side, 'side_trace_crossings': side_section['crossings'],
                'width_over_height': (front_span[1] - front_span[0]) / front_height,
                'depth_over_height': (side_span[1] - side_span[0]) / side_height,
                'alignment_assumption': 'same object height and vertical axis in both source views',
                'cross_section_shape': 'unobserved',
                'status': 'paired_source_silhouette_envelopes_only',
            })
    columns = min(3, len(selected))
    rows = (len(selected) + columns - 1) // columns
    panel_w, panel_h = 510, 600
    image = Image.new('RGB', (columns * panel_w, 110 + rows * panel_h + 100), 'white')
    draw = ImageDraw.Draw(image)
    draw.text((28, 22), 'PREBUILD TECHNICAL TRACE SHEET', fill='#111111')
    draw.text((28, 52), 'Black: observed outer silhouette. Blue: traced internal boundary, depth unresolved.',
              fill='#222222')
    coordinate_transforms = {}
    for number, name in enumerate(selected):
        row, column = divmod(number, columns)
        x0, y0 = column * panel_w + 18, row * panel_h + 105
        x1, y1 = x0 + panel_w - 36, y0 + panel_h - 25
        draw.rectangle((x0, y0, x1, y1), outline='#444444', width=2)
        draw.text((x0 + 12, y0 + 12), f'{name.upper()} / SOURCE TRACE', fill='#111111')
        record = observations[name]
        w, h = record['source_size_px']
        scale = min((x1 - x0 - 42) / w, (y1 - y0 - 80) / h)
        ox = x0 + (x1 - x0 - w * scale) / 2
        oy = y0 + 40 + (y1 - y0 - 80 - h * scale) / 2
        coordinate_transforms[name] = {'sheet_xy_from_source_xy':
                                        {'scale': scale, 'offset_xy': [ox, oy]}}
        for item in record['traces']:
            points = item['points_source_xy']
            if len(points) < 2:
                continue
            mapped = [(ox + px * scale, oy + py * scale) for px, py in points]
            color = {'outer_silhouette': '#111111',
                     'internal_intensity_boundary': '#1260a8',
                     'opposed_mask_opening': '#008b51'}[item['kind']]
            draw.line(mapped, fill=color,
                      width=2 if item['kind'] != 'internal_intensity_boundary' else 1)
        for section in record['observed_elevation_sections']:
            if not any(abs(section['height_fraction_from_top'] - station) < .001
                       for station in (.15, .5, .85)):
                continue
            span = section['outer_envelope_x_source_px']
            if span is None:
                continue
            yy = oy + section['y_source_px'] * scale
            for xx in span:
                px = ox + xx * scale
                draw.line((px - 5, yy, px + 5, yy), fill='#a04a00', width=2)
        draw.text((x0 + 12, y1 - 27),
                  f"{record['outer_path_count']} outer / {record['internal_path_count']} internal / "
                  f"{record['opposed_mask_opening_count']} opposed-mask openings",
                  fill='#333333')
    footer_y = 110 + rows * panel_h
    draw.text((28, footer_y),
              'GREEN: OPPOSING MASKS AGREE; THROUGH-HOLE UNVERIFIED. NO INFERRED PROTRUSIONS.',
              fill='#008b51')
    draw.text((28, footer_y + 28),
              'ORANGE TICKS: MEASURED ELEVATION WIDTHS; INTERVENING 3D SECTION UNKNOWN.',
              fill='#a04a00')
    draw.text((28, footer_y + 56),
              'Unseen surfaces and physical meaning of internal traces require cross-view validation.',
              fill='#333333')
    report = {'schema': 1, 'stage': 'before_geometry',
              'status': 'source_observations_and_opposed_mask_openings',
              'observations': observations, 'coordinate_transforms': coordinate_transforms,
              'paired_elevation_envelopes': paired_sections,
              'geometry_inferences': [], 'build_constraints': constraints,
              'unknowns': ['internal depth', 'material or shadow versus relief',
                           'unseen geometry', 'physical scale']}
    image.save(destination / 'technical-traces.png')
    (destination / 'technical-traces.json').write_text(json.dumps(report))
    return report
