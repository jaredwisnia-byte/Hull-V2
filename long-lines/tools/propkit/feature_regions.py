"""Trace internal image boundaries and isolate candidate relief regions.

Regions are observations, not physical parts or assertions of groove depth.
No object vocabulary or geometric templates are used.
"""
import numpy as np
from scipy import ndimage
from skimage.feature import canny, peak_local_max
from skimage.segmentation import watershed
from skimage.measure import find_contours


def trace(rgb, mask):
    """Accept linear RGB in the same pixel frame as the foreground mask."""
    rgb = np.asarray(rgb, float)
    mask = np.asarray(mask, bool)
    if mask.ndim != 2 or min(mask.shape) < 3:
        raise ValueError(
            'A two-dimensional image at least three pixels wide and high is required')
    if rgb.shape != (*mask.shape, 3) or not np.isfinite(rgb).all():
        raise ValueError('Finite RGB and matching foreground mask required')
    interior = ndimage.binary_erosion(mask, iterations=2)
    luminance = np.log(np.maximum(rgb @ [.2126, .7152, .0722], .003))
    chroma = np.log(np.maximum(rgb, .003)) - \
        np.log(np.maximum(rgb.mean(2, keepdims=True), .003))
    scale = max(1., min(mask.shape) / 180)
    edges = canny(luminance, sigma=scale, mask=interior)
    broad = canny(luminance, sigma=scale * 2, mask=interior)
    persistent = edges & ndimage.binary_dilation(
        broad, iterations=max(1, round(scale * 2)))
    chroma_gradient = np.sqrt(sum(sum(
        g * g for g in np.gradient(ndimage.gaussian_filter(chroma[..., c], scale))) for c in range(3)))
    colour_boundary = chroma_gradient > .06 / scale
    # Colour evidence marks appearance ambiguity; it never chooses a depth sign.
    relief_boundary = persistent & ~ndimage.binary_dilation(
        colour_boundary, iterations=1)
    barrier = ndimage.binary_closing(
        persistent, iterations=max(1, round(scale))) & interior
    distance = ndimage.distance_transform_edt(mask & ~barrier)
    peaks = peak_local_max(distance, min_distance=max(3, round(scale * 4)),
                           threshold_abs=max(2, scale * 2), labels=mask.astype(np.uint8), num_peaks=256)
    markers = np.zeros(mask.shape, np.int32)
    for identifier, (y, x) in enumerate(peaks, 1):
        markers[y, x] = identifier
    labels = watershed(-distance, markers, mask=mask,
                       watershed_line=True) if len(peaks) else markers
    from .region_grouping import merge_weak_lines, crease_evidence
    fragment_count = len(np.unique(labels[labels > 0]))
    cavity = crease_evidence(luminance, mask, scale * 6)
    labels = merge_weak_lines(labels, mask, cavity, protect_strong=True)
    regions = []
    minimum = max(20, int(mask.sum() * .0005))
    cleaned = np.zeros_like(labels)
    for identifier in np.unique(labels[labels > 0]):
        selected = labels == identifier
        if selected.sum() < minimum:
            continue
        rim = ndimage.binary_dilation(selected) & ~selected & interior
        support = float((ndimage.binary_dilation(persistent)
                        & rim).sum() / max(1, rim.sum()))
        if support < .15:
            continue
        number = len(regions) + 1
        cleaned[selected] = number
        contours = [np.c_[c[:, 1] - 1, c[:, 0] - 1].tolist() for c in
                    find_contours(np.pad(selected.astype(float), 1), .5)]
        regions.append({'id': number, 'area_px': int(selected.sum()), 'boundary_support': support,
                        'contours_xy': contours, 'depth_sign': 'unresolved',
                        'status': 'candidate_requires_surface_validation'})
    curves = [np.c_[c[:, 1], c[:, 0]].tolist() for c in find_contours(
        persistent.astype(float), .5) if len(c) >= 6]
    return {'labels': cleaned, 'boundaries': persistent, 'relief_boundaries': relief_boundary,
            'appearance_boundaries': persistent & ~relief_boundary, 'regions': regions, 'edge_curves_xy': curves,
            'method': 'multiscale image edges / chromatic ambiguity / marker watershed',
            'physical_parts_created': False, 'fragment_count': fragment_count,
            'grouping': 'shared original weak-crease merging; no geometry templates'}


def export(result, image, directory, name):
    """Save exact-frame contours, region labels and an inspectable overlay."""
    import json
    from pathlib import Path
    from PIL import Image, ImageDraw
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    canvas = image.convert('RGB').copy()
    if canvas.size != result['labels'].shape[::-1]:
        canvas = canvas.resize(result['labels'].shape[::-1])
    pixels = np.asarray(canvas).copy()
    pixels[result['relief_boundaries']] = [40, 255, 130]
    pixels[result['appearance_boundaries']] = [255, 150, 40]
    canvas = Image.fromarray(pixels)
    overlay = directory / (name + '-feature-regions.png')
    canvas.save(overlay)
    draw = ImageDraw.Draw(canvas)
    for region in sorted(result['regions'], key=lambda r: -r['area_px'])[:32]:
        y, x = np.nonzero(result['labels'] == region['id'])
        draw.text((float(np.median(x)), float(np.median(y))),
                  str(region['id']), fill='cyan')
    labelled = directory / (name + '-feature-labels.png')
    canvas.save(labelled)
    np.savez_compressed(directory / (name + '-feature-regions.npz'), **{k: result[k] for k in
                        ('labels', 'boundaries', 'relief_boundaries', 'appearance_boundaries')})
    report = {k: v for k, v in result.items() if not isinstance(v, np.ndarray)}
    report.update(coordinate_frame='analysis grid pixel centres; x right, y down',
                  image_size=list(canvas.size), overlay=str(overlay), label_overlay=str(labelled),
                  legend={'green': 'persistent intensity edge without strong colour change; not geometry confidence',
                          'orange': 'persistent intensity edge with colour change; not geometry confidence'})
    (directory / (name + '-feature-regions.json')
     ).write_text(json.dumps(report, indent=2))
    return report
