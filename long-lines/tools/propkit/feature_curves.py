"""Connected image-curve paths and checked cubic representations; not 3D parts."""
import inspect
import numpy as np
from skimage.morphology import skeletonize
from scipy.spatial import cKDTree
from scipy.interpolate import make_splprep


def paths(edges):
    """Walk actual skeleton adjacency; no straight segments across gaps."""
    sk = skeletonize(edges)
    hh, ww = sk.shape
    nodes = set(map(int, np.flatnonzero(sk)))
    neighbours = {}
    for node in nodes:
        y, x = divmod(node, ww)
        adj = []
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if not (dx or dy) or not (0 <= y + dy < hh and 0 <= x + dx < ww):
                    continue
                other = (y + dy) * ww + x + dx
                if other not in nodes:
                    continue
                if dx and dy and (sk[y, x + dx] or sk[y + dy, x]):
                    continue
                adj.append(other)
        neighbours[node] = adj
    visited = set()
    curves = []

    def walk(a, b):
        curve = [a]
        previous = a
        current = b
        while True:
            visited.add(tuple(sorted((previous, current))))
            curve.append(current)
            if len(neighbours[current]) != 2:
                break
            following = next(n for n in neighbours[current] if n != previous)
            if tuple(sorted((current, following))) in visited:
                break
            previous, current = current, following
        if len(curve) >= 4:
            curves.append([[int(n % ww), int(n // ww)] for n in curve])
    for node in sorted(nodes, key=lambda n: (len(neighbours[n]) == 2, n)):
        for other in neighbours[node]:
            if tuple(sorted((node, other))) not in visited:
                walk(node, other)
    return sk, curves


def fit(points, tolerance=.75):
    points = np.asarray(points, float)
    if len(points) < 8:
        return {'representation': 'polyline', 'points_xy': points.tolist()}
    weights = np.ones(len(points))
    weights[[0, -1]] = 100
    if np.array_equal(points[0], points[-1]) and 'bc_type' not in inspect.signature(make_splprep).parameters:
        return {'representation': 'polyline', 'points_xy': points.tolist(), 'reason': 'periodic spline API unavailable'}
    for factor in (.25, .1, .04, .01, .002, 0.):
        options = {'bc_type': 'periodic'} if np.array_equal(
            points[0], points[-1]) else {}
        spline, u = make_splprep(
            points.T, w=weights, s=factor * len(points), k=3, **options)
        samples = spline(np.linspace(0, 1, max(200, len(points) * 8))).T
        # Compare to the original connected path, not just its integer vertices.
        parameter = np.r_[0, np.cumsum(
            np.linalg.norm(np.diff(points, axis=0), axis=1))]
        parameter /= parameter[-1]
        dense = np.stack([np.interp(np.linspace(0, 1, max(
            200, len(points) * 8)), parameter, points[:, i]) for i in range(2)], 1)
        error = max(float(cKDTree(dense).query(samples)[0].max()), float(
            cKDTree(samples).query(dense)[0].max()))
        endpoint_error = float(np.linalg.norm(
            spline([0, 1]).T - points[[0, -1]], axis=1).max())
        if error <= tolerance and endpoint_error <= .01:
            return {'representation': 'cubic_B_spline', 'degree': 3, 'knots': spline.t.tolist(), 'coefficient_axis': 0,
                    'control_points_xy': spline.c.tolist(), 'sampled_max_deviation_px': error,
                    'endpoint_error_px': endpoint_error, 'source_points': len(points),
                    'points_xy': samples.tolist()}
    return {'representation': 'polyline', 'points_xy': points.tolist(), 'reason': 'sampled deviation bound not met'}


def trace(edges):
    _, curves = paths(edges)
    return [fit(points) for points in curves if len(points) >= 12]
