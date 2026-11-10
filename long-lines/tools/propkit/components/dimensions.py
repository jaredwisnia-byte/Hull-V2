"""Scale orthographic silhouettes using an explicit height anchor, never guessed depth."""
import math


def from_height(front_size, side_size, height_m):
    values = [*front_size, *side_size, height_m]
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0 for v in values):
        raise ValueError("silhouette sizes and height anchor must be positive finite numbers")
    fw, fh = front_size
    sw, sh = side_size
    # Each drawing may have a different pixel scale.
    return [height_m * fw / fh, height_m * sw / sh, height_m]
