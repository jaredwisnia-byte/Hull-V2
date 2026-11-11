"""Continuous shape-from-shading, with explicit reflectance and depth ambiguity.

The unknown is a height at every valid pixel, never a sphere/groove template.
Differentiating that height gives an integrable normal field. A coarse surface,
material-colour model, smoothness and silhouette boundaries constrain the inverse
problem; brightness itself is never treated as height.
"""
import numpy as np
from scipy import ndimage, optimize


def gradients(height):
    p = np.zeros_like(height)
    q = np.zeros_like(height)
    p[:, :-1] = np.diff(height, axis=1)
    q[:-1] = np.diff(height, axis=0)
    return p, q


def adjoint(p, q):
    result = np.zeros_like(p)
    result[:, :-1] -= p[:, :-1]
    result[:, 1:] += p[:, :-1]
    result[:-1] -= q[:-1]
    result[1:] += q[:-1]
    return result


def illumination(height, light, ambient=.25, derivatives=False):
    p, q = gradients(height)
    length = np.sqrt(1 + p * p + q * q)
    numerator = light[2] - light[0] * p - light[1] * q
    diffuse = numerator / length
    value = ambient + np.maximum(diffuse, .02)
    if not derivatives:
        return value
    active = diffuse > .02
    dp = active * (-light[0] / length - numerator * p / length**3) / value
    dq = active * (-light[1] / length - numerator * q / length**3) / value
    return value, dp, dq


def masked_mean(values, mask, sigma):
    return ndimage.gaussian_filter(values * mask, sigma) / np.maximum(
        ndimage.gaussian_filter(mask.astype(float), sigma), 1e-8)


def appearance(image, mask, base, light):
    """Separate chromatic material changes and broad exposure from local shading.

    Achromatic painted relief remains ambiguous. Report it rather than claiming
    an intensity contour is a measured production contour.
    """
    rgb = np.asarray(image, float)[..., :3] / 255
    rgb = np.where(rgb <= .04045, rgb / 12.92, ((rgb + .055) / 1.055)**2.4)
    rgb = np.maximum(rgb, .003)
    observed = np.log(rgb @ [.2126, .7152, .0722])
    chroma = np.log(rgb) - np.log(rgb.mean(2, keepdims=True))
    design = np.concatenate([np.ones((*mask.shape, 1)), chroma], axis=2)
    base_shading = np.log(illumination(base, light))
    target = observed - base_shading
    coefficients = np.linalg.lstsq(design[mask], target[mask], rcond=None)[0]
    material = design @ coefficients
    # Robust reweighting prevents isolated dark cast shadows setting the material.
    for _ in range(3):
        residual = (target - material)[mask]
        scale = max(float(np.median(abs(residual))) * 1.4826, .02)
        weight = np.minimum(1., scale / np.maximum(abs(residual), 1e-8))
        coefficients = np.linalg.lstsq(design[mask] * weight[:, None],
                                       target[mask] * weight, rcond=None)[0]
        material = design @ coefficients
    broad = masked_mean(target - material, mask,
                        max(8., min(mask.shape) * .08))
    material += broad
    cx = sum(g * g for g in gradients(chroma[..., 0]))
    cy = sum(g * g for g in gradients(chroma[..., 1]))
    confidence = np.exp(-6 * np.sqrt(cx + cy)) * \
        ndimage.binary_erosion(mask, iterations=2)
    return observed, material, confidence


def reconstruct(image, mask, base, max_depth_px, light=None, iterations=150, diagnostics=None, engine='joint'):
    """Estimate a continuous, silhouette-bounded height correction in pixels.

    A competing material-only prediction and held-out pixels keep fitting error
    separate from evidence of generalization. Depth scale/light gauge remain
    priors when the image does not determine them.
    """
    if light is None and engine == 'joint':
        from . import joint_shading
        return joint_shading.reconstruct(image,mask,base,max_depth_px,
            iterations=iterations,diagnostics=diagnostics)
    mask = np.asarray(mask, bool)
    base = np.asarray(base, float)
    if mask.shape != base.shape or mask.sum() < 25:
        return np.zeros_like(base), {'accepted': False, 'reason': 'insufficient visible pixels'}
    # Solve broad fall-off before brush/pixel noise. Height scales with pixel
    # spacing, so this changes numerical bandwidth rather than physical depth.
    if max(mask.shape) > 384:
        from PIL import Image
        scale = 384 / max(mask.shape)
        shape = tuple(max(8, round(n * scale)) for n in mask.shape)
        ratios = np.asarray(shape) / mask.shape
        height_scale = ratios[1]
        small_mask = ndimage.zoom(mask, ratios, order=0)
        small_base = ndimage.zoom(base, ratios, order=1) * height_scale
        small_image = image.resize(shape[::-1], Image.Resampling.LANCZOS)
        small_diagnostics = {} if diagnostics is not None else None
        result, report = reconstruct(small_image, small_mask, small_base,
                                     max_depth_px * height_scale, light=light, iterations=iterations,
                                     diagnostics=small_diagnostics)
        result = ndimage.zoom(
            result, 1 / ratios, order=1)[:mask.shape[0], :mask.shape[1]] / height_scale
        result *= mask
        if diagnostics is not None:
            for name, value in small_diagnostics.items():
                enlarged = ndimage.zoom(
                    value, 1 / ratios, order=0 if name == 'mask' else 1)
                enlarged = enlarged[:mask.shape[0], :mask.shape[1]]
                diagnostics[name] = enlarged / \
                    height_scale if name.endswith('_px') else enlarged
        report.update(solve_resolution=list(shape), source_resolution=list(mask.shape),
                      source_depth_bound_px=float(max_depth_px))
        return result, report
    light_inferred = light is None
    light = np.array([-.45, -.55, .8] if light is None else light, float)
    light /= max(np.linalg.norm(light), 1e-9)
    observed, material, confidence = appearance(image, mask, base, light)
    rows, cols = np.indices(mask.shape)
    held_out = (rows + 3 * cols) % 7 == 0
    training = confidence * ~held_out
    active = confidence > .01
    count = max(float(training.sum()), 1.)
    target = observed - material
    indices = np.flatnonzero(active)
    curvature_weight = 1.
    tether_weight = .0001

    def objective(values):
        delta = np.zeros(mask.shape)
        delta.flat[indices] = values
        shade, dp, dq = illumination(base + delta, light, derivatives=True)
        residual = np.log(shade) - target
        robust = np.sqrt(residual * residual + .02**2)
        data_gradient = training * residual / robust / count
        laplacian = adjoint(*gradients(delta))
        loss = float(np.sum(training * robust) / count + curvature_weight * np.mean(laplacian**2)
                     + tether_weight * np.mean(delta**2))
        gradient = adjoint(data_gradient * dp, data_gradient * dq)
        gradient += 2 * curvature_weight * \
            adjoint(*gradients(laplacian)) / delta.size
        gradient += 2 * tether_weight * delta / delta.size
        return loss, gradient.flat[indices].copy()

    if not len(indices):
        return np.zeros_like(base), {'accepted': False, 'reason': 'no reliable shading pixels'}
    solution = optimize.minimize(objective, np.full(len(indices), -.01), jac=True,
                                 bounds=[(-float(max_depth_px), 0.)] * len(indices), method='L-BFGS-B',
                                 options={'maxiter': iterations, 'ftol': 1e-10, 'gtol': 1e-7, 'maxcor': 8})
    delta = np.zeros(mask.shape)
    delta.flat[indices] = solution.x
    valid = held_out & (confidence > .1)
    before = np.log(illumination(base, light)) - target
    after = np.log(illumination(base + delta, light)) - target
    baseline = float(np.mean(before[valid]**2)) if valid.any() else 0.
    error = float(np.mean(after[valid]**2)) if valid.any() else 0.
    improvement = 1 - error / max(baseline, 1e-12)
    accepted = baseline > .0001 and improvement > .05
    if diagnostics is not None:
        diagnostics.update(mask=mask, coarse_height_px=base,
                           hypothesis_height_px=delta, accepted_height_px=delta if accepted else np.zeros_like(
                               delta),
                           log_material=material, observed_log_luminance=observed,
                           predicted_log_shading=np.log(illumination(base + delta, light)))
    report = {'method': 'continuous height/gradient inverse shading; no primitive templates',
              'accepted': bool(accepted), 'held_out_gain': float(improvement),
              'material_only_error': baseline, 'surface_error': error,
              'light': light.tolist(), 'light_source': 'gauge prior' if light_inferred else 'provided',
              'depth_bound_px': float(max_depth_px), 'iterations': int(solution.nit),
              'converged': bool(solution.success),
              'smoothness_weight': curvature_weight,
              'integrability': 'exact discrete height gradient',
              'uncertainty': 'unknown achromatic albedo and illumination can imitate relief'}
    return (delta if accepted else np.zeros_like(delta)), report
