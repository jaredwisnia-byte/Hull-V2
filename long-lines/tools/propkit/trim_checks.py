"""Source-aware checks for the extrude line. No Blender dependency in this module.

The profile comparison tests the exported cap geometry against the source section;
it must not test only the profile that the generator *intended* to create.
"""
import hashlib
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

BG_MAX = 48


def foreground(path):
    """Largest painted connected component, filled and cropped to its actual bounds."""
    im = np.asarray(Image.open(path).convert("RGB"))
    binary = im.max(axis=2) > BG_MAX
    labels, count = ndimage.label(binary)
    if not count:
        return None
    sizes = np.bincount(labels.ravel())
    sizes[0] = 0
    mask = ndimage.binary_fill_holes(labels == sizes.argmax())
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return None
    return mask[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


def normalized(mask, n=128):
    return np.asarray(Image.fromarray(mask.astype("uint8") * 255).resize((n, n), Image.Resampling.NEAREST)) > 127


def exported_section(vertices, faces, n=128):
    """Rasterize the actual GLB end-cap polygons (the Y/Z cross-section)."""
    verts = np.asarray([[float(c) for c in v] for v in vertices], dtype=float)
    if len(verts) < 3:
        return None, None
    lo, hi = verts.min(axis=0), verts.max(axis=0)
    depth, height = hi[1] - lo[1], hi[2] - lo[2]
    if depth <= 1e-6 or height <= 1e-6:
        return None, None
    eps = max(1e-4, (hi[0] - lo[0]) * 0.001)
    img = Image.new("1", (n, n))
    pen = ImageDraw.Draw(img)
    found = False
    for poly in faces:
        if len(poly) < 3 or not all(abs(verts[i, 0] - lo[0]) <= eps for i in poly):
            continue
        coords = [((verts[i, 1] - lo[1]) / depth * (n - 1),
                   (hi[2] - verts[i, 2]) / height * (n - 1)) for i in poly]
        pen.polygon(coords, fill=1)
        found = True
    return (np.asarray(img).astype(bool) if found else None), depth / height


def section_match(source, vertices, faces):
    """Return shape IoU and proportion error (0 is ideal); no cap = hard failure."""
    ref = foreground(source)
    got, aspect = exported_section(vertices, faces)
    if ref is None or got is None:
        return None
    target = normalized(ref)
    area_union = lambda a, b: max(int(np.logical_or(a, b).sum()), 1)
    iou = max(float(np.logical_and(got, target).sum()) / area_union(got, target),
              float(np.logical_and(got[:, ::-1], target).sum()) / area_union(got[:, ::-1], target))
    reference_aspect = ref.shape[1] / ref.shape[0]
    relative_error = abs(aspect / reference_aspect - 1)
    return round(iou, 3), round(relative_error, 3)


def opening_from_paint(path, method="strict"):
    """Find a dark central void. `interior` is the one-retry path for U-shaped frames."""
    a = np.asarray(Image.open(path).convert("RGB"))
    mask = a.max(axis=2) > BG_MAX
    h, w = mask.shape
    bg = ~mask
    labels, count = ndimage.label(bg)
    candidates = []
    for k in range(1, count + 1):
        ys, xs = np.nonzero(labels == k)
        if len(xs) < .06 * h * w:
            continue
        x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
        if x0 <= 0 or x1 >= w or y0 <= 0 or x1 - x0 < .20 * w:
            continue
        candidates.append((len(xs), (x0 / w, y0 / h, x1 / w, y1 / h)))
    if candidates:
        return max(candidates)[1]
    if method != "interior":
        return None
    rows = []
    mid = w // 2
    for y in range(int(h * .12), int(h * .94)):
        left = np.flatnonzero(mask[y, :mid])
        right = np.flatnonzero(mask[y, mid:])
        if not len(left) or not len(right):
            continue
        inner_left, inner_right = int(left[-1]) + 1, mid + int(right[0])
        if inner_right - inner_left < .18 * w:
            continue
        if bg[y, inner_left:inner_right].mean() < .6:
            continue
        rows.append((y, inner_left, inner_right))
    if len(rows) < .15 * h:
        return None
    left = int(np.median([r[1] for r in rows]))
    right = int(np.median([r[2] for r in rows]))
    return left / w, rows[0][0] / h, right / w, (rows[-1][0] + 1) / h


def geometry_signature(vertices, faces=None, decimals=3):
    """Stable fingerprint for mesh shape and topology, independent of vertex indexing.

    Rounds positions to the nearest millimetre to avoid tiny float differences.
    A change to face connectivity also changes the fingerprint.
    """
    points = [tuple(round(float(c), decimals) for c in v) for v in vertices]
    key = sorted(points)
    if faces is not None:
        polygons = sorted(tuple(sorted(points[i] for i in face)) for face in faces)
        key = (key, polygons)
    return hashlib.sha256(repr(key).encode("ascii")).hexdigest()[:20]


def texture_difference(source, baked):
    """Coarse texture-colour validation, not a pixel-by-pixel visual match.

    The atlas and its baked UV islands have different layouts. This compares the
    median RGB of the painted source foreground against non-background baked pixels.
    Returns a normalized 0..1 RGB difference, or None for unusable input.
    """
    src = np.asarray(Image.open(source).convert("RGB"), dtype=np.float32)
    mask = src.max(axis=2) > BG_MAX
    if not mask.any():
        return None
    tex = np.asarray(Image.open(baked).convert("RGB"), dtype=np.float32)
    # The bake background is commonly black; exclude it when sufficiently distinct.
    occupied = tex.max(axis=2) > 24
    if occupied.mean() < .01:
        return None
    src_rgb = np.median(src[mask], axis=0)
    dst_rgb = np.median(tex[occupied], axis=0)
    return round(float(np.linalg.norm(src_rgb - dst_rgb) / (255 * np.sqrt(3))), 3)


def colour_signature(path):
    """Coarse baked-pixel statistics. UV packing may move islands, so not pixel hashes."""
    a = np.asarray(Image.open(path).convert("RGB"), dtype=np.float32)
    return [int(round(float(v) / 8)) for v in np.r_[a.mean(axis=(0, 1)), a.std(axis=(0, 1))]]
