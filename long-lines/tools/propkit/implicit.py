"""Metric boundary conditions for cell-centred signed fields (negative inside)."""
import numpy as np


def bounded_field(field, dimensions):
    """Intersect with the physical sampling box before adding interior detail.

    Silhouette extrusions can be unbounded along a camera axis. Explicit box
    distances give the boundary cells the same metric meaning as interior cells.
    """
    result = np.asarray(field, dtype=np.float32).copy()
    for axis, (count, span) in enumerate(zip(field.shape, dimensions)):
        distance = (np.abs((np.arange(count) + .5) / count - .5) - .5) * span
        shape = [1, 1, 1]
        shape[axis] = count
        np.maximum(result, distance.reshape(shape), out=result)
    return result


def pad_field(field, dimensions):
    """One exterior cell layer at metric half-voxel distances.

    A constant unrelated to voxel size shifts a zero crossing towards the first
    interior cell, shrinking the shape and flattening shallow crowns.
    """
    result = np.pad(np.asarray(field, dtype=np.float32), 1, mode='edge')
    for axis, (count, span) in enumerate(zip(field.shape, dimensions)):
        for index in (0, -1):
            section = [slice(None)] * 3
            section[axis] = index
            face = result[tuple(section)]
            np.maximum(face, span / count / 2, out=face)
    return result
