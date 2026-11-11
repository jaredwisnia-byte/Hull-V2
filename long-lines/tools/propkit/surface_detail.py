"""Object-independent surface evidence and continuous implicit detail.

Construction patches are computational regions of one physical surface. They
never become capped objects merely because width or curvature changes. All
lengths passed to the field station are metres; source observations stay in
their own image frame until sampling.
"""
import numpy as np
from scipy import ndimage

VIEWS = {'front': (1, False), 'back': (1, True),
         'right': (0, True), 'left': (0, False),
         'top': (2, True), 'bottom': (2, False)}


def visible_root(field, axis, reverse, span):
    stack = np.moveaxis(field, axis, 0)
    if reverse:
        stack = stack[::-1]
    occupied = stack < 0
    first = occupied.argmax(0)
    previous = np.maximum(0, first - 1)
    a = np.take_along_axis(stack, previous[None], axis=0)[0]
    b = np.take_along_axis(stack, first[None], axis=0)[0]
    step = span / field.shape[axis]
    fraction = np.clip(a / np.maximum(a - b, 1e-12), 0, 1)
    root = np.where(first == 0, 0, (previous + fraction + .5) * step)
    slope = np.where(first == 0, (stack[0] - stack[1]) / step, (a - b) / step)
    last = len(stack) - 1 - occupied[::-1].argmax(0)
    return root, slope, (last - first + 1) * step, occupied.any(0)


def root_image(root, view, dimensions, field_shape, image_shape):
    hh, ww = image_shape
    yy, xx = np.mgrid[:hh, :ww]
    u, v = (xx + .5) / ww, (yy + .5) / hh
    if view in ('back', 'left'):
        u = 1 - u
    axis, _ = VIEWS[view]
    transverse = [i for i in range(3) if i != axis]
    other = v if view == 'bottom' else 1 - v
    indices = np.array([u * field_shape[transverse[0]] - .5,
                       other * field_shape[transverse[1]] - .5])
    return ndimage.map_coordinates(root, indices, order=1, mode='nearest')


def chart_frame(view, dimensions):
    w, d, h = dimensions
    return {'front': ([-w / 2, -d / 2, h], [w, 0, 0], [0, 0, -h], [0, -1, 0]),
            'back': ([w / 2, d / 2, h], [-w, 0, 0], [0, 0, -h], [0, 1, 0]),
            'right': ([w / 2, -d / 2, h], [0, d, 0], [0, 0, -h], [1, 0, 0]),
            'left': ([-w / 2, d / 2, h], [0, -d, 0], [0, 0, -h], [-1, 0, 0]),
            'top': ([-w / 2, d / 2, h], [w, 0, 0], [0, -d, 0], [0, 0, 1]),
            'bottom': ([-w / 2, -d / 2, 0], [w, 0, 0], [0, d, 0], [0, 0, -1])}[view]


def analyse(views, dimensions, report, exclusions=()):
    """Prepare pixel observations. Geometry is inferred after the base field exists.

    No circle recognition, primitive selection or fixed groove profiles run here.
    The visible field supplies the initial surface and boundary conditions.
    """
    from .hull import silhouette
    maps, inputs = {}, {}
    for view, path in views.items():
        if view not in VIEWS:
            continue
        mask, image, box = silhouette(path, with_box=True)
        valid = ndimage.binary_erosion(mask, iterations=3)
        for excluded_view, box in exclusions:
            if view == excluded_view:
                a, b, c, d = box
                hh, ww = mask.shape
                valid[max(0, int(b * hh) - 2):min(hh, int(np.ceil(d * hh)) + 2),
                      max(0, int(a * ww) - 2):min(ww, int(np.ceil(c * ww)) + 2)] = False
        maps[view] = np.zeros(mask.shape)
        inputs[view] = {'image': image, 'valid': valid,
                        'path': path, 'crop_box': box}
    report.update(features=[], views={}, method='continuous pixel shading/height inference',
                  physical_separation='physical ownership only; shading contours do not create parts')
    return {'maps': maps, 'fine_maps': {}, 'shading_inputs': inputs,
            'dimensions': tuple(dimensions), 'report': report}


def shading_view(root, view, plan, shape):
    """Map the visible coarse surface to image pixels and solve its relief."""
    from . import shading
    observation = plan['shading_inputs'][view]
    mask = observation['valid']
    hh, ww = mask.shape
    axis, _ = VIEWS[view]
    transverse = [i for i in range(3) if i != axis]
    depth = root_image(root, view, plan['dimensions'], shape, mask.shape)
    span = plan['dimensions'][transverse[0]]
    pixel = span / ww
    base = -depth / pixel
    # A physical safety bound is not a measured depth. The solver reports it.
    bound = min(plan['dimensions']) * .04 / pixel
    diagnostics = {}
    height, evidence = shading.reconstruct(
        observation['image'], mask, base, bound, diagnostics=diagnostics)
    diagnostics['metres_per_pixel'] = np.asarray(pixel)
    plan.setdefault('diagnostics', {})[view] = diagnostics
    plan['report']['views'][view] = evidence
    print('SHADING_VIEW', view, evidence, flush=True)
    before = len(plan['report']['features'])
    curvature_probes(height, mask, view, plan['report'])
    from .depth_measurement import estimate
    for feature in plan['report']['features'][before:]:
        for probe in feature['probes']:
            center = np.asarray(probe['center_px'])
            normal = np.asarray(probe['normal_px'])
            span = probe['sample_span_px']
            probe['depth_estimate'] = estimate(height,
                                               [center, center - normal * span,
                                                   center + normal * span], pixel, evidence,
                                               scale_status=plan.get('physical_scale_status', 'estimated'))
    return height * pixel


def curvature_probes(height, mask, view, report):
    """Sample continuous curvature for validation, without classifying its shape."""
    from skimage.feature import peak_local_max
    if min(height.shape) < 3 or not np.any(mask):
        return
    # These samples validate the inferred field; they never generate primitives
    # or feed point-shaped dents back into the reconstruction.
    smooth = ndimage.gaussian_filter(height, 1.)
    gy, gx = np.gradient(smooth)
    hyy, hxy = np.gradient(gy)
    _, hxx = np.gradient(gx)
    delta = np.sqrt((hxx - hyy)**2 + 4 * hxy * hxy)
    largest = (hxx + hyy + delta) / 2
    smallest = (hxx + hyy - delta) / 2
    curvature = np.where(abs(largest) >= abs(smallest), largest, smallest)
    angle = .5 * np.arctan2(2 * hxy, hxx - hyy)
    angle += np.where(abs(largest) >= abs(smallest), 0, np.pi / 2)
    threshold = max(1e-4, float(np.percentile(abs(curvature)[mask], 90)) * .25)
    peaks = peak_local_max(abs(curvature) * mask, min_distance=5,
                           threshold_abs=threshold, num_peaks=96)
    for row, col in peaks:
        radius = np.clip(
            np.sqrt(abs(height[row, col]) / max(abs(curvature[row, col]), 1e-6)), 2, 16)
        normal = np.array([np.cos(angle[row, col]), np.sin(angle[row, col])])
        points = np.asarray(
            [[col, row], [col, row] - normal * radius, [col, row] + normal * radius])
        values = ndimage.map_coordinates(
            height, points[:, ::-1].T, order=1, mode='nearest')
        contrast = values[0] - np.mean(values[1:])
        if abs(contrast) < .15:
            continue
        report['features'].append({'id': f'surface_{len(report["features"]):03d}',
                                   'view': view, 'kind': 'shading', 'sign': float(np.sign(contrast)),
                                   'probes': [{'center_px': [float(col), float(row)], 'normal_px': normal.tolist(),
                                               'radius_px': float(radius), 'sample_span_px': float(radius)}],
                                   'evidence': 'extremum of continuous inferred surface curvature; no shape classification'})


def _mapping(view, dimensions, shape):
    """Image-normalized coordinates on the field's two transverse grid axes."""
    nx, ny, nz = shape
    x = (np.arange(nx) + .5) / nx
    y = (np.arange(ny) + .5) / ny
    z = (np.arange(nz) + .5) / nz
    if view == 'front':
        return np.meshgrid(x, 1 - z, indexing='ij')
    if view == 'back':
        return np.meshgrid(1 - x, 1 - z, indexing='ij')
    if view == 'right':
        return np.meshgrid(y, 1 - z, indexing='ij')
    if view == 'left':
        return np.meshgrid(1 - y, 1 - z, indexing='ij')
    if view == 'top':
        return np.meshgrid(x, 1 - y, indexing='ij')
    return np.meshgrid(x, y, indexing='ij')


def apply_field(field, plan):
    """Local signed-field offsets on the visible skin, before isosurface extraction.

    Uses metric root positions and directional derivatives. Opposite skins are
    protected by compact depth support; computational patches share vertices
    in the one extracted surface, with no cut caps or region normal seams.
    """
    field = np.asarray(field, dtype=np.float32)
    dimensions = plan['dimensions']
    bounds = [(-dimensions[0] / 2, dimensions[0] / 2),
              (-dimensions[1] / 2, dimensions[1] / 2), (0, dimensions[2])]
    plan['report']['probes'] = []
    plan['report']['unobservable_probes'] = 0
    observations = []
    for view, height_map in plan['maps'].items():
        axis, reverse = VIEWS[view]
        stack = np.moveaxis(field, axis, 0)
        if reverse:
            stack = stack[::-1]
        occupied = stack < 0
        has_surface = occupied.any(0)
        visible_surface = has_surface.astype(float)
        first = occupied.argmax(0)
        previous = np.maximum(0, first - 1)
        a = np.take_along_axis(stack, previous[None], axis=0)[0]
        b = np.take_along_axis(stack, first[None], axis=0)[0]
        fraction = np.clip(a / np.maximum(a - b, 1e-12), 0, 1)
        spacing = dimensions[axis] / field.shape[axis]
        root = (previous + fraction + .5) * spacing
        root = np.where(first == 0, 0, root)
        raw_slope = (a - b) / spacing
        raw_slope = np.where(
            first == 0, (stack[0] - stack[1]) / spacing, raw_slope)
        slope = np.clip(raw_slope, .1, 2.)
        if 'shading_inputs' in plan:
            height_map = shading_view(root, view, plan, field.shape)
            plan['maps'][view] = height_map
        u, v = _mapping(view, dimensions, field.shape)
        hh, ww = height_map.shape
        sampled = ndimage.map_coordinates(
            height_map, [v * hh - .5, u * ww - .5], order=1, mode='nearest')
        sampled *= has_surface
        last = len(stack) - 1 - occupied[::-1].argmax(0)
        thickness = (last - first + 1) * spacing
        # Preserve a two-cell core through thin supports. A minimum displacement
        # of half a voxel can otherwise cut the same thin neck from both sides.
        cap = np.maximum(0., np.minimum(
            thickness * .3, (thickness - 2 * spacing) * .5))
        sampled = np.clip(sampled, -cap, cap)
        # Save source-derived probe anchors before modifying the field. The
        # final QA measures their displacements on exported triangles.
        for feature in plan['report']['features']:
            if feature['view'] != view:
                continue
            for number, probe in enumerate(feature['probes']):
                center = np.asarray(probe['center_px'])
                normal = np.asarray(probe['normal_px'])
                radius = probe['radius_px']
                # Symmetric samples measure local continuous curvature contrast.
                offset = probe.get('sample_span_px', radius * 2.5)
                points = np.array(
                    [center, center - normal * offset, center + normal * offset])
                anchors = []
                targets = []
                observable = True
                for px, py in points:
                    uu = (px + .5) / ww
                    vv = (py + .5) / hh
                    if view in ('back', 'left'):
                        uu = 1 - uu
                    if axis == 1:
                        coordinates = [
                            uu * dimensions[0] - dimensions[0] / 2, 0, (1 - vv) * dimensions[2]]
                    elif axis == 0:
                        coordinates = [0, uu * dimensions[1] -
                                       dimensions[1] / 2, (1 - vv) * dimensions[2]]
                    else:
                        coordinates = [uu * dimensions[0] - dimensions[0] /
                                       2, (1 - vv) * dimensions[1] - dimensions[1] / 2, 0]
                    if view == 'bottom':
                        coordinates[1] = vv * dimensions[1] - dimensions[1] / 2
                    transverse = [i for i in range(3) if i != axis]
                    index = [(coordinates[i] - bounds[i][0]) / dimensions[i]
                             * field.shape[i] - .5 for i in transverse]
                    if not (0 <= uu <= 1 and 0 <= vv <= 1) or ndimage.map_coordinates(
                            visible_surface, np.array(index)[:, None], order=1, mode='constant', cval=0)[0] < .9:
                        observable = False
                    if ndimage.map_coordinates(raw_slope, np.array(index)[:, None], order=1, mode='nearest')[0] < .5:
                        observable = False
                    depth = float(ndimage.map_coordinates(root, np.array(
                        index)[:, None], order=1, mode='nearest')[0])
                    coordinates[axis] = bounds[axis][1] - \
                        depth if reverse else bounds[axis][0] + depth
                    anchors.append(coordinates)
                    targets.append(float(ndimage.map_coordinates(
                        sampled, np.array(index)[:, None], order=1, mode='nearest')[0]))
                if not observable:
                    plan['report']['unobservable_probes'] += 1
                    continue
                contrast = targets[0] - np.mean(targets[1:])
                if contrast * feature.get('sign', np.sign(contrast)) <= 0:
                    # An overlapping feature can reverse the proposed section.
                    # Such a location cannot validate this feature's geometry.
                    plan['report']['conflicting_probes'] = plan['report'].get(
                        'conflicting_probes', 0) + 1
                    continue
                if abs(contrast) < spacing * .1:
                    plan['report'].setdefault('below_resolution_probes', 0)
                    plan['report']['below_resolution_probes'] += 1
                    continue
                plan['report']['probes'].append({'id': feature['id'] + f'_{number}', 'kind': feature['kind'],
                                                 'view': view, 'axis': axis, 'outward': 1 if reverse else -1,
                                                 'anchors_m': anchors, 'target_offsets_m': targets,
                                                 'depth_estimate': probe.get('depth_estimate'),
                                                 'tolerance_m': max(spacing * .15, abs(targets[0] - np.mean(targets[1:])) * .2)})
        observations.append({'axis': axis, 'reverse': reverse, 'height': sampled, 'root': root,
                             'slope': slope, 'facing': np.clip(raw_slope, 0, 1), 'spacing': spacing})
    # Fuse observations of the same surface instead of sequentially carving
    # it once per camera. Facing/skin support excludes the opposite surface.
    from .implicit import pad_field
    padded = pad_field(field, dimensions)
    result = np.empty_like(field)
    for start in range(0, field.shape[0], 16):
        stop = min(start + 16, field.shape[0])
        chunk = (stop - start, *field.shape[1:])
        numerator = np.zeros(chunk, np.float32)
        weight_sum = np.zeros(chunk, np.float32)
        for observation in observations:
            axis = observation['axis']

            def expand(values):
                if axis == 0:
                    return values[None, :, :]
                if axis == 1:
                    return values[start:stop, None, :]
                return values[start:stop, :, None]
            height = expand(observation['height'])
            root = expand(observation['root'])
            facing = expand(observation['facing'])
            index = np.arange(start, stop) if axis == 0 else np.arange(
                field.shape[axis])
            distance = (index + .5) * observation['spacing']
            if observation['reverse']:
                distance = dimensions[axis] - distance
            grid_shape = [1, 1, 1]
            grid_shape[axis] = len(index)
            distance = distance.reshape(grid_shape)
            support = np.maximum(abs(height) * 4, observation['spacing'] * 3)
            fade = np.exp(-((distance - root) / support)**4)
            weight = facing**8 * fade * (abs(height) > 1e-9)
            # Resample the actual field along the viewing ray. A first-order
            # slope offset under-fits deep grooves on curved base surfaces.
            source_index = index.reshape(
                grid_shape) + 1 - (1 if observation['reverse'] else -1) * height / observation['spacing']
            source_index = np.clip(source_index, 0, field.shape[axis] + 1)
            lower = np.floor(source_index).astype(np.intp)
            upper = np.minimum(lower + 1, field.shape[axis] + 1)
            fraction = source_index - lower
            if axis == 0:
                source = padded[:, 1:-1, 1:-1]
            elif axis == 1:
                source = padded[start + 1:stop + 1, :, 1:-1]
            else:
                source = padded[start + 1:stop + 1, 1:-1, :]
            shifted = (1 - fraction) * np.take_along_axis(source, lower, axis=axis) + \
                fraction * np.take_along_axis(source, upper, axis=axis)
            numerator += weight * (shifted - field[start:stop])
            weight_sum += weight
        result[start:stop] = field[start:stop] + \
            numerator / np.maximum(weight_sum, .05)
    plan['report']['field'] = {'mode': 'signed_field_detail_before_meshing', 'isovalue': 0.,
                               'depth_limit': '30% of observed local solid thickness; openings remain silhouette constraints',
                               'grid_shape': list(field.shape), 'spacing_m': [dimensions[i] / field.shape[i] for i in range(3)]}
    # Fitting sparse validation points can introduce pinched dents. The pixel
    # solver already supplies a continuous integrable surface, so keep it whole.
    baseline_components = ndimage.label(field < 0)[1]
    scale = 1.
    candidate = result
    for _ in range(5):
        if ndimage.label(candidate < 0)[1] == baseline_components:
            break
        scale *= .5
        candidate = field + (result - field) * scale
    else:
        scale = 0.
        candidate = field
    plan['report']['topology'] = {'baseline_solid_components': int(baseline_components),
                                  'detail_scale': scale, 'method': 'protect thin cores; back off conflicting relief before extraction'}
    for view, values in plan.get('diagnostics', {}).items():
        if 'mask' not in values:
            continue
        axis, reverse = VIEWS[view]
        final_root, _, _, _ = visible_root(
            candidate, axis, reverse, dimensions[axis])
        pixel = float(values['metres_per_pixel'])
        values['final_shared_height_px'] = -root_image(
            final_root, view, dimensions, candidate.shape, values['mask'].shape) / pixel
    return candidate


def capture_high(obj, plan=None):
    """Keep implicit detail for normal baking before any budget simplification."""
    import bpy
    if plan and plan.get('diagnostic_folder'):
        export_maps(plan, plan['diagnostic_folder'])
    high = bpy.data.objects.new(obj.name.split(
        '.')[0] + '__high', obj.data.copy())
    bpy.context.scene.collection.objects.link(high)
    obj['dense_source_name'] = high.name
    triangles = sum(len(p.vertices) - 2 for p in high.data.polygons)
    if triangles > 800000:
        from .core import select_only, apply_mods
        modifier = high.modifiers.new('normal_source_budget', 'DECIMATE')
        modifier.ratio = 800000 / triangles
        select_only(high)
        apply_mods(high)
    if plan and plan.get('fine_maps'):
        from . import relief
        maps = {k: v for k, v in plan['fine_maps'].items(
        ) if k in relief.ELEVATIONS}
        if maps:
            relief.hook({k: '' for k in maps}, *plan['dimensions'], {}, maps_override=maps,
                        keep_high=False, cap_share=.02, light_override=np.array([-.7, -.7]))(high)
    return high


def export_maps(plan, directory):
    """Save numerical topography and contour diagnostics, including rejections."""
    from pathlib import Path
    from PIL import Image, ImageDraw
    from skimage.measure import find_contours
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    for view, values in plan.get('diagnostics', {}).items():
        if 'mask' not in values or not values['mask'].any():
            continue
        np.savez_compressed(directory / (view + '.npz'), **values)
        mask = values['mask']
        height = values['hypothesis_height_px']
        low, high = np.percentile(height[mask], [1, 99])
        normalized = np.clip((height - low) / max(high - low, 1e-8), 0, 1)
        colors = np.stack(
            [normalized, 1 - abs(2 * normalized - 1), 1 - normalized], axis=2)
        colors[~mask] = .08
        canvas = Image.fromarray(np.uint8(colors * 255))
        draw = ImageDraw.Draw(canvas)
        for level in np.linspace(low, high, 15)[1:-1]:
            for contour in find_contours(height, level, mask=mask):
                if len(contour) >= 2:
                    draw.line([(float(x), float(y))
                              for y, x in contour], fill=(30, 30, 30))
        canvas.save(directory / (view + '-hypothesis-contours.png'))
        if plan.get('cad_export') and 'final_shared_height_px' in values:
            from . import spline_surface, cad_export
            import json
            pixel = float(values['metres_per_pixel'])
            fit = spline_surface.fit_height(
                values['final_shared_height_px'] * pixel, mask, max(pixel * .5, 1e-5))
            document = spline_surface.document(
                fit, *chart_frame(view, plan['dimensions']))
            document['source_uncertainty'] = plan['report']['views'].get(
                view, {}).get('absolute_depth_status', 'unverified')
            path = directory / (view + '.nurbs.json')
            path.write_text(json.dumps(document, indent=2))
            result = dict(fit['report'], document=str(
                path), closed_solid=False)
            result['native_backend_available'] = cad_export.available()
            if not result['native_backend_available']:
                result['step_failure'] = 'Optional Open CASCADE backend unavailable; numerical chart only'
            if fit['report']['accepted'] and result['native_backend_available']:
                try:
                    result['step'] = cad_export.export_step(
                        [document], directory / (view + '.step'))
                except (ValueError, RuntimeError) as error:
                    result['step_failure'] = str(error)
            plan['report'].setdefault('cad_surfaces', {})[view] = result
    plan['report']['diagnostic_folder'] = str(directory)


def protected_samples(obj, report, geometry_tolerance=None):
    """Protect detected features locally, without tightening every planar face."""
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    if geometry_tolerance is not None:
        coarse, fine = [], []
        for probe in report.get('probes', []):
            offsets = probe['target_offsets_m']
            contrast = abs(offsets[0] - np.mean(offsets[1:]))
            (coarse if contrast >= geometry_tolerance * .5 else fine).append(probe)
        report['probes'] = coarse
        report['normal_map_probes'] = fine
        report['geometry_contrast_floor_m'] = float(geometry_tolerance * .5)
        report['fine_representation'] = 'dense continuous surface baked to tangent-space normals'
    tree = BVHTree.FromPolygons([v.co for v in obj.data.vertices], [
                                p.vertices for p in obj.data.polygons])
    from .local_features import check_surface_features
    baseline = check_surface_features([tuple(v.co) for v in obj.data.vertices],
                                      [tuple(p.vertices) for p in obj.data.polygons], report, tree=tree)
    conflicts = {probe['id']
                 for probe in baseline['probes'] if not probe['retained']}
    report['unmet_before_reduction'] = sorted(conflicts)
    # A single image with unknown lighting/material cannot establish absolute
    # relief. Keep its probes in final QA, but do not freeze millions of faces
    # to an uncalibrated hypothesis. Legacy/calibrated probes remain protected.
    uncertain = {probe['id'] for probe in report.get('probes', [])
                 if probe.get('depth_estimate') is not None
                 and not probe['depth_estimate'].get('absolute_depth_supported_under_model', False)}
    report['unverified_depth_probes'] = sorted(uncertain)
    report['depth_review_required'] = bool(uncertain)
    excluded = conflicts | uncertain
    reach = max(obj.dimensions) * 2
    points = []
    tolerances = []
    identifiers = []
    supports = []
    for probe in report.get('probes', []):
        if probe['id'] in excluded:
            continue
        direction = np.zeros(3)
        direction[probe['axis']] = probe['outward']
        for number, anchor in enumerate(probe['anchors_m']):
            location, _, _, _ = tree.ray_cast(
                Vector(np.asarray(anchor) + direction * reach), Vector(-direction), reach * 2)
            if location is not None:
                points.append(tuple(location))
                tolerances.append(probe['tolerance_m'])
                supports.append(float(np.linalg.norm(np.asarray(
                    probe['anchors_m'][1]) - probe['anchors_m'][2])) * .25)
                identifiers.append(probe['id'] + f'/{number}')
    report['protected_samples'] = len(points)
    reference = []
    for probe in report.get('probes', []):
        if probe['id'] in excluded:
            continue
        direction = np.zeros(3)
        direction[probe['axis']] = probe['outward']
        offsets = []
        for anchor in probe['anchors_m']:
            location, _, _, _ = tree.ray_cast(
                Vector(np.asarray(anchor) + direction * reach), Vector(-direction), reach * 2)
            if location is None:
                break
            offsets.append(float((np.asarray(location) - anchor) @ direction))
        if len(offsets) == 3 and abs(offsets[0] - np.mean(offsets[1:])) > 1e-5:
            reference.append(dict(probe, target_offsets_m=offsets))
    return {'points': np.asarray(points), 'tolerance_m': np.asarray(tolerances), 'ids': identifiers,
            'support_m': np.asarray(supports),
            # Conflicting input fits remain in final QA. They cannot be repaired
            # by retaining millions of triangles during reduction.
            'source_report': {'probes': [probe for probe in report.get('probes', []) if probe['id'] not in excluded]},
            'contrast_report': {'probes': reference}} if points else None
