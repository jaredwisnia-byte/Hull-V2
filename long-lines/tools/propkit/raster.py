"""Small deterministic orthographic/UV rasterizer shared by visibility and QA."""
import numpy as np


def triangle_samples(points, width, height):
    points = np.asarray(points, float)
    low = np.maximum(np.ceil(points.min(0)).astype(int), 0)
    high = np.minimum(np.floor(points.max(0)).astype(int),
                      [width - 1, height - 1])
    if np.any(high < low):
        return None
    a, b, c = points
    denominator = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
    if abs(denominator) < 1e-12:
        return None
    y, x = np.mgrid[low[1]:high[1] + 1, low[0]:high[0] + 1]
    first = ((b[1] - c[1]) * (x - c[0]) +
             (c[0] - b[0]) * (y - c[1])) / denominator
    second = ((c[1] - a[1]) * (x - c[0]) +
              (a[0] - c[0]) * (y - c[1])) / denominator
    third = 1 - first - second
    mask = (first >= -1e-8) & (second >= -1e-8) & (third >= -1e-8)
    return y[mask], x[mask], np.stack([first[mask], second[mask], third[mask]], axis=1)


def depth_buffer(points, triangles, depths, owners, width, height):
    zbuffer = np.full((height, width), np.inf)
    owner = np.full((height, width), -1, dtype=np.int32)
    for index, face in enumerate(triangles):
        sampled = triangle_samples(points[face], width, height)
        if sampled is None:
            continue
        y, x, barycentric = sampled
        depth = barycentric @ depths[face]
        closer = depth < zbuffer[y, x]
        zbuffer[y[closer], x[closer]] = depth[closer]
        owner[y[closer], x[closer]] = owners[index]
    return zbuffer, owner
