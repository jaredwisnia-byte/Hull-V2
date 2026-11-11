"""Probe the finished mesh for the local evidence a silhouette cannot verify."""
import numpy as np


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
