"""Diagnostic open-surface meshes from actual numerical relief maps."""
import numpy as np


def mesh_grid(base, height, mask, view, dimensions, pixel_m):
    from .surface_detail import chart_frame
    base, height, mask = np.asarray(base), np.asarray(
        height), np.asarray(mask, bool)
    if base.shape != height.shape or mask.shape != base.shape or mask.ndim != 2:
        raise ValueError(
            'Height, reference and mask must share an image frame')
    if not np.isfinite(base[mask]).all() or not np.isfinite(height[mask]).all() or pixel_m <= 0:
        raise ValueError(
            'Finite height and positive physical pixel scale required')
    origin, u, v, normal = map(np.asarray, chart_frame(view, dimensions))
    hh, ww = mask.shape
    yy, xx = np.nonzero(mask)
    vertices = origin + (xx[:, None] + .5) / ww * u + (yy[:, None] + .5) / \
        hh * v + (base[mask] + height[mask])[:, None] * pixel_m * normal
    indices = np.full(mask.shape, -1, np.int64)
    indices[mask] = np.arange(mask.sum())
    quads = mask[:-1, :-1] & mask[1:, :-1] & mask[:-1, 1:] & mask[1:, 1:]
    a = indices[:-1, :-1][quads]
    b = indices[:-1, 1:][quads]
    c = indices[1:, :-1][quads]
    d = indices[1:, 1:][quads]
    faces = np.concatenate([np.c_[a, c, b], np.c_[b, c, d]])
    return vertices, faces
