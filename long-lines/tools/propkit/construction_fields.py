"""Boolean removal/addition volumes derived from a fitted shared surface.

Operations are implicit fields, not separately capped render meshes. This changes
representation; it does not supply missing depth evidence or exact distance values.
"""
import numpy as np


def volumes(base, target):
    return np.maximum(base, -target), np.maximum(target, -base)


def compose(base, removal, addition):
    return np.minimum(np.maximum(base, -removal), addition)


def reconstruct(base, target, maximum_root_shift_cells=.1):
    """Compose in bounded-memory slabs and report resolution/representation limits."""
    output = np.empty_like(target)
    removed = added = 0
    sign_errors = 0
    for start in range(0, len(base), 16):
        sl = slice(start, start + 16)
        removal, addition = volumes(base[sl], target[sl])
        output[sl] = compose(base[sl], removal, addition)
        removed += int(np.count_nonzero(removal < 0))
        added += int(np.count_nonzero(addition < 0))
        sign_errors += int(np.count_nonzero(
            (output[sl] < 0) != (target[sl] < 0)))
    if sign_errors:
        raise RuntimeError(
            'Construction operations changed the fitted solid membership')
    drift = 0.
    for axis in range(target.ndim):
        source = np.moveaxis(target, axis, 0)
        composed = np.moveaxis(output, axis, 0)
        for start in range(0, len(source) - 1, 16):
            stop = min(start + 16, len(source) - 1)
            a, b = source[start:stop], source[start + 1:stop + 1]
            c, d = composed[start:stop], composed[start + 1:stop + 1]
            crossing = (a < 0) != (b < 0)
            if crossing.any():
                before = a[crossing] / (a[crossing] - b[crossing])
                after = c[crossing] / (c[crossing] - d[crossing])
                drift = max(drift, float(np.max(abs(before - after))))
    safe = drift <= maximum_root_shift_cells
    if not safe:
        output = target
    return output, {'representation': 'base minus fitted removal volume, union fitted addition volume',
                    'removed_cells': removed, 'added_cells': added, 'membership_errors': sign_errors,
                    'maximum_root_shift_cells': drift, 'allowed_root_shift_cells': maximum_root_shift_cells,
                    'composition_applied': safe, 'fallback': 'none' if safe else 'preserve fitted zero crossings; sampled CSG needs distance reinitialization',
                    'feature_isolation': 'aggregate shared-surface difference; individual reusable cutters not yet exported',
                    'distance_values': 'CSG bounds, not exact Euclidean distances',
                    'depth_evidence': 'inherited from fitted observations; not newly validated by Boolean operations'}
