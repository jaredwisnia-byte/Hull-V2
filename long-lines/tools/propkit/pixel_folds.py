"""Deterministic spatially balanced pixel folds, independent of image values."""
import numpy as np


def balanced(shape, seed=1975):
    """Every full 3x3 block contains each fold once, without fixed row phases."""
    hh, ww = shape
    rng = np.random.default_rng(seed)
    order = np.argsort(rng.random(((hh + 2) // 3, (ww + 2) // 3, 9)), axis=2)
    result = np.empty((hh, ww), np.uint8)
    for row in range(3):
        for col in range(3):
            target = result[row::3, col::3]
            target[:] = order[:target.shape[0],
                              :target.shape[1], row * 3 + col]
    return result
