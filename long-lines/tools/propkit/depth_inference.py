"""Evidence-first depth estimates and conservative selection of existing relief.

Dimensions remain estimates when source scale/camera orientation is inferred.
No object names, per-image coordinates or runtime LLM calls are used here.
"""
import numpy as np


def profile_depth(height_m, profiles, prior):
    """Side masks share the front's height axis; thin mounting pins are excluded
    by the median occupied row width. Opposite-side conflicts stay explicit."""
    if not np.isfinite(height_m) or height_m <= 0:
        raise ValueError('height must be positive and finite')
    lo, hi = map(float, prior)
    if not 0 < lo <= hi:
        raise ValueError('invalid physical prior')
    observations = []
    for view, mask in profiles.items():
        mask = np.asarray(mask, dtype=bool)
        if mask.ndim != 2:
            raise ValueError('profile must be a 2D mask')
        ys, xs = np.nonzero(mask)
        if not len(xs):
            continue
        tile = mask[ys.min():ys.max()+1, xs.min():xs.max()+1]
        spans = [np.ptp(np.nonzero(row)[0])+1 for row in tile if row.any()]
        width = float(np.median(spans))
        if tile.shape[0] < 8 or width < 3:
            continue
        ratio = width/tile.shape[0]
        if ratio > 2:  # likely a face misclassified as a profile
            continue
        observations.append({'view': view, 'depth_m': float(height_m*ratio),
                             'profile_height_px': int(tile.shape[0]), 'median_span_px': width})
    values = [o['depth_m'] for o in observations]
    conflict = bool(values and (max(values)-min(values))/max(values) > .2)
    if values and not conflict:
        depth = float(np.median(values))
        return {'depth_m': depth, 'source': 'side_profile', 'confidence': .9 if len(values) > 1 else .7,
                'observations': observations, 'needs_review': not lo <= depth <= hi,
                'prior_conflict': not lo <= depth <= hi, 'prior_range_m': [lo, hi]}
    return {'depth_m': (lo+hi)/2, 'source': 'physical_prior', 'confidence': .2,
            'observations': observations, 'needs_review': True, 'profile_conflict': conflict,
            'prior_range_m': [lo, hi]}


def select_relief(observed, candidates, light, mask, min_score=.15, margin=.05):
    """Compare fixed-light height hypotheses with flat paint. Positive lighting
    gain prevents an inverted surface winning by fitting negative illumination."""
    scores = {'flat': 0.0}
    mask = np.asarray(mask, dtype=bool)
    signal = np.asarray(observed, dtype=float)[mask]
    if len(signal) < 20 or np.var(signal) < 1e-8:
        return 'flat', scores
    signal = signal-signal.mean()
    for name, height in candidates.items():
        gy, gx = np.gradient(height)
        predicted = (-gx*light[0]-gy*light[1])[mask]
        predicted = predicted-predicted.mean()
        gain = max(0, float(predicted@signal) /
                   max(float(predicted@predicted), 1e-12))
        scores[name] = float(
            1-np.sum((signal-gain*predicted)**2)/np.sum(signal**2))
    ranked = sorted(scores, key=scores.get, reverse=True)
    winner = ranked[0]
    if scores[winner] < min_score or scores[winner]-scores[ranked[1]] < margin:
        winner = 'flat'
    return winner, scores


def body_hook(views, W, D, H, report, exclusions=(), keep_high=False):
    """Reuse relief segmentation/displacement, but compare hypotheses first and
    suppress regions already owned by separately manufactured components."""
    from . import relief
    from .hull import silhouette
    from scipy import ndimage
    light = relief.shared_light(views)
    maps = {}
    for view, path in views.items():
        if view not in relief.ELEVATIONS:
            continue
        mask, image = silhouette(path)
        regions = []
        height, evidence = relief.view_relief(
            path, view, light, region_masks=regions)
        lum = relief._lum(image, mask)
        observed = lum-relief._local_mean(lum, mask, 8)
        valid = ndimage.binary_erosion(mask, iterations=3)
        for excluded_view, box in exclusions:
            if excluded_view != view:
                continue
            x0, y0, x1, y1 = box
            hh, ww = mask.shape
            valid[max(0, int(y0*hh)-2):min(hh, int(np.ceil(y1*hh))+2),
                  max(0, int(x0*ww)-2):min(ww, int(np.ceil(x1*ww))+2)] = False
        height = np.where(valid, height, 0)
        # Evaluate the existing physical regions separately: wood colour variation
        # elsewhere on the object must not veto an otherwise supported groove.
        selected = np.zeros_like(height)
        decisions = []
        for index, region in enumerate(regions):
            local_mask = region & valid
            chosen, scores = select_relief(
                observed, {"relief": height}, light, local_mask)
            if chosen == "relief":
                selected[local_mask] = height[local_mask]
            decisions.append({"region": index, "selected": chosen, "scores": scores,
                              "pixels": int(local_mask.sum())})
        maps[view] = ndimage.gaussian_filter(selected, .7) * valid
        accepted = sum(item["selected"] == "relief" for item in decisions)
        report.setdefault("views", {})[view] = {
            "selected": "regional" if accepted else "flat", "accepted_regions": accepted,
            "tested_regions": len(decisions), "regions": decisions, "evidence": evidence,
            "depth_source": "local_shading_hypothesis_not_measurement",
        }
    return relief.hook(views, W, D, H, report, maps_override=maps,
                       keep_high=keep_high, cap_share=.02, light_override=light)
