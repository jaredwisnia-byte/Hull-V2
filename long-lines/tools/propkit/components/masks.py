"""Explicit source masks for apertures that ordinary silhouette filling removes."""
import numpy as np
from PIL import Image


def masked_crop(reference, mask_path, box):
    with Image.open(mask_path) as source:
        if source.size != reference.size:
            raise ValueError("explicit mask must match its reference canvas")
        mask = np.asarray(source.convert("L").crop(box)) >= 128
    y, x = np.nonzero(mask)
    if not len(x):
        raise ValueError("explicit mask has no foreground in crop")
    bounds = (int(x.min()), int(y.min()), int(x.max()+1), int(y.max()+1))
    return mask[bounds[1]:bounds[3], bounds[0]:bounds[2]], reference.crop(box).crop(bounds), bounds
