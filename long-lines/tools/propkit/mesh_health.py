"""Local topology checks on exported geometry, independent of its texture."""

from collections import defaultdict

import numpy as np


def folded_edges(vertices, polygons, angle_degrees=115):
    """Count adjacent faces whose outward normals form an extreme fold.

    glTF may duplicate positions at UV seams, so adjacency uses welded positions.
    This is a review signal: a fold can be intentional, but many folds usually
    indicate slivers, spikes, or unstable extraction from an implicit field.
    """
    points = np.asarray(vertices, dtype=float)
    if len(points) == 0:
        return {'count': 0, 'per_1k': 0., 'triangles': 0}
    _, inverse = np.unique(np.rint(points / 1e-5).astype(np.int64), axis=0,
                           return_inverse=True)
    normals = []
    edges = defaultdict(list)
    for polygon in polygons:
        for j in range(1, len(polygon) - 1):
            tri = [polygon[0], polygon[j], polygon[j + 1]]
            ids = inverse[tri]
            if len(set(ids)) != 3:
                continue
            a, b, c = points[tri]
            normal = np.cross(b - a, c - a)
            length = np.linalg.norm(normal)
            if length < 1e-12:
                continue
            face = len(normals)
            normals.append(normal / length)
            for start, end in ((0, 1), (1, 2), (2, 0)):
                edge = tuple(sorted((int(ids[start]), int(ids[end]))))
                edges[edge].append(face)
    if not normals:
        return {'count': 0, 'per_1k': 0., 'triangles': 0}
    normals = np.asarray(normals)
    limit = np.cos(np.deg2rad(angle_degrees))
    count = sum(float(np.dot(normals[faces[0]], normals[faces[1]])) < limit
                for faces in edges.values() if len(faces) == 2)
    return {'count': int(count), 'per_1k': round(float(count / len(normals) * 1000), 3),
            'triangles': len(normals)}
