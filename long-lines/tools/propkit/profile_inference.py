"""Software-only cross-view profiles, construction bands and continuous valleys.

All coordinates are inferred from masks. There are no object names or supplied
shaft boxes. Absolute scale remains the responsibility of the sizing station.
"""
import numpy as np
from scipy import ndimage, signal, interpolate, optimize


def elevation(mask, image, samples=161):
    mask = np.asarray(mask, bool)
    rgb = np.asarray(image, float) / 255
    height = len(mask)
    left = np.array([np.flatnonzero(row)[0] if row.any()
                    else np.nan for row in mask])
    right = np.array([np.flatnonzero(row)[-1] if row.any()
                     else np.nan for row in mask])
    valid = np.isfinite(left)
    rows = np.arange(height)
    left = np.interp(rows, rows[valid], left[valid])
    right = np.interp(rows, rows[valid], right[valid])
    width = right - left + 1
    center = (left + right) / 2
    u = np.linspace(-1, 1, samples)
    x = center[:, None] + u[None, :] * (width[:, None] - 1) / 2
    y = np.broadcast_to(rows[:, None], x.shape)
    colours = np.stack([ndimage.map_coordinates(rgb[:, :, channel], [y, x], order=1)
                        for channel in range(3)], axis=-1)
    return {'width': width, 'center': center, 'rgb': colours, 'u': u, 'rows': rows, 'image_width': mask.shape[1]}


def construction_regions(profiles):
    """Find a long tapered span from cross-view width derivatives; retain other
    regions as independently identified construction bands, not false cylinders."""
    count = min(len(profile['width']) for profile in profiles.values())
    z = np.linspace(0, 1, count)
    widths = np.array([np.interp(z, np.linspace(0, 1, len(p['width'])), p['width'] / len(p['width']))
                       for p in profiles.values()])
    width = np.median(widths, axis=0)
    smooth = ndimage.gaussian_filter1d(width, max(1, count * .008))
    curvature = np.abs(np.gradient(np.gradient(smooth)))
    stable = (smooth < .8 * np.max(smooth)) & (curvature <
                                               np.quantile(curvature, .65))
    stable[:int(count * .08)] = False
    stable[-int(count * .08):] = False
    stable = ndimage.binary_closing(
        stable, iterations=max(1, int(count * .012)))
    labels, n = ndimage.label(stable)
    spans = [sl[0] for sl in ndimage.find_objects(labels)]
    shaft = max(spans, key=lambda s: s.stop - s.start, default=None)
    if shaft is None or shaft.stop - shaft.start < count * .2:
        return [], None
    # Collars split a smooth run sharply. Use the inferred run's endpoints, not
    # any annotation, filename or fixed image coordinate.
    start, stop = shaft.start / count, shaft.stop / count
    rows = np.arange(shaft.start, shaft.stop)
    coefficients = np.polyfit(z[rows], smooth[rows], 2)
    fit = optimize.least_squares(lambda c: np.polyval(c, z[rows]) - smooth[rows],
                                 coefficients, loss='soft_l1', f_scale=np.median(smooth[rows]) * .015)
    linear = np.abs(np.polyval(
        fit.x, z[rows]) - smooth[rows]) < np.median(smooth[rows]) * .07
    runs = ndimage.find_objects(ndimage.label(linear)[0])
    if runs:
        longest = max(runs, key=lambda s: s[0].stop - s[0].start)[0]
        shaft = slice(shaft.start + longest.start, shaft.start + longest.stop)
        start, stop = shaft.start / count, shaft.stop / count
    peaks, properties = signal.find_peaks(curvature, prominence=np.quantile(
        curvature, .8), distance=max(2, int(count * .06)))
    # Construction regions are modelling stations, not every edge in painted
    # ornament. Keep only the strongest changes outside the smooth shaft.
    peaks = sorted((int(peaks[i]) for i in np.argsort(properties['prominences'])[::-1]
                    if not shaft.start < peaks[i] < shaft.stop), key=lambda p: -curvature[p])[:4]
    cuts = sorted(set([0, count, shaft.start, shaft.stop] + [int(p) for p in peaks
                                                             if not shaft.start < p < shaft.stop]))
    regions = [{'id': f'region_{i:03d}', 'v': [a / count, b / count],
                'model': 'spline_shaft' if a == shaft.start and b == shaft.stop else 'visual_hull'}
               for i, (a, b) in enumerate(zip(cuts, cuts[1:])) if b - a >= max(2, count * .008)]
    return regions, (start, stop)


def fit_axis(profiles, band):
    """Joint orthographic axis fit: shared nonlinear 3D bend plus per-view roll.
    Linear tilt is a coordinate gauge, not uniquely observable absolute pose.
    This intentionally does not claim arbitrary perspective calibration."""
    directions = {'front': (1, 0), 'back': (-1, 0),
                  'right': (0, 1), 'left': (0, -1)}
    names = [name for name in profiles if name in directions]
    t = np.linspace(-1, 1, 80)
    # Remove constant/linear parts from the curvature basis to separate the gauge.
    bend = np.stack([t * t - np.mean(t * t), t**3 - t *
                    np.sum(t**4) / np.sum(t * t)], axis=1)
    observations = []
    for name in names:
        profile = profiles[name]
        h = len(profile['center'])
        rows = np.linspace(band[0] * h, band[1] * h - 1, len(t))
        center = np.interp(rows, np.arange(h), profile['center']) / h
        observations.append(center - np.mean(center))
    observed = np.asarray(observations)

    def residual(parameters):
        curves = parameters[:4].reshape(2, 2) @ bend.T
        predicted = np.array([np.asarray(directions[name]) @ curves + parameters[4 + i] * t
                              for i, name in enumerate(names)])
        return np.r_[(predicted - observed).ravel(), parameters[:4] * .01]
    solution = optimize.least_squares(residual, np.zeros(
        4 + len(names)), loss='soft_l1', f_scale=.002)
    span = (band[1] - band[0]) / 2
    return {'roll_degrees': {name: float(np.degrees(np.arctan(solution.x[4 + i] / span)))
                             for i, name in enumerate(names)},
            'bend_coefficients': solution.x[:4].reshape(2, 2).tolist(),
            'residual_rms': float(np.sqrt(np.mean(residual(solution.x)**2))),
            'pivot_v': float(np.mean(band)),
            'gauge': 'linear tilt attributed to camera; absolute camera/object tilt ambiguous',
            'projection': 'orthographic axis model; no arbitrary perspective recovery'}


def trace_valleys(profile, band):
    """Longitudinal, scale-normalized channels with curvature-smoothed paths.
    Jointly remove smooth illumination and colour-dependent reflectance first.
    Dark stripes alone remain ambiguous; fit/validation records their support."""
    h = len(profile['rgb'])
    start, stop = (int(v * h) for v in band)
    rgb = profile['rgb'][start:stop]
    luminance = np.log(np.maximum(rgb @ [.299, .587, .114], .01))
    chroma = np.log(np.maximum(rgb, .01)) - \
        np.log(np.maximum(rgb.mean(2, keepdims=True), .01))
    # Alternate a broad illumination term and colour-correlated material term.
    design = np.c_[np.ones(luminance.size), chroma.reshape(-1, 3)]
    material = np.zeros_like(luminance)
    for _ in range(4):
        illumination = ndimage.gaussian_filter(
            luminance - material, (max(1, len(rgb) * .06), 8))
        coefficients = np.linalg.lstsq(
            design, (luminance - illumination).ravel(), rcond=None)[0]
        material = (design @ coefficients).reshape(luminance.shape)
    residual = luminance - material - illumination
    darkness = - \
        ndimage.gaussian_filter(residual, (max(1, len(rgb) * .02), 1.5))
    score = np.median(darkness, axis=0)
    peaks, properties = signal.find_peaks(
        score, prominence=max(.012, float(np.std(score)) * .6), distance=12)
    result = []
    for index, prominence in zip(peaks, properties['prominences']):
        if abs(profile['u'][index]) > .8:
            continue
        lo, hi = max(0, index - 9), min(len(score), index + 10)
        locations = np.argmax(darkness[:, lo:hi], axis=1) + lo
        rows = np.arange(len(locations))
        spline = interpolate.UnivariateSpline(
            rows, profile['u'][locations], s=len(rows) * .0003)
        path = spline(rows)
        support = float(np.mean(darkness[rows, locations] > .01))
        if support < .55:
            continue
        width = float(signal.peak_widths(score, [index], rel_height=.5)[
                      0][0]) * 2 / (len(score) - 1)
        result.append({'u': float(profile['u'][index]), 'path_u': path.tolist(),
                       'width_u': max(.025, min(.3, width)), 'prominence': float(prominence),
                       'support': support, 'v': list(band),
                       'evidence': 'persistent intensity valley after smooth lighting/chromatic material fit'})
    return result, {'illumination_rms': float(np.std(illumination)),
                    'material_coefficients': coefficients.tolist(),
                    'unexplained_rms': float(np.std(residual)),
                    'ambiguity': 'achromatic paint stripes can mimic grooves'}


def groove_map(profile, grooves, max_depth_fraction=.035):
    """Signed channel hypothesis in image pixels, with smooth end closures.
    Physical depth is bounded from observed width and reported as inferred."""
    height = len(profile['width'])
    output = np.zeros((height, len(profile['u'])))
    for groove in grooves:
        start, stop = (int(v * height) for v in groove['v'])
        path = np.asarray(groove['path_u'])
        width = groove['width_u']
        distance = (profile['u'][None, :] -
                    path[:, None]) / max(width * .6, .01)
        closure = np.sin(np.linspace(0, np.pi, len(path)))**.4
        depth = np.minimum(profile['width'][start:stop] * max_depth_fraction,
                           profile['width'][start:stop] * groove['fit']['depth_fraction'])
        output[start:stop] -= np.exp(-distance**4) * \
            depth[:, None] * closure[:, None]
        groove['depth_px_median'] = float(np.median(depth))
        groove['depth_status'] = 'bounded geometric hypothesis, not measured depth'
    return output


def fit_channel(profile, groove):
    """Bounded inverse rendering of a channel, illumination and smooth albedo.

    Constant/linear albedo and a fixed light gauge prevent arbitrary per-pixel
    paint from explaining every shape. A flat fit is retained for comparison.
    Achromatic paint remains a real ambiguity and is explicitly recorded.
    """
    h = len(profile['rgb'])
    first, last = (int(v * h) for v in groove['v'])
    rgb = profile['rgb'][first:last: max(1, (last - first) // 48)]
    path = np.asarray(groove['path_u'])[::max(1, (last - first) // 48)]
    u = profile['u']
    width = groove['width_u']
    keep = np.abs(u - groove['u']) < width * 1.8
    keep &= np.abs(u) < .95
    x = np.broadcast_to(u[keep], (len(rgb), keep.sum()))
    observed = np.log(np.maximum(rgb[:, keep] @ [.299, .587, .114], .02))
    chroma = np.log(np.maximum(rgb[:, keep], .02))
    chroma = chroma - chroma.mean(2, keepdims=True)
    distance = (x - path[:, None]) / max(width * .6, .02)
    shape = -np.exp(-distance**4)
    # Normal derivatives are in units of full shaft width, not image pixels.
    derivative = 4 * distance**3 * \
        np.exp(-distance**4) / max(width * .6, .02) * 2
    base_slope = -x / np.sqrt(np.maximum(1 - x * x, .01))
    upper = min(.06, width * .3)

    def predict(parameters, depth):
        slope = base_slope + depth * derivative
        nx = -slope / np.sqrt(1 + slope * slope)
        ny = 1 / np.sqrt(1 + slope * slope)
        light = np.maximum(.05, 1 + parameters[0] * nx + parameters[1] * ny)
        # A recess also blocks part of the ambient hemisphere. Without this
        # term a flat channel floor is incorrectly predicted to be as bright as
        # the surrounding flat surface, regardless of its depth.
        visibility = 1 - .5 * depth / \
            np.sqrt(depth * depth + (width * .3)**2) * np.exp(-distance**4)
        material = parameters[2] + parameters[3] * x + \
            np.einsum('ijk,k->ij', chroma, parameters[4:7])
        return material + np.log(light) + np.log(visibility)

    def residual(parameters, fixed_depth=None):
        depth = parameters[-1] if fixed_depth is None else fixed_depth
        p = parameters[:7]
        return np.r_[(predict(p, depth) - observed).ravel(), p[:2] * .15, p[3:] * .1]
    seed = np.array([0, .3, float(observed.mean()), 0, 0, 0, 0])
    lower = [-.7, -.7, -5, -1, -1, -1, -1]
    higher = [.7, .7, 1, 1, 1, 1, 1]
    flat = optimize.least_squares(lambda p: residual(p, 0), seed, bounds=(
        lower, higher), loss='soft_l1', f_scale=.05, max_nfev=80)
    curved = optimize.least_squares(residual, np.r_[flat.x, upper * .3],
                                    bounds=(lower + [0], higher + [upper]), loss='soft_l1', f_scale=.05, max_nfev=120)
    flat_error = float(np.mean((predict(flat.x, 0) - observed)**2))
    error = float(np.mean((predict(curved.x[:7], curved.x[-1]) - observed)**2))
    # A painted stripe is a competing explanation, not a flat constant albedo.
    # Retain the bounded channel hypothesis while reporting this ambiguity.

    def painted_residual(parameters):
        prediction = predict(parameters[:7], 0) + parameters[7] * (-shape)
        return np.r_[(prediction - observed).ravel(), parameters[:2] * .15, parameters[3:7] * .1]
    painted = optimize.least_squares(painted_residual, np.r_[flat.x, -.1],
                                     bounds=(lower + [-1.5], higher + [1.5]), loss='soft_l1', f_scale=.05, max_nfev=80)
    painted_error = float(
        np.mean((predict(painted.x[:7], 0) + painted.x[7] * (-shape) - observed)**2))
    gain = 1 - error / max(flat_error, 1e-8)
    # Penalize the extra shape parameter; reject estimates at the search bound.
    accepted = gain > .04 and curved.x[-1] > upper * \
        .02 and curved.x[-1] < upper * .98
    return {'depth_fraction': float(curved.x[-1]) if accepted else 0,
            'candidate_depth_fraction': float(curved.x[-1]), 'accepted': bool(accepted),
            'flat_mse': flat_error, 'shape_mse': error, 'improvement': float(gain),
            'paint_mse': painted_error, 'ambiguous_with_paint': bool(painted_error <= error * 1.1),
            'lighting': curved.x[:2].tolist(), 'albedo': curved.x[2:7].tolist(),
            'depth_status': 'joint bounded shading/material hypothesis; not metric ground truth'}


def analyse(profiles, guide_band=None):
    regions, band = construction_regions(profiles)
    if band is None:
        return {'status': 'not_applicable', 'regions': regions}, {}
    if guide_band is not None:
        band = (max(band[0], guide_band[0]), min(band[1], guide_band[1]))
    if band[1] - band[0] < .15:
        return {'status': 'insufficient_profile_span', 'regions': regions}, {}
    cameras = fit_axis(profiles, band)
    maps = {}
    observations = {}
    for name, profile in profiles.items():
        grooves, intrinsics = trace_valleys(profile, band)
        for groove in grooves:
            groove['fit'] = fit_channel(profile, groove)
        accepted = [g for g in grooves if g['fit']['accepted']]
        maps[name] = groove_map(profile, accepted)
        observations[name] = {'grooves': grooves, 'appearance': intrinsics}
    return {'status': 'fitted', 'band': list(band), 'regions': regions,
            'camera_axis_fit': cameras, 'views': observations,
            'limitations': ['achromatic paint ambiguity', 'orthographic profile-family restriction']}, maps


def feature_identities(report):
    """One physical channel per angular cluster, retaining every observation.
    This is appropriate only for the fitted rounded shaft family."""
    observations = []
    for view, evidence in report.get('views', {}).items():
        for index, groove in enumerate(evidence['grooves']):
            if not groove['fit']['accepted']:
                continue
            u = np.clip(groove['u'], -1, 1)
            angle = {'front': -np.arccos(u), 'back': np.arccos(-u),
                     'right': np.arcsin(u), 'left': np.pi + np.arcsin(u)}[view]
            observations.append({'view': view, 'index': index, 'angle': float(angle % (2 * np.pi)),
                                 'width': groove['width_u'] / max(.4, np.sqrt(1 - u * u)),
                                 'ambiguous_with_paint': groove['fit'].get('ambiguous_with_paint', True),
                                 'depth_fraction': groove['fit']['depth_fraction']})
    groups = []
    for observation in sorted(observations, key=lambda item: item['angle']):
        group = next((group for group in groups
                      if abs(np.angle(np.exp(1j * (observation['angle'] - group['angle'])))) < .18), None)
        if group is None:
            groups.append({'id': f'channel_{len(groups):03d}', 'angle': observation['angle'],
                           'observations': [observation]})
        else:
            group['observations'].append(observation)
            group['angle'] = float(
                np.angle(np.mean([np.exp(1j * o['angle']) for o in group['observations']])))
    for group in groups:
        group['width'] = float(np.median([o['width']
                               for o in group['observations']]))
        group['depth_fraction'] = float(
            np.median([o['depth_fraction'] for o in group['observations']]))
        group['cross_view_support'] = len(
            set(o['view'] for o in group['observations']))
        group['uncertain'] = group['cross_view_support'] < 2 or any(
            o['ambiguous_with_paint'] for o in group['observations'])
    return groups
