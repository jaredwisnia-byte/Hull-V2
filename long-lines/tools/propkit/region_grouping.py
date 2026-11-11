"""Shared weak-crease merging extracted from the original relief engine.

This operates on image evidence only; it does not manufacture dome/dish shapes.
"""
import numpy as np
from scipy import ndimage


def merge_weak_lines(labels, interior, strength, threshold=.22, protect_strong=False):
    labels = np.asarray(labels, np.int32).copy()
    interior = np.asarray(interior, bool)
    strength = np.asarray(strength, float)
    if labels.shape != interior.shape or strength.shape != labels.shape:
        raise ValueError(
            'Region labels, mask and crease evidence must share a frame')
    if not np.any(labels):
        return labels
    pairs = {}
    hh, ww = labels.shape
    for y, x in zip(*np.nonzero((labels == 0) & interior)):
        neighbours = labels[max(0, y - 1):y + 2, max(0, x - 1):x + 2]
        ids = np.unique(neighbours[neighbours > 0])
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                total, count = pairs.get((a, b), (0., 0))
                pairs[a, b] = (total + strength[y, x], count + 1)
    parent = np.arange(int(labels.max()) + 1)

    def root(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    strong = [pair for pair, (total, count) in pairs.items()
              if total / count >= threshold]
    ordered = sorted(pairs.items(
    ), key=lambda item: item[1][0] / item[1][1]) if protect_strong else pairs.items()
    for (a, b), (total, count) in ordered:
        if total / count < threshold:
            if protect_strong and any({root(c), root(d)} == {root(a), root(b)} for c, d in strong):
                continue
            parent[root(a)] = root(b)
    roots = np.array([root(i) for i in range(len(parent))])
    result = roots[labels]
    result[~interior] = 0
    weak = (result == 0) & interior & (strength < threshold)
    nearest = ndimage.distance_transform_edt(
        result == 0, return_distances=False, return_indices=True)
    result[weak] = result[nearest[0][weak], nearest[1][weak]]
    return result


def crease_evidence(log_luminance, mask, sigma):
    """Original relief principle: darkness relative to a masked neighbourhood."""
    mask = np.asarray(mask, bool)
    mean = ndimage.gaussian_filter(np.where(mask, log_luminance, 0.), sigma) / np.maximum(
        ndimage.gaussian_filter(mask.astype(float), sigma), 1e-6)
    cavity = np.maximum(0., mean - log_luminance) * mask
    scale = float(np.percentile(cavity[mask], 95)) if mask.any() else 0.
    return np.clip(cavity / max(scale, .03), 0, 1)
