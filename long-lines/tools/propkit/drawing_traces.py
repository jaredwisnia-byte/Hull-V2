"""Prebuild drafting evidence: only paths traced in the supplied views.

This deliberately does not create solids, fit circles, or infer depth. A later
cross-view solver may consume these paths, but must record its own inferences.
"""

import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from skimage.measure import find_contours

from .feature_curves import paths
from .feature_regions import trace
from .silhouette import silhouette


def _linear_rgb(pixels):
    color = np.asarray(pixels, np.float32) / 255.0
    return np.where(color <= .04045, color / 12.92,
                    ((color + .055) / 1.055) ** 2.4)


def observe(view, path):
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
    return {'view': view, 'source_path': str(path),
            'source_size_px': [image.width, image.height],
            'foreground_box_px': list(map(int, box)),
            'trace_backend': traced['tracing_backend'],
            'traces': records,
            'outer_path_count': len(outer),
            'internal_path_count': sum(r['kind'] == 'internal_intensity_boundary'
                                       for r in records)}


def infer(views, destination):
    """Create the first-station drawing and JSON from arbitrary labelled views."""
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    selected = [name for name in ('front', 'right', 'left', 'back', 'top', 'bottom')
                if name in views]
    if not selected:
        raise ValueError('At least one labelled source view is required')
    observations = {name: observe(name, views[name]) for name in selected}
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
            color = '#111111' if item['kind'] == 'outer_silhouette' else '#1260a8'
            draw.line(mapped, fill=color,
                      width=2 if item['kind'] == 'outer_silhouette' else 1)
        draw.text((x0 + 12, y1 - 27),
                  f"{record['outer_path_count']} outer / {record['internal_path_count']} internal paths",
                  fill='#333333')
    footer_y = 110 + rows * panel_h
    draw.text((28, footer_y), 'NO INFERRED HOLES, PROTRUSIONS, SECTION CUTS OR DIMENSIONS', fill='#9a2626')
    draw.text((28, footer_y + 28),
              'Unseen surfaces and physical meaning of internal traces require cross-view validation.',
              fill='#333333')
    report = {'schema': 1, 'stage': 'before_geometry',
              'status': 'observations_only_not_build_constraints',
              'observations': observations, 'coordinate_transforms': coordinate_transforms,
              'geometry_inferences': [], 'build_constraints': [],
              'unknowns': ['internal depth', 'material or shadow versus relief',
                           'unseen geometry', 'physical scale']}
    image.save(destination / 'technical-traces.png')
    (destination / 'technical-traces.json').write_text(json.dumps(report))
    return report
