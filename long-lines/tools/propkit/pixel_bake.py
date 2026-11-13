"""Final-UV per-texel projection with geometric ownership and source rejection.

Uses source-camera depth buffers, not interpolated vertex visibility. Material
families without projection evidence retain their normal Cycles bake.
"""
import numpy as np
from PIL import Image
from scipy import ndimage
from .raster import triangle_samples, depth_buffer
from .pathing import io_path

AXES = {'front': (1, 1), 'back': (1, -1), 'right': (0, -1),
        'left': (0, 1), 'top': (2, -1)}
DIRECTIONS = {'front': (0, -1, 0), 'back': (0, 1, 0),
              'right': (1, 0, 0), 'left': (-1, 0, 0), 'top': (0, 0, 1)}


def linear_rgb(rgb):
    return np.where(rgb <= .04045, rgb / 12.92, ((rgb + .055) / 1.055) ** 2.4)


def srgb(rgb):
    return np.where(rgb <= .0031308, rgb * 12.92, 1.055 * np.maximum(rgb, 0) ** (1 / 2.4) - .055)


def overlap_offsets(colours, valid, limit=.04):
    """One bounded exposure correction per source, shared by all UV islands.

    Use only consistent overlapping observations. Incompatible paint patterns
    are rejected, not explained away with a large brightness correction.
    """
    count = colours.shape[1]
    equations = []
    differences = []
    for a in range(count):
        for b in range(a):
            keep = valid[:, a] & valid[:, b]
            if keep.sum() < 12:
                continue
            delta = colours[keep, a] - colours[keep, b]
            median = np.median(delta, axis=0)
            if np.max(abs(median)) > limit or np.median(np.linalg.norm(delta - median, axis=1)) > .035:
                continue
            equation = np.zeros(count)
            equation[a] = 1
            equation[b] = -1
            equations.append(equation)
            differences.append(median)
    if not equations:
        return np.zeros((count, 3))
    equations = np.vstack([equations, np.ones(count)])
    differences = np.vstack([differences, np.zeros(3)])
    return np.clip(np.linalg.lstsq(equations, differences, rcond=None)[0], -limit, limit)


def calibrate_sources(cameras, points, normals, record):
    colours = []
    valid = []
    for camera in cameras:
        sw, sh = camera['size']
        mapping = camera_uv(camera['name'], points, record)
        ix = np.clip(np.rint(mapping[:, 0] * sw - .5).astype(int), 0, sw - 1)
        iy = np.clip(
            np.rint((1 - mapping[:, 1]) * sh - .5).astype(int), 0, sh - 1)
        depth = points[:, camera['axis']] * camera['sign']
        seen = abs(camera['depth'][iy, ix] -
                   depth) < max(record['dimensions']) / max(sw, sh) * 2
        seen &= (mapping >= 0).all(1) & (mapping <= 1).all(1)
        seen &= normals @ np.asarray(DIRECTIONS[camera['name']]) > .25
        colours.append(linear_rgb(camera['rgb'][iy, ix]))
        valid.append(seen)
    return overlap_offsets(np.stack(colours, axis=1), np.stack(valid, axis=1))


def uv(view, points, dimensions):
    W, D, H = dimensions
    x, y, z = points.T
    if view == 'front':
        return np.c_[(x + W / 2) / W, z / H]
    if view == 'back':
        return np.c_[1 - (x + W / 2) / W, z / H]
    if view == 'right':
        return np.c_[(y + D / 2) / D, z / H]
    if view == 'left':
        return np.c_[1 - (y + D / 2) / D, z / H]
    return np.c_[(x + W / 2) / W, (y + D / 2) / D]


def transform(points, matrix):
    return points @ matrix[:3, :3].T + matrix[:3, 3]


def camera_uv(view, points, record):
    mapping = uv(view, points, record['dimensions'])
    fit = record.get('camera_fit')
    if not fit or view == 'top':
        return mapping
    width, depth, height = record['dimensions']
    span = depth if view in ('left', 'right') else width
    roll = np.radians(fit['roll_degrees'].get(view, 0))
    horizontal = (mapping[:, 0] - .5) * span
    pivot = 1 - fit.get('pivot_v', .5)
    vertical = (mapping[:, 1] - pivot) * height
    mapping[:, 0] = .5 + (horizontal * np.cos(roll) -
                          vertical * np.sin(roll)) / span
    mapping[:, 1] = pivot + (vertical * np.cos(roll) +
                             horizontal * np.sin(roll)) / height
    return mapping


def bind_sources(registry):
    sources = {}
    for material, record in registry.items():
        obj = record['object']
        sources[material] = {**record, 'world_to_source': record['initial_matrix']
                             @ np.linalg.inv(np.asarray(obj.matrix_world))}
    return sources


def refine_albedo(obj, sources, output_path, shift=(0, 0, 0)):
    mesh = obj.data
    mesh.calc_loop_triangles()
    if not sources:
        return {}
    image = np.asarray(Image.open(output_path).convert('RGB')).copy()
    height, width = image.shape[:2]
    positions = np.array([tuple(obj.matrix_world @ vertex.co)
                         for vertex in mesh.vertices])
    faces = np.array([tuple(triangle.vertices)
                     for triangle in mesh.loop_triangles])
    owners = mesh.attributes['hull_owner']
    triangle_owners = np.array(
        [owners.data[triangle.polygon_index].value for triangle in mesh.loop_triangles])
    normals = np.array([tuple(vertex.normal) for vertex in mesh.vertices])
    normals = normals @ np.linalg.inv(np.asarray(obj.matrix_world)[:3, :3])
    atlas = mesh.uv_layers.active
    covered = np.zeros((height, width), bool)
    occupied = np.zeros((height, width), bool)
    atlas_owners = np.full((height, width), -1, np.int32)
    confidence = np.zeros((height, width), np.float32)
    view_codes = {'front': 1, 'back': 2, 'left': 3,
                  'right': 4, 'top': 5, 'bottom': 6}
    source_view = np.zeros((height, width), np.uint8)
    material_sources = {}
    camera_cache = {}
    for material_index, material in enumerate(mesh.materials):
        record = sources.get(material.name)
        if record is None:
            continue
        matrix = record['world_to_source'].copy()
        matrix[:3, 3] -= matrix[:3, :3] @ np.asarray(shift)
        projected = transform(positions, matrix)
        cache_key = (matrix.tobytes(), tuple(sorted(record['views'].items())),
                     tuple(record['dimensions']), str(record.get('camera_fit')))
        if cache_key in camera_cache:
            material_sources[material_index] = (
                record, matrix, camera_cache[cache_key])
            continue
        camera_sources = []
        for view, path in record['views'].items():
            if view not in AXES:
                continue
            colours = np.asarray(Image.open(path).convert('RGB'), float) / 255
            sh, sw = colours.shape[:2]
            mapping = camera_uv(view, projected, record)
            pixels = mapping * [sw, -sh] + [-.5, sh - .5]
            axis, sign = AXES[view]
            zbuffer, ownership = depth_buffer(pixels, faces, projected[:, axis] * sign,
                                              triangle_owners, sw, sh)
            camera_sources.append({'name': view, 'rgb': colours, 'depth': zbuffer, 'owners': ownership,
                                   'pixels': pixels, 'axis': axis, 'sign': sign, 'size': (sw, sh)})
        source_normals = normals @ np.linalg.inv(matrix[:3, :3])
        source_normals /= np.maximum(np.linalg.norm(source_normals,
                                     axis=1, keepdims=True), 1e-9)
        offsets = calibrate_sources(
            camera_sources, projected, source_normals, record)
        for camera, offset in zip(camera_sources, offsets):
            camera['offset'] = offset
        material_sources[material_index] = (record, matrix, camera_sources)
        camera_cache[cache_key] = camera_sources
    unknown = 0
    disagreements = 0
    processed = 0
    for triangle_index, triangle in enumerate(mesh.loop_triangles):
        settings = material_sources.get(
            mesh.polygons[triangle.polygon_index].material_index)
        atlas_uv = np.array([tuple(atlas.data[i].uv) for i in triangle.loops])
        sampled = triangle_samples(
            atlas_uv * [width, -height] + [-.5, height - .5], width, height)
        if sampled is None:
            continue
        yy, xx, barycentric = sampled
        occupied[yy, xx] = True
        if settings is None:
            continue
        record, matrix, cameras = settings
        atlas_owners[yy, xx] = triangle_owners[triangle_index]
        source_points = transform(
            barycentric @ positions[faces[triangle_index]], matrix)
        n = barycentric @ normals[faces[triangle_index]]
        n = n @ np.linalg.inv(matrix[:3, :3])
        n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-9)
        weights = []
        colour_samples = []
        owner = triangle_owners[triangle_index]
        for camera in cameras:
            sw, sh = camera['size']
            mapping = camera_uv(camera['name'], source_points, record)
            px = mapping[:, 0] * sw - .5
            py = (1 - mapping[:, 1]) * sh - .5
            ix = np.clip(np.rint(px).astype(int), 0, sw - 1)
            iy = np.clip(np.rint(py).astype(int), 0, sh - 1)
            depth = source_points[:, camera['axis']] * camera['sign']
            # Quantization tolerance is tied to source pixels, not a large
            # world-space ray offset that can jump over small controls.
            tolerance = max(record['dimensions']) / max(sw, sh) * 2
            visible = (camera['owners'][iy, ix] == owner) & (
                abs(camera['depth'][iy, ix] - depth) < tolerance)
            visible &= (px >= 0) & (px < sw) & (py >= 0) & (py < sh)
            facing = np.maximum(0, n @ np.asarray(DIRECTIONS[camera['name']]))
            span = record['dimensions'][1] if camera['name'] in (
                'left', 'right') else record['dimensions'][0]
            weights.append(facing**4 * visible * sw / span)
            samples = np.stack([ndimage.map_coordinates(camera['rgb'][:, :, c], [py, px], order=1, mode='nearest')
                                for c in range(3)], axis=1)
            samples = srgb(np.clip(linear_rgb(samples) -
                           camera.get('offset', 0), 0, 1))
            colour_samples.append(samples)
        weights = np.asarray(weights).T
        colours = np.stack(colour_samples, axis=1)
        best = np.argmax(weights, axis=1)
        reference = colours[np.arange(len(best)), best]
        # Source consistency is tested in display space; blending uses linear
        # radiance. Do not perform a different exposure correction per triangle.
        disagreement = np.linalg.norm(
            colours - reference[:, None, :], axis=2) > .18
        disagreements += int((disagreement & (weights > 0)).sum())
        weights[disagreement] = 0
        total = weights.sum(1)
        valid = total > 0
        # The original leading camera may have failed colour consistency.
        # Record the strongest surviving source, not that rejected candidate.
        selected = np.argmax(weights, axis=1)
        predicted = np.einsum(
            'ij,ijk->ik', weights, linear_rgb(colours)) / np.maximum(total[:, None], 1e-9)
        image[yy[valid], xx[valid]] = np.uint8(
            np.clip(srgb(predicted[valid]), 0, 1) * 255)
        covered[yy[valid], xx[valid]] = True
        camera_codes = np.asarray([view_codes[camera['name']] for camera in cameras], np.uint8)
        source_view[yy[valid], xx[valid]] = camera_codes[selected[valid]]
        confidence[yy, xx] = np.maximum(
            confidence[yy, xx], weights.max(1) / np.maximum(total, 1e-9))
        unknown += int((~valid).sum())
        processed += len(valid)
    # A vertex-shader fallback may already contain a painted child ghost.
    # Replace unsupported projected texels only from evidence belonging to
    # the same physical owner. This is explicit hole filling, not recovered
    # hidden texture detail. Procedural materials keep their native bake.
    filled = 0
    unresolved = 0
    for owner in np.unique(atlas_owners[atlas_owners >= 0]):
        missing = (atlas_owners == owner) & ~covered
        known = (atlas_owners == owner) & covered
        if known.any():
            indices = ndimage.distance_transform_edt(
                ~known, return_distances=False, return_indices=True)
            image[missing] = image[indices[0][missing], indices[1][missing]]
            source_view[missing] = 254  # same-owner colour, no direct source view
            filled += int(missing.sum())
        else:
            unresolved += int(missing.sum())
    # Extend only outside UV islands, never over another material's pixels.
    if covered.any():
        distance, indices = ndimage.distance_transform_edt(
            ~covered, return_indices=True)
        margin = (distance > 0) & (
            distance <= max(4, width // 128)) & ~occupied
        image[margin] = image[indices[0][margin], indices[1][margin]]
    Image.fromarray(image).save(io_path(output_path))
    Image.fromarray(np.uint8(confidence * 255)).save(io_path(
        str(output_path).replace('_albedo.png', '_source_confidence.png')))
    Image.fromarray(source_view).save(io_path(
        str(output_path).replace('_albedo.png', '_source_view.png')))
    palette = np.zeros((256, 3), np.uint8)
    view_colours = {'front': (225, 89, 89), 'back': (75, 150, 232),
                    'left': (91, 185, 123), 'right': (241, 190, 68),
                    'top': (174, 105, 218), 'bottom': (220, 135, 72)}
    for view, colour in view_colours.items():
        palette[view_codes[view]] = colour
    palette[254] = (160, 160, 160)
    Image.fromarray(palette[source_view]).save(io_path(
        str(output_path).replace('_albedo.png', '_source_view_preview.png')))
    return {'mode': 'per_texel_owned_projection', 'processed_samples': processed,
            'unseen_source_samples': unknown, 'unseen_pixels_filled_from_same_owner': filled,
            'unresolved_projected_pixels': unresolved, 'needs_review': bool(unresolved),
            'rejected_colour_samples': disagreements,
            'covered_atlas_pixels': int(covered.sum()),
            'source_view_legend': {**view_codes, 'same_owner_fill': 254},
            'source_view_preview_rgb': view_colours,
            'source_view_pixels': {view: int((source_view == code).sum())
                                   for view, code in view_codes.items()},
            'source_selection': 'visibility + ownership + facing + colour consistency; linear-light blend'}
