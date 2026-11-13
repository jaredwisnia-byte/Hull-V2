"""Prebuild source traces and explicitly labelled visual-hull inferences.

Observed paths stay in source pixels. Inferred section masks are projections of
the same compiled silhouettes supplied to construction, never observed cuts.
"""

import json
import hashlib
import math
from pathlib import Path
from xml.etree import ElementTree as ET

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


def _projected_section(masks, active_views, height_fraction, resolution=128):
    """Intersect compiled masks at a height, using the hull constructor frame.

    The result is the *initial visual hull* section. It does not include later
    revolutions, shading relief, smoothing, or inferred hidden cavities.
    """
    coordinate = (np.arange(resolution) + .5) / resolution
    x, y = np.meshgrid(coordinate, coordinate, indexing='xy')
    z = 1. - height_fraction

    def sample(view, u, v):
        mask = masks[view]
        h, w = mask.shape
        ix = np.clip(np.rint(u * (w - 1)).astype(int), 0, w - 1)
        iy = np.clip(np.rint(v * (h - 1)).astype(int), 0, h - 1)
        return mask[iy, ix]

    section = np.ones((resolution, resolution), bool)
    if 'front' in active_views:
        section &= sample('front', x, 1 - z)
    if 'back' in active_views:
        section &= sample('back', 1 - x, 1 - z)
    if 'right' in active_views:
        section &= sample('right', y, 1 - z)
    if 'left' in active_views:
        section &= sample('left', 1 - y, 1 - z)
    if 'top' in active_views:
        section &= sample('top', x, 1 - y)
    return section


def _write_vector_sheet(destination, image_size, selected, observations,
                        coordinate_transforms, panel_width=510, panel_height=600):
    """Export the observed trace sheet as editable vectors with source IDs."""
    namespace = 'http://www.w3.org/2000/svg'
    ET.register_namespace('', namespace)
    svg = ET.Element(f'{{{namespace}}}svg', {
        'width': str(image_size[0]), 'height': str(image_size[1]),
        'viewBox': f'0 0 {image_size[0]} {image_size[1]}'})
    ET.SubElement(svg, f'{{{namespace}}}text', {
        'x': '28', 'y': '28', 'fill': '#111111'}).text = (
            'PREBUILD SOURCE-TRACED CONSTRUCTION REFERENCE')
    ET.SubElement(svg, f'{{{namespace}}}text', {
        'x': '28', 'y': '57', 'fill': '#555555'}).text = (
            'Black: observed outline. Blue: unresolved image boundary. Hidden geometry unknown.')
    columns = min(3, len(selected))
    for number, view in enumerate(selected):
        row, column = divmod(number, columns)
        panel_x, panel_y = column * panel_width + 18, row * panel_height + 105
        ET.SubElement(svg, f'{{{namespace}}}rect', {
            'x': str(panel_x), 'y': str(panel_y),
            'width': str(panel_width - 36), 'height': str(panel_height - 25),
            'fill': 'none', 'stroke': '#444444'})
        ET.SubElement(svg, f'{{{namespace}}}text', {
            'x': str(panel_x + 12), 'y': str(panel_y + 22),
            'fill': '#111111'}).text = view.upper() + ' / SOURCE TRACE'
        transform = coordinate_transforms[view]['sheet_xy_from_source_xy']
        scale, (offset_x, offset_y) = transform['scale'], transform['offset_xy']
        for trace_record in observations[view]['traces']:
            points = trace_record['points_source_xy']
            if len(points) < 2:
                continue
            command = 'M ' + ' L '.join(
                f'{offset_x + scale * x:.2f},{offset_y + scale * y:.2f}'
                for x, y in points)
            if trace_record['kind'] == 'outer_silhouette':
                color = '#111111'
            elif trace_record['kind'] == 'opposed_mask_opening':
                color = '#008b51'
            else:
                color = '#2474c3'
            path = ET.SubElement(svg, f'{{{namespace}}}path', {
                'd': command, 'fill': 'none', 'stroke': color,
                'stroke-width': '1', 'data-source-id': trace_record['id'],
                'data-kind': trace_record['kind']})
            ET.SubElement(path, f'{{{namespace}}}title').text = (
                trace_record['physical_interpretation'])
        box = observations[view]['foreground_box_px']
        left, top = offset_x + scale * box[0], offset_y + scale * box[1]
        right, bottom = offset_x + scale * box[2], offset_y + scale * box[3]
        dimension_x = max(panel_x + 9, left - 18)
        dimension_y = min(panel_y + panel_height - 76, bottom + 18)
        for x1, y1, x2, y2 in (
                (dimension_x, top, dimension_x, bottom),
                (dimension_x - 5, top, dimension_x + 5, top),
                (dimension_x - 5, bottom, dimension_x + 5, bottom),
                (left, dimension_y, right, dimension_y),
                (left, dimension_y - 5, left, dimension_y + 5),
                (right, dimension_y - 5, right, dimension_y + 5)):
            ET.SubElement(svg, f'{{{namespace}}}line', {
                'x1': f'{x1:.2f}', 'y1': f'{y1:.2f}',
                'x2': f'{x2:.2f}', 'y2': f'{y2:.2f}',
                'stroke': '#a04a00', 'stroke-width': '1'})
        ET.SubElement(svg, f'{{{namespace}}}text', {
            'x': f'{dimension_x + 7:.2f}', 'y': f'{(top + bottom) / 2:.2f}',
            'fill': '#a04a00'}).text = f'{box[3] - box[1]} px'
        ET.SubElement(svg, f'{{{namespace}}}text', {
            'x': f'{(left + right) / 2:.2f}', 'y': f'{dimension_y - 7:.2f}',
            'fill': '#a04a00'}).text = f'{box[2] - box[0]} px'
        ET.SubElement(svg, f'{{{namespace}}}text', {
            'x': str(panel_x + 12), 'y': str(panel_y + panel_height - 55),
            'fill': '#555555'}).text = (
                f'OBSERVED BBOX {box[2] - box[0]} x {box[3] - box[1]} source px')
    ET.ElementTree(svg).write(destination, encoding='utf-8', xml_declaration=True)


def _end_frame_hypotheses(observations):
    """Compare end-view frame axes with the measured elevation extents.

    Aspect alone cannot decide 0 versus 180 degrees or prove camera pose. Keep
    both residuals as source evidence; this function never rotates an image.
    """
    side = 'right' if 'right' in observations else 'left'
    if 'front' not in observations or side not in observations:
        return {}

    def ratio(name):
        x0, y0, x1, y1 = observations[name]['foreground_box_px']
        return (x1 - x0) / (y1 - y0)

    width_over_depth = ratio('front') / ratio(side)
    result = {}
    for end in ('top', 'bottom'):
        if end not in observations:
            continue
        observed = ratio(end)
        result[end] = {
            'source_elevation_views': ['front', side],
            'expected_width_over_depth_from_elevations': width_over_depth,
            'observed_end_view_width_over_depth': observed,
            'axis_residual_log': {
                '0_or_180_degrees': abs(math.log(observed / width_over_depth)),
                '90_or_270_degrees': abs(math.log(observed * width_over_depth)),
            },
            'status': 'aspect_only; rotation, mirror and camera pose unresolved',
            'construction_use': 'diagnostic_only',
        }
    return result


def _verified_build_to_source_map(source_path, build_path, frame):
    """Accept only a lossless, pixel-checked identity or horizontal flip."""
    if not frame or frame.get('appearance_modifications'):
        return None
    mapping = frame.get('build_to_source_xy', {})
    with Image.open(source_path) as original, Image.open(build_path) as built:
        source = np.asarray(original.convert('RGB'))
        candidate = np.asarray(built.convert('RGB'))
    height, width = source.shape[:2]
    if candidate.shape != source.shape or frame.get('source_size_px') != [width, height]:
        return None
    scale = mapping.get('scale_xy')
    offset = mapping.get('offset_xy')
    if (scale, offset) == ([1, 1], [0, 0]):
        expected = source
    elif (scale, offset) == ([-1, 1], [width - 1, 0]):
        expected = source[:, ::-1]
    else:
        return None
    return mapping if np.array_equal(candidate, expected) else None


def audit_projected_elevations(drawing, projected_masks, size_xyz_m):
    """Compare exported width profiles with observed source contour crossings.

    The comparison is in width/height units and is insensitive to left/right
    mirroring. It checks the outer envelope only; no internal 3D section is
    inferred. Views lacking a source-to-build pixel map are left unresolved.
    """
    axes = {'front': 0, 'back': 0, 'left': 1, 'right': 1}
    unresolved = set(drawing.get('reconciled_views_without_source_pixel_map', ()))
    view_use = drawing.get('view_construction_use', {})
    audit = {'status': 'measured', 'views': {}, 'unresolved_views': sorted(unresolved),
             'comparison': 'source outer contour width versus exported orthographic silhouette'}
    for view, record in drawing.get('observations', {}).items():
        if view not in axes or view not in projected_masks:
            continue
        if view in unresolved or view_use.get(view, {}).get('used_for_geometry') is False:
            continue
        mask = np.asarray(projected_masks[view], bool)
        if mask.ndim != 2 or not mask.size:
            continue
        x0, y0, x1, y1 = record['foreground_box_px']
        source_height = y1 - y0
        mesh_height = float(size_xyz_m[2])
        mesh_width = float(size_xyz_m[axes[view]])
        if source_height <= 0 or mesh_height <= 0 or mesh_width <= 0:
            continue
        samples = []
        for section in record.get('observed_elevation_sections', ()):
            span = section.get('outer_envelope_x_source_px')
            if span is None or not section.get('crossing_parity_valid', False):
                continue
            fraction = section['height_fraction_from_top']
            row = min(mask.shape[0] - 1, max(0, round(fraction * mask.shape[0] - .5)))
            occupied = np.flatnonzero(mask[row])
            source_ratio = (span[1] - span[0]) / source_height
            exported_ratio = (float(np.ptp(occupied) + 1) / mask.shape[1] *
                              mesh_width / mesh_height) if len(occupied) else 0.0
            tolerance = (.02 + 2 / source_height +
                         2 * mesh_width / (mask.shape[1] * mesh_height))
            samples.append({
                'height_fraction_from_top': fraction,
                'source_width_over_height': source_ratio,
                'exported_width_over_height': exported_ratio,
                'absolute_error_in_height_units': abs(exported_ratio - source_ratio),
                'resolution_tolerance_in_height_units': tolerance,
                'outside_resolution_tolerance': abs(exported_ratio - source_ratio) > tolerance,
                'severe_outlier': abs(exported_ratio - source_ratio) > 3 * tolerance,
                'source_trace_ids': sorted({crossing['source_trace_id']
                                            for crossing in section['crossings']}),
                'exported_raster_row': row,
            })
        if samples:
            errors = [item['absolute_error_in_height_units'] for item in samples]
            audit['views'][view] = {
                'sample_count': len(samples),
                'outside_tolerance_count': sum(item['outside_resolution_tolerance']
                                               for item in samples),
                'severe_outlier_count': sum(item['severe_outlier'] for item in samples),
                'max_error_in_height_units': max(errors),
                'median_error_in_height_units': float(np.median(errors)),
                'samples': samples,
            }
    if not audit['views']:
        audit['status'] = 'no_comparable_elevation_views'
    return audit


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
            'observed_bbox_dimensions': {
                'width_source_px': int(box[2] - box[0]),
                'height_source_px': int(box[3] - box[1]),
                'units': 'source image pixels; physical scale unknown',
                'method': 'foreground mask bounding box',
                'source_trace_ids': [f'{view}:outer:{index}'
                                     for index in range(len(outer))]},
            'trace_backend': traced['tracing_backend'],
            'traces': records,
            'observed_elevation_sections': sections,
            'outer_path_count': len(outer),
            'internal_path_count': sum(r['kind'] == 'internal_intensity_boundary'
                                       for r in records),
            'opposed_mask_opening_count': sum(r['kind'] == 'opposed_mask_opening'
                                           for r in records)}


def infer(views, destination, construction_masks=None, opening_report=None,
          view_consistency=None, geometry_views=None, source_views=None,
          source_sheet_frames=None, compile_construction_masks=False,
          estimated_height_m=None):
    """Create the first-station drawing and JSON from arbitrary labelled views."""
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    selected = [name for name in ('front', 'right', 'left', 'back', 'top', 'bottom')
                if name in views]
    if not selected:
        raise ValueError('At least one labelled source view is required')
    if estimated_height_m is not None and not (
            np.isfinite(estimated_height_m) and estimated_height_m > 0):
        raise ValueError('Drawing height estimate must be positive and finite')
    construction_masks = construction_masks or {}
    opening_report = opening_report or {}
    source_views = source_views or views
    view_consistency = view_consistency or {}
    proposed_paint_only = set(view_consistency.get('paint_only', ()))
    opposites = {'front': 'back', 'back': 'front',
                 'left': 'right', 'right': 'left'}
    build_observations = {
        name: observe(name, views[name],
                      construction_masks[name][0] if name in construction_masks else None,
                      opposites.get(name) if opening_report.get('accepted', {}).get(name, 0)
                      else None)
        for name in selected}
    compiled_masks = {}
    if compile_construction_masks:
        mask_folder = destination / 'construction-masks'
        mask_folder.mkdir(exist_ok=True)
        for name in selected:
            mask, painting, box = silhouette(views[name], with_box=True)
            if name in construction_masks:
                supplied = construction_masks[name][0]
                if supplied.shape != mask.shape:
                    raise ValueError(f'{name}: construction mask differs from drawing frame')
                mask = supplied
            mask_path = mask_folder / f'{name}.png'
            Image.fromarray(mask.astype(np.uint8) * 255).save(mask_path)
            compiled_masks[name] = {
                'path': str(mask_path), 'build_input_path': str(views[name]),
                'build_input_sha256': hashlib.sha256(Path(views[name]).read_bytes()).hexdigest(),
                'mask_sha256': hashlib.sha256(mask_path.read_bytes()).hexdigest(),
                'foreground_box_px': list(map(int, box)),
            }
    changed_frames = [name for name in selected
                      if str(source_views.get(name, views[name])) != str(views[name])]
    verified_maps = {}
    for name in changed_frames:
        mapping = _verified_build_to_source_map(
            source_views[name], views[name],
            view_consistency.get('pixel_frames', {}).get(name))
        if mapping is not None:
            verified_maps[name] = mapping
    unresolved_frames = [name for name in changed_frames if name not in verified_maps]
    for name in changed_frames:
        for item in build_observations[name]['traces']:
            item['id'] = f"build_input:{item['id']}"
        for section in build_observations[name]['observed_elevation_sections']:
            for crossing in section['crossings']:
                crossing['source_trace_id'] = f"build_input:{crossing['source_trace_id']}"
    for name in compiled_masks:
        compiled_masks[name]['outer_build_trace_ids'] = [
            item['id'] for item in build_observations[name]['traces']
            if item['kind'] == 'outer_silhouette']
    observations = dict(build_observations)
    for name in changed_frames:
        observations[name] = observe(name, source_views[name])
    for name, frame in (source_sheet_frames or {}).items():
        if name in observations:
            observations[name]['source_sheet_frame'] = frame
            for trace in observations[name]['traces']:
                trace['source_sheet_frame'] = frame
    view_use = {}
    for name in selected:
        used = None if geometry_views is None else name in geometry_views
        proposed = name in proposed_paint_only
        view_use[name] = {
            'used_for_geometry': used,
            'preflight_proposes_paint_only': proposed,
            'preflight_proportion_off_pct': view_consistency.get(
                'views', {}).get(name, {}).get('off_pct'),
            'conflict_in_use': bool(used and proposed),
            'preflight_is_diagnostic_only': bool(view_consistency),
            'original_source_path': str(source_views.get(name, views[name])),
            'build_input_path': str(views[name]),
            'build_input_differs_from_source': name in changed_frames,
            'build_to_source_pixel_map': (
                verified_maps.get(name) if name in changed_frames else
                {'scale_xy': [1, 1], 'offset_xy': [0, 0]}),
            'source_pixel_map_verified': name not in unresolved_frames,
        }
        observations[name]['construction_use'] = view_use[name]
    conflicts = [name for name, status in view_use.items()
                 if status['conflict_in_use']]
    frame_hypotheses = _end_frame_hypotheses(observations)
    constraints = [
        {'id': item['id'], 'kind': 'opposed_mask_opening',
         'source_view': name, 'cross_view_witness': item['cross_view_witness'],
         'source_trace_id': item['id'] if name not in changed_frames else None,
         'build_input_trace_id': item['id'],
         'area_source_px': item['area_source_px'] if name not in changed_frames else None,
         'area_build_input_px': item['area_source_px'] if name in changed_frames else None,
         'measurement_pixel_frame': ('reconciled_build_input' if name in changed_frames
                                     else 'original_source'),
         'mapped_original_source_xy': (
             [[mapping['scale_xy'][0] * x + mapping['offset_xy'][0],
               mapping['scale_xy'][1] * y + mapping['offset_xy'][1]]
              for x, y in item.get('points_source_xy', ())]
             if (mapping := verified_maps.get(name)) is not None else None),
         'appearance_median_rgb': item['appearance_median_rgb'],
         'appearance_std_rgb': item['appearance_std_rgb'],
         'status': ('construction_candidate_in_use_physical_hole_unverified'
                    if name not in changed_frames else
                    'build_input_candidate_original_source_mapping_unresolved')}
        for name, observed in build_observations.items() for item in observed['traces']
        if item['kind'] == 'opposed_mask_opening']
    side = 'right' if 'right' in observations else 'left'
    paired_sections = []
    frames = source_sheet_frames or {}
    repeated_pair = ('front' in frames and side in frames and
                     frames['front'].get('source_region_id') ==
                     frames[side].get('source_region_id'))
    if 'front' in observations and side in observations and not repeated_pair:
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
    section_records = []
    if paired_sections and compiled_masks:
        # Draw measured section *envelopes* before construction. The dashed
        # rectangle is a bound from two elevations, not a guessed cut face.
        stations = [min(paired_sections, key=lambda item: abs(
            item['height_fraction_from_top'] - fraction))
            for fraction in (.05, .25, .5, .75, .95)]
        section_sheet = Image.new('RGB', (1100, 190 * len(stations) + 105), 'white')
        section_draw = ImageDraw.Draw(section_sheet)
        section_draw.text((24, 18), 'PREBUILD SECTION ENVELOPES / SOURCE MEASUREMENTS',
                          fill='#111111')
        section_draw.text((24, 44),
                          'Gray: inferred initial visual hull. Dashed box: observed limits. Hidden cut profile unknown.',
                          fill='#555555')
        section_masks = {name: np.asarray(Image.open(item['path']).convert('L')) > 127
                         for name, item in compiled_masks.items()}
        active_views = set(geometry_views) if geometry_views is not None else set(selected)
        overall_width = (observations['front']['foreground_box_px'][2] -
                         observations['front']['foreground_box_px'][0]) / (
                             observations['front']['foreground_box_px'][3] -
                             observations['front']['foreground_box_px'][1])
        overall_depth = (observations[side]['foreground_box_px'][2] -
                         observations[side]['foreground_box_px'][0]) / (
                             observations[side]['foreground_box_px'][3] -
                             observations[side]['foreground_box_px'][1])
        for index, station in enumerate(stations):
            y0 = 80 + 190 * index
            fraction = station['height_fraction_from_top']
            width = station['width_over_height']
            depth = station['depth_over_height']
            section_draw.text((24, y0), f'SECTION {index + 1} / {fraction:.0%} FROM TOP',
                              fill='#111111')
            section_draw.text((24, y0 + 25),
                              f'WIDTH / HEIGHT {width:.3f}    DEPTH / HEIGHT {depth:.3f}',
                              fill='#a04a00')
            if estimated_height_m is not None:
                section_draw.text((24, y0 + 75),
                                  f'ESTIMATED W {1000 * width * estimated_height_m:.1f} mm'
                                  f'    D {1000 * depth * estimated_height_m:.1f} mm',
                                  fill='#a04a00')
            section_draw.text((24, y0 + 50),
                              f'Front trace: {station["front_trace_crossings"][0]["source_trace_id"]}'
                              f'    {side.title()} trace: '
                              f'{station["side_trace_crossings"][0]["source_trace_id"]}',
                              fill='#555555')
            cx, cy = 820, y0 + 86
            scale = 110 / max(overall_width, overall_depth, 1e-6)
            half_w, half_d = width * scale / 2, depth * scale / 2
            section = _projected_section(
                section_masks, active_views, fraction)
            section_path = destination / f'construction-section-{index + 1}.png'
            Image.fromarray(section.astype(np.uint8) * 255).save(section_path)
            section_records.append({
                'height_fraction_from_top': fraction,
                'mask_path': str(section_path),
                'mask_sha256': hashlib.sha256(section_path.read_bytes()).hexdigest(),
                'construction_views': sorted(active_views & set(section_masks)),
                'source_front_trace_ids': sorted({crossing['source_trace_id']
                    for crossing in station['front_trace_crossings']}),
                'source_side_trace_ids': sorted({crossing['source_trace_id']
                    for crossing in station['side_trace_crossings']}),
                'status': 'inferred_initial_visual_hull_section_not_observed_cut',
                'estimated_width_m': (width * estimated_height_m
                                      if estimated_height_m is not None else None),
                'estimated_depth_m': (depth * estimated_height_m
                                      if estimated_height_m is not None else None),
            })
            display = Image.fromarray(np.where(section, 75, 255).astype(np.uint8))
            display = display.resize((max(1, round(overall_width * scale)),
                                      max(1, round(overall_depth * scale))),
                                     Image.Resampling.NEAREST)
            section_sheet.paste(display.convert('RGB'),
                                (round(cx - display.width / 2),
                                 round(cy - display.height / 2)))
            section_draw.line((cx - 75, cy, cx + 75, cy), fill='#6c8ca0')
            section_draw.line((cx, cy - 75, cx, cy + 75), fill='#6c8ca0')
            for x0, yy, x1, y1 in ((cx - half_w, cy - half_d, cx + half_w, cy - half_d),
                                   (cx + half_w, cy - half_d, cx + half_w, cy + half_d),
                                   (cx + half_w, cy + half_d, cx - half_w, cy + half_d),
                                   (cx - half_w, cy + half_d, cx - half_w, cy - half_d)):
                length = max(abs(x1 - x0), abs(y1 - yy))
                for step in range(0, int(length), 12):
                    a, b = step / length, min(step + 6, length) / length
                    section_draw.line((x0 + (x1 - x0) * a, yy + (y1 - yy) * a,
                                       x0 + (x1 - x0) * b, yy + (y1 - yy) * b),
                                      fill='#a04a00', width=2)
            section_draw.line((24, y0 + 167, 1076, y0 + 167), fill='#cccccc')
        section_draw.text((24, section_sheet.height - 23),
                          'Physical scale and hidden material are unobserved; no cut profile is asserted.',
                          fill='#555555')
        section_sheet.save(destination / 'construction-sections.png')
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
        if view_use[name]['conflict_in_use']:
            draw.text((x0 + 12, y0 + 29),
                      'PREFLIGHT CONFLICT: VIEW STILL USED FOR GEOMETRY',
                      fill='#b00020')
        if name in changed_frames:
            draw.text((x0 + 12, y0 + 45),
                      ('ORIGINAL SOURCE SHOWN; BUILD FLIP PIXELS VERIFIED'
                       if name in verified_maps else
                       'ORIGINAL SOURCE SHOWN; BUILD PIXEL MAP UNRESOLVED'),
                      fill='#b00020')
        record = observations[name]
        w, h = record['source_size_px']
        header_height = 70 if name in changed_frames else 40
        scale = min((x1 - x0 - 58) / w, (y1 - y0 - header_height - 112) / h)
        ox = x0 + (x1 - x0 - w * scale) / 2
        oy = y0 + header_height + (y1 - y0 - header_height - 112 - h * scale) / 2
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
        bx0, by0, bx1, by1 = record['foreground_box_px']
        left, right = ox + bx0 * scale, ox + bx1 * scale
        top, bottom = oy + by0 * scale, oy + by1 * scale
        dimension_x = max(x0 + 8, left - 14)
        dimension_y = min(y1 - 86, bottom + 12)
        draw.line((dimension_x, top, dimension_x, bottom), fill='#555555')
        draw.line((dimension_x - 4, top, dimension_x + 4, top), fill='#555555')
        draw.line((dimension_x - 4, bottom, dimension_x + 4, bottom), fill='#555555')
        draw.line((left, dimension_y, right, dimension_y), fill='#555555')
        draw.line((left, dimension_y - 4, left, dimension_y + 4), fill='#555555')
        draw.line((right, dimension_y - 4, right, dimension_y + 4), fill='#555555')
        measured_widths = []
        for station in (.15, .5, .85):
            section = next((item for item in record['observed_elevation_sections']
                            if abs(item['height_fraction_from_top'] - station) < .001), None)
            span = section.get('outer_envelope_x_source_px') if section else None
            measured_widths.append('?' if span is None else f'{span[1] - span[0]:.1f}')
        draw.text((x0 + 12, y1 - 75),
                  f'SOURCE BBOX: W {bx1 - bx0} px  H {by1 - by0} px', fill='#333333')
        if record['observed_elevation_sections']:
            draw.text((x0 + 12, y1 - 59),
                      'TRACE WIDTHS @ 15/50/85% H: ' + ' / '.join(measured_widths) + ' px',
                      fill='#a04a00')
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
              'Source-pixel dimensions only; physical scale and unseen surfaces remain unknown.',
              fill='#333333')
    report = {'schema': 1, 'stage': 'before_geometry',
              'status': 'source_observations_and_opposed_mask_openings',
              'observations': observations, 'coordinate_transforms': coordinate_transforms,
              'paired_elevation_envelopes': paired_sections,
              'physical_scale': {'estimated_height_m': estimated_height_m,
                                 'status': ('order_estimate_not_source_measurement'
                                            if estimated_height_m is not None else
                                            'unknown')},
              'inferred_visual_hull_sections': section_records,
              'section_envelope_sheet': (str(destination / 'construction-sections.png')
                                         if section_records else None),
              'unresolved_view_pairs_same_source_region':
                  [['front', side]] if repeated_pair else [],
              'view_construction_use': view_use,
              'view_conflicts_in_use': conflicts,
              'reconciled_views_without_source_pixel_map': unresolved_frames,
              'reconciled_views_with_verified_source_pixel_map': list(verified_maps),
              'reconciliation_pixel_frames': {
                  name: view_consistency.get('pixel_frames', {}).get(name)
                  for name in changed_frames},
              'reconciled_build_input_observations': {
                  name: build_observations[name] for name in changed_frames},
              'compiled_construction_masks': compiled_masks,
              'construction_constraints': [
                  {'id': f'compiled_silhouette:{name}',
                   'kind': 'orthographic_source_mask',
                   'build_input_sha256': item['build_input_sha256'],
                   'mask_sha256': item['mask_sha256'],
                   'source_trace_ids': item['outer_build_trace_ids'],
                   'used_for_geometry': view_use[name]['used_for_geometry'],
                   'source_pixel_map_verified': view_use[name]['source_pixel_map_verified'],
                   'physical_interpretation': 'visible outer envelope only'}
                  for name, item in compiled_masks.items()],
              'end_view_frame_hypotheses': frame_hypotheses,
              'geometry_inferences': [], 'build_constraints': constraints,
              'unknowns': ['internal depth', 'material or shadow versus relief',
                           'unseen geometry', 'physical scale']}
    image.save(destination / 'technical-traces.png')
    _write_vector_sheet(destination / 'technical-traces.svg', image.size,
                        selected, observations, coordinate_transforms)
    report['vector_sheet'] = str(destination / 'technical-traces.svg')
    (destination / 'technical-traces.json').write_text(json.dumps(report))
    return report


def load_construction_masks(drawing_path, views):
    """Use recorded prebuild silhouettes only for unchanged, matching input pixels."""
    drawing = json.loads(Path(drawing_path).read_text())
    masks, use = {}, {}
    for view, path in views.items():
        record = drawing.get('compiled_construction_masks', {}).get(view)
        if record is None:
            raise ValueError(f'{view}: prebuild drawing lacks a compiled construction mask')
        digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
        if digest != record['build_input_sha256']:
            raise ValueError(f'{view}: build input changed after technical tracing')
        if hashlib.sha256(Path(record['path']).read_bytes()).hexdigest() != record['mask_sha256']:
            raise ValueError(f'{view}: compiled drawing mask changed after tracing')
        box = record['foreground_box_px']
        mask = np.asarray(Image.open(record['path']).convert('L')) > 127
        if mask.shape != (box[3] - box[1], box[2] - box[0]):
            raise ValueError(f'{view}: compiled drawing mask has wrong dimensions')
        painting = Image.open(path).convert('RGB').crop(tuple(box))
        masks[view] = (mask, painting)
        source_use = drawing.get('view_construction_use', {}).get(view, {})
        use[view] = {
            'build_trace_ids': record['outer_build_trace_ids'],
            'original_source_path': source_use.get('original_source_path'),
            'source_pixel_map_verified': source_use.get('source_pixel_map_verified'),
            'construction_mask_path': record['path'],
            'construction_mask_sha256': record['mask_sha256'],
            'build_input_sha256': record['build_input_sha256'],
            'used_for_geometry': source_use.get('used_for_geometry'),
        }
    return masks, use


def compile_relief_trace(drawing_path, view, image_path, mask, valid, painting):
    """Record the exact post-exclusion shading boundaries before meshing."""
    drawing_path = Path(drawing_path)
    drawing = json.loads(drawing_path.read_text())
    record = drawing['compiled_construction_masks'][view]
    if hashlib.sha256(Path(image_path).read_bytes()).hexdigest() != record['build_input_sha256']:
        raise ValueError(f'{view}: build input changed after technical tracing')
    mask_path = Path(record['path'])
    if hashlib.sha256(mask_path.read_bytes()).hexdigest() != record['mask_sha256']:
        raise ValueError(f'{view}: compiled drawing mask changed after tracing')
    saved_mask = np.asarray(Image.open(mask_path).convert('L')) > 127
    if not np.array_equal(saved_mask, mask):
        raise ValueError(f'{view}: relief input mask differs from prebuild drawing')
    if valid.shape != mask.shape or np.any(valid & ~mask):
        raise ValueError(f'{view}: valid shading region lies outside drawing mask')
    if np.count_nonzero(valid) < 25:
        record.pop('relief_trace', None)
        drawing_path.write_text(json.dumps(drawing))
        return None
    from .joint_shading import prepare_image_trace
    traced = prepare_image_trace(painting, valid)['traced']
    arrays = {key: value for key, value in traced.items()
              if isinstance(value, np.ndarray)}
    metadata = {key: value for key, value in traced.items()
                if not isinstance(value, np.ndarray)}
    arrays_path = mask_path.with_name(f'{view}-relief-trace.npz')
    metadata_path = mask_path.with_name(f'{view}-relief-trace.json')
    np.savez_compressed(arrays_path, **arrays)
    metadata_path.write_text(json.dumps(metadata))
    overlay_path = mask_path.with_name(f'{view}-relief-boundaries.png')
    overlay = np.asarray(painting.convert('RGB').resize(
        arrays['boundaries'].shape[::-1])).copy()
    overlay[arrays['appearance_boundaries']] = [255, 150, 40]
    overlay[arrays['relief_boundaries']] = [40, 255, 130]
    overlay[arrays['fine_candidates']] = [55, 205, 255]
    Image.fromarray(overlay).save(overlay_path)
    record['relief_trace'] = {
        'arrays': str(arrays_path), 'metadata': str(metadata_path),
        'arrays_sha256': hashlib.sha256(arrays_path.read_bytes()).hexdigest(),
        'metadata_sha256': hashlib.sha256(metadata_path.read_bytes()).hexdigest(),
        'valid_mask_sha256': hashlib.sha256(np.packbits(valid).tobytes()).hexdigest(),
        'input_mask_shape': list(mask.shape),
        'boundary_pixel_count': int(arrays['boundaries'].sum()),
        'overlay': str(overlay_path),
        'legend': {'green': 'persistent achromatic boundary; depth sign unresolved',
                   'orange': 'boundary with colour ambiguity',
                   'cyan': 'fine candidate; weak curvature evidence only'},
        'role': 'prebuild internal boundaries guide shading regularization; depth sign unresolved',
    }
    drawing_path.write_text(json.dumps(drawing))
    return traced


def load_relief_trace(drawing_path, view, image_path, mask, valid):
    """Load prebuild boundary evidence only in its measured image frame."""
    drawing = json.loads(Path(drawing_path).read_text())
    record = drawing['compiled_construction_masks'][view]
    packet = record.get('relief_trace')
    if packet is None:
        return None
    if hashlib.sha256(Path(image_path).read_bytes()).hexdigest() != record['build_input_sha256']:
        raise ValueError(f'{view}: build input changed after technical tracing')
    mask_path = Path(record['path'])
    if hashlib.sha256(mask_path.read_bytes()).hexdigest() != record['mask_sha256']:
        raise ValueError(f'{view}: compiled drawing mask changed after tracing')
    saved_mask = np.asarray(Image.open(mask_path).convert('L')) > 127
    if not np.array_equal(saved_mask, mask):
        raise ValueError(f'{view}: relief input mask differs from prebuild drawing')
    if valid.shape != mask.shape or list(valid.shape) != packet['input_mask_shape']:
        raise ValueError(f'{view}: shading valid region has wrong drawing frame')
    if hashlib.sha256(np.packbits(valid).tobytes()).hexdigest() != packet['valid_mask_sha256']:
        raise ValueError(f'{view}: shading valid region differs from prebuild trace')
    arrays_path, metadata_path = Path(packet['arrays']), Path(packet['metadata'])
    if (hashlib.sha256(arrays_path.read_bytes()).hexdigest() != packet['arrays_sha256'] or
            hashlib.sha256(metadata_path.read_bytes()).hexdigest() != packet['metadata_sha256']):
        raise ValueError(f'{view}: prebuild relief trace changed after tracing')
    with np.load(arrays_path, allow_pickle=False) as saved:
        result = {key: saved[key] for key in saved.files}
    result.update(json.loads(metadata_path.read_text()))
    return result


def infer_sheet_regions(sheet_path, records, regions, destination):
    """Trace exact source-sheet crops for assembly and companion view groups.

    The assigned orthographic view name is an intake hypothesis. Crop-local
    paths retain a translation back to the original sheet; no prepared-view
    paint, erased background or rotation is presented as an original pixel.
    """
    sheet_path = Path(sheet_path).resolve()
    sheet = Image.open(sheet_path).convert('RGB')
    by_id = {region['id']: region for region in regions}
    destination = Path(destination)
    results = {}
    for group, record in records.items():
        if Path(group).name != group or group in ('.', '..'):
            raise ValueError('Unsafe source drawing group name')
        raw_folder = destination / group / 'source-crops'
        raw_folder.mkdir(parents=True, exist_ok=True)
        raw_views, frames = {}, {}
        for view, identifier in record.get('views', {}).items():
            if view not in ('front', 'back', 'left', 'right', 'top', 'bottom'):
                continue
            region = by_id[identifier]
            box = tuple(map(int, region['box']))
            if not (0 <= box[0] < box[2] <= sheet.width and
                    0 <= box[1] < box[3] <= sheet.height):
                raise ValueError('Source region lies outside the original sheet')
            path = raw_folder / f'v_{view}.png'
            sheet.crop(box).save(path)
            raw_views[view] = str(path)
            frames[view] = {
                'original_sheet_path': str(sheet_path),
                'source_region_id': identifier,
                'source_crop_box_sheet_px': list(box),
                'sheet_xy_from_crop_xy': {'scale_xy': [1, 1],
                                          'offset_xy': [box[0], box[1]]},
                'view_assignment': ('source_caption' if group == 'assembly' else
                                    'automatic_companion_view_hypothesis'),
            }
        if not raw_views:
            continue
        result_folder = destination / group
        drawing = infer(raw_views, result_folder, source_sheet_frames=frames)
        reused = sorted({identifier for identifier in record.get('views', {}).values()
                         if list(record.get('views', {}).values()).count(identifier) > 1})
        drawing['original_sheet_path'] = str(sheet_path)
        drawing['source_region_reused_for_multiple_view_labels'] = reused
        drawing['source_kind'] = 'unaltered crop of original supplied sheet'
        trace_path = result_folder / 'technical-traces.json'
        trace_path.write_text(json.dumps(drawing))
        results[group] = {'sheet': str(result_folder / 'technical-traces.png'),
                          'traces': str(trace_path), 'source_views': raw_views,
                          'source_sheet_frames': frames,
                          'reused_source_regions': reused}
    return results
