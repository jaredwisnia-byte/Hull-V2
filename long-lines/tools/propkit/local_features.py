"""Probe the finished mesh for the local evidence a silhouette cannot verify."""
import numpy as np


def geometry_components(vertices, polygons, tolerance=1e-6):
    """Count geometric islands after welding exporter-only UV/normal splits."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    coordinates = np.rint(np.asarray(vertices) / tolerance).astype(np.int64)
    unique, index = np.unique(coordinates, axis=0, return_inverse=True)
    edges = []
    for face in polygons:
        values = index[list(face)]
        edges.extend(zip(values, np.roll(values, -1)))
    edges = np.asarray(edges)
    graph = coo_matrix((np.ones(len(edges)), (edges[:, 0], edges[:, 1])), shape=(
        len(unique), len(unique)))
    return int(connected_components(graph, directed=False, return_labels=False))


def check_surface_features(vertices, polygons, report, minimum_fraction=.5, maximum_fraction=None, tree=None, sampling_tolerance=False):
    """Test source-derived crowns/rims and valleys/shoulders on exported triangles.

    Subtract the original envelope at each probe so macro curvature cannot
    masquerade as detail. Texture and normal maps cannot make this check pass.
    """
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    tree = tree or BVHTree.FromPolygons(
        [Vector(p) for p in vertices], polygons)
    reach = float(np.ptp(np.asarray(vertices), axis=0).max() * 2)
    records = []
    fails = []
    for probe in report.get('probes', []):
        direction = np.zeros(3)
        direction[probe['axis']] = probe['outward']
        matrix = np.asarray(report.get('matrix_world', np.eye(4)))
        direction = matrix[:3, :3] @ direction
        direction /= max(np.linalg.norm(direction), 1e-9)
        offsets = []
        for anchor in probe['anchors_m']:
            anchor = matrix[:3, :3] @ np.asarray(anchor) + matrix[:3, 3]
            location, _, _, _ = tree.ray_cast(
                Vector(np.asarray(anchor) + direction * reach), Vector(-direction), reach * 2)
            offsets.append(None if location is None else float(
                (np.asarray(location) - anchor) @ direction))
        target = np.asarray(probe['target_offsets_m'])
        expected = float(target[0] - np.mean(target[1:]))
        measured = None if None in offsets else float(
            offsets[0] - np.mean(offsets[1:]))
        uncertainty = probe.get(
            'tolerance_m', 0.) if sampling_tolerance else 0.
        lower = max(abs(expected) * .5, abs(expected)
                    * minimum_fraction - uncertainty)
        retained = measured is not None and measured * \
            expected > 0 and abs(measured) >= lower
        if maximum_fraction is not None and measured is not None:
            retained &= abs(measured) <= abs(expected) * \
                maximum_fraction + uncertainty
        records.append({'id': probe['id'], 'kind': probe['kind'], 'view': probe['view'],
                        'expected_contrast_m': expected, 'measured_contrast_m': measured, 'retained': bool(retained)})
        if not retained:
            fails.append('missing ' + probe['kind'] + ' depth: ' + probe['id'])
    return {'status': 'pass' if not fails else 'fail', 'probes': records, 'fails': fails,
            'method': 'exported geometric crown/rim and valley/shoulder contrasts; source-derived locations'}


def check_channels(vertices, polygons, construction):
    """Measure recesses by rays through actual exported triangles, not normals.

    Reference radii come from the independently fitted silhouette splines.
    Geometry below 45% of the fitted recess is flagged; shading fit confidence
    remains separate from this check of whether the mesh retained the feature.
    """
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    profile = construction.get('spline_profile')
    if not profile:
        return {'status': 'not_applicable', 'features': [], 'fails': []}
    tree = BVHTree.FromPolygons([Vector(p) for p in vertices], polygons)
    height = construction['height_m']
    stations = profile['stations']
    v = np.linspace(*construction['band'], stations)
    rx, ry = np.asarray(profile['radius_samples_m'])
    centers = np.asarray(profile['center_samples_m'])
    records = []
    fails = []
    for feature in construction['features']:
        angle = feature['angle']
        direction = np.array([np.cos(angle), np.sin(angle), 0.])
        depths = []
        expected = []
        for row in (stations // 4, stations // 2, stations * 3 // 4):
            base = 1 / np.sqrt((direction[0] / rx[row])
                               ** 2 + (direction[1] / ry[row])**2)
            center = np.r_[centers[:, row], (1 - v[row]) * height]
            origin = center + direction * height
            location, _, _, distance = tree.ray_cast(
                Vector(origin), Vector(-direction), height)
            expected.append(2 * min(rx[row], ry[row]) * feature['depth_fraction']
                            * np.sin(np.pi * row / (stations - 1))**.4)
            depths.append(None if location is None else float(
                base - np.dot(np.array(location) - center, direction)))
        retained = all(depth is not None and depth >= .45 *
                       target for depth, target in zip(depths, expected))
        records.append({'id': feature['id'], 'measured_recess_m': depths, 'fitted_recess_m': expected,
                        'retained': retained, 'evidence_uncertain': feature['uncertain']})
        if not retained:
            fails.append('missing exported local channel ' + feature['id'])
    return {'status': 'pass' if not fails else 'fail', 'features': records, 'fails': fails,
            'method': 'radial rays through exported triangles at three interior stations'}
