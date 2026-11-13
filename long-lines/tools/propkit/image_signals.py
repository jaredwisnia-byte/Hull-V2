"""Small image measurements shared by reconstruction stages."""

import numpy as np
from scipy import ndimage

CAVITY_SIGMA = 6.0


def masked_luminance(image, mask):
    rgb = np.asarray(image.convert("RGB")).astype(float) / 255
    return np.where(mask, rgb @ [0.299, 0.587, 0.114], 0)


def masked_local_mean(values, mask, sigma):
    return ndimage.gaussian_filter(np.where(mask, values, 0), sigma) / np.maximum(
        ndimage.gaussian_filter(mask.astype(float), sigma), 1e-3)
