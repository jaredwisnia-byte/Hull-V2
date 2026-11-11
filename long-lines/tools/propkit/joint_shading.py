"""Coupled shape, diffuse illumination and reflectance estimation.

Height is represented by continuous B-spline controls, not geometric templates.
Lighting and reflectance are nuisance variables with explicit gauges. Unknown
single-image lighting/material cannot silently become calibrated metric depth.
"""
import numpy as np
from scipy import ndimage, optimize
from scipy.sparse.linalg import LinearOperator, cg
from .shading import gradients, adjoint
from .spline_surface import Basis, control_shape


def linear_image(image):
    rgb = np.asarray(image, float)[..., :3] / 255
    return np.maximum(np.where(rgb <= .04045, rgb / 12.92, ((rgb + .055) / 1.055)**2.4), .003)


def normals(height):
    p, q = gradients(height)
    length = np.sqrt(1 + p * p + q * q)
    return np.stack([-p / length, -q / length, 1 / length], axis=2)


def shade(height, lighting, derivatives=False):
    p, q = gradients(height)
    length = np.sqrt(1 + p * p + q * q)
    numerator = lighting[2] - lighting[0] * p - lighting[1] * q
    raw = lighting[3] + numerator / length
    value = np.maximum(raw, .01)
    if not derivatives:
        return value
    active = raw > .01
    dp = active * (-lighting[0] / length - numerator * p / length**3) / value
    dq = active * (-lighting[1] / length - numerator * q / length**3) / value
    return value, dp, dq


def fit_light(observed, material, height, training, prior):
    n = normals(height)
    matrix = np.concatenate(
        [n, np.ones((*height.shape, 1))], axis=2)[training > 0]
    target = np.exp(np.clip((observed - material)[training > 0], -8, 3))
    weight = np.sqrt(training[training > 0])
    if len(target) > 16000:
        selected = np.linspace(0, len(target) - 1, 16000).astype(int)
        matrix, target, weight = matrix[selected], target[selected], weight[selected]
    singular = np.linalg.svd(matrix * weight[:, None], compute_uv=False)
    rank = int(np.sum(singular > max(singular[0] * .005, 1e-8)))
    # A flat starting surface cannot calibrate a light direction. Preserve the
    # declared direction gauge and fit only exposure rather than invent rank.
    if rank < 4:
        prediction = np.maximum(matrix @ prior, .01)
        scale = float(np.median(target / prediction))
        return np.asarray(prior) * np.clip(scale, .5, 2), {'rank': rank, 'direction_identifiable': False}
    strength = .002 * float(np.linalg.norm(matrix, ord='fro'))
    result = np.asarray(prior).copy()
    for _ in range(4):
        residual = matrix @ result - target
        noise = max(float(np.median(abs(residual))) * 1.4826, .01)
        robust = np.sqrt(np.minimum(
            1., noise / np.maximum(abs(residual), 1e-8)))
        w = weight * robust
        augmented = np.r_[matrix * w[:, None], np.eye(4) * strength]
        rhs = np.r_[target * w, prior * strength]
        result = optimize.lsq_linear(augmented, rhs, bounds=(
            [-4, -4, .01, .005], [4, 4, 4, 4]), tol=1e-8).x
    return result, {'rank': rank, 'direction_identifiable': True,
                    'condition': float(singular[0] / max(singular[-1], 1e-12))}


def material_prior(rgb, observed, base_shading, training):
    chroma = np.log(rgb) - np.log(rgb.mean(2, keepdims=True))
    design = np.concatenate([np.ones((*observed.shape, 1)), chroma], axis=2)
    keep = training > 0
    coefficients = optimize.lsq_linear(design[keep], (observed - base_shading)[keep],
                                       bounds=([-8, -1, -1, -1], [3, 1, 1, 1])).x
    return design @ coefficients, chroma


def fit_material(target, initial, prior, chroma, training, mask):
    """Edge-aware, robust reflectance solve; held-out intensities are excluded."""
    valid_x = mask.copy()
    valid_x[:, -1] = False
    valid_x[:, :-1] &= mask[:, 1:]
    valid_y = mask.copy()
    valid_y[-1] = False
    valid_y[:-1] &= mask[1:]
    chroma_x = sum(
        g * g for g in [gradients(chroma[..., i])[0] for i in range(3)])
    chroma_y = sum(
        g * g for g in [gradients(chroma[..., i])[1] for i in range(3)])
    edge_x = np.exp(-chroma_x / .08) * valid_x
    edge_y = np.exp(-chroma_y / .08) * valid_y
    current = initial.copy()
    infos = []
    for _ in range(2):
        px, py = gradients(current)
        wx = edge_x / np.sqrt(px * px + .04**2)
        wy = edge_y / np.sqrt(py * py + .04**2)
        residual = current - target
        robust = np.minimum(1., .08 / np.maximum(abs(residual), 1e-8))
        data = training * robust
        prior_weight = .08
        regularity = .12

        def multiply(values):
            values = values.reshape(mask.shape)
            gx, gy = gradients(values)
            return ((data + prior_weight) * values + regularity * adjoint(wx * gx, wy * gy)).ravel()
        matrix = LinearOperator((mask.size, mask.size),
                                matvec=multiply, dtype=float)
        diagonal = data + prior_weight + regularity * (wx + wy)
        diagonal[:, 1:] += regularity * wx[:, :-1]
        diagonal[1:] += regularity * wy[:-1]
        preconditioner = LinearOperator(
            matrix.shape, matvec=lambda v: v / diagonal.ravel(), dtype=float)
        rhs = data * target + prior_weight * prior
        solution, info = cg(matrix, rhs.ravel(), x0=current.ravel(
        ), M=preconditioner, rtol=1e-5, atol=0, maxiter=100)
        current = np.clip(solution.reshape(mask.shape), -8, 3)
        infos.append(int(info))
    return current, infos


def depth_information(height, base, lighting, observed, material, testing, chroma,
                      fixed_light=False, fixed_material=False):
    """Profile linearized depth scale against competing appearance variables.

    The interval is conditional on the fitted surface and material regularity.
    Arbitrary unknown per-pixel reflectance is intrinsically unidentifiable;
    a narrow prior-conditioned interval must not conceal that fact.
    """
    illumination, dp, dq = shade(base + height, lighting, True)
    gx, gy = gradients(height)
    derivative = (dp * gx + dq * gy)[testing]
    residual = (material + np.log(illumination) - observed)[testing]
    keep = np.arange(len(derivative))
    if len(keep) > 10000:
        keep = np.linspace(0, len(keep) - 1, 10000).astype(int)
    derivative, residual = derivative[keep], residual[keep]
    nuisance = []
    if not fixed_light:
        n = normals(base + height)[testing][keep]
        light_jacobian = np.c_[n, np.ones(
            len(n))] / illumination[testing][keep, None]
        nuisance.extend(light_jacobian.T)
    if not fixed_material:
        yy, xx = np.indices(height.shape)
        u, v = xx / max(1, height.shape[1] -
                        1), yy / max(1, height.shape[0] - 1)
        nuisance.extend(np.c_[np.ones(len(keep)), chroma[testing][keep],
                              u[testing][keep], v[testing][keep], (u * u)[
            testing][keep],
            (u * v)[testing][keep], (v * v)[testing][keep]].T)
    raw_information = float(derivative @ derivative)
    if nuisance and len(derivative):
        matrix = np.asarray(nuisance).T
        derivative = derivative - \
            matrix @ np.linalg.lstsq(matrix, derivative, rcond=1e-6)[0]
    information = float(derivative @ derivative)
    appearance_retained = information / max(raw_information, 1e-12)
    noise = max(float(np.median(abs(residual))) *
                1.4826, .005) if len(residual) else 1.
    # Correlated neighbouring pixels are not independent depth measurements.
    effective = max(1., len(derivative) / 36)
    information *= effective / max(1, len(derivative))
    standard_error = noise / np.sqrt(max(information, 1e-12))
    interval = [float(max(0., 1 - 1.96 * standard_error)),
                float(1 + 1.96 * standard_error)]
    informative = raw_information > 1e-8 and standard_error < .5
    return {'scale_interval_95_conditional': interval, 'scale_standard_error_conditional': float(standard_error),
            'informative_under_model': bool(informative), 'data_only_identifiable': bool(fixed_light and fixed_material and informative),
            'appearance_information_retained': float(appearance_retained),
            'noise_log_luminance': noise, 'effective_samples': effective,
            'assumptions': 'fitted height shape; declared lighting/material model; supplied physical scale'}


def fit_height(base, initial, basis, material, observed, training, lighting, mask, bound, iterations):
    feather = np.clip(ndimage.distance_transform_edt(mask) / 2, 0, 1)
    coefficients, _ = basis.project(initial, mask)
    coefficients = np.clip(coefficients, -bound, 0)
    count = max(float(training.sum()), 1.)

    def objective(values):
        height = basis.evaluate(values) * feather
        illumination, dp, dq = shade(base + height, lighting, True)
        residual = material + np.log(illumination) - observed
        robust = np.sqrt(residual * residual + .03**2)
        g = training * residual / robust / count
        laplace = adjoint(*gradients(height))
        loss = float(np.sum(training * robust) / count + .35 *
                     np.mean(laplace**2) + .0001 * np.mean(height**2))
        gradient = adjoint(g * dp, g * dq) + .7 * adjoint(*gradients(laplace)
                                                          ) / height.size + .0002 * height / height.size
        return loss, basis.adjoint(gradient * feather).ravel()
    fit = optimize.minimize(objective, coefficients.ravel(), jac=True, method='L-BFGS-B',
                            bounds=[(-bound, 0)] * coefficients.size,
                            options={'maxiter': iterations, 'ftol': 1e-7, 'gtol': 1e-7, 'maxcor': 12})
    height = basis.evaluate(fit.x) * feather
    return height, {'iterations': int(fit.nit), 'converged': bool(fit.success),
                    'objective': float(fit.fun), 'controls': list(basis.controls)}, fit.x.reshape(basis.controls)


def reconstruct(image, mask, base, max_depth_px, light=None, albedo=None, iterations=160, diagnostics=None):
    """Alternate shape/light/material fits through actual resolution refinement."""
    from PIL import Image
    mask = np.asarray(mask, bool)
    base = np.asarray(base, float)
    if base.shape != mask.shape or mask.sum() < 25:
        return np.zeros_like(base), {'accepted': False, 'reason': 'insufficient visible pixels'}
    fixed_light = light is not None
    fixed_material = albedo is not None
    direction = np.array([-.45, -.55, .8] if light is None else light, float)
    direction /= np.linalg.norm(direction)
    lighting = np.r_[direction, .25]
    history = []
    previous = None
    previous_material = None
    final_coefficients = None
    initial_identifiability = None
    maximum = min(max(mask.shape), 768)
    finest_shape = tuple(max(8, round(n * maximum / max(mask.shape)))
                         for n in mask.shape)
    reference_rgb = linear_image(image.resize(
        finest_shape[::-1], Image.Resampling.LANCZOS))
    reference_mask = ndimage.zoom(
        mask, np.asarray(finest_shape) / mask.shape, order=0)
    rows, cols = np.indices(finest_shape)
    reference_fold = (rows + 3 * cols) % 9
    reference_training = reference_mask & (reference_fold >= 2)
    reference_validation = reference_mask & (reference_fold == 0)
    reference_testing = reference_mask & (reference_fold == 1)
    # Remove withheld intensities before making any lower-resolution image.
    # Otherwise the coarse initialization leaks test pixels into fitted shape.
    nearest = ndimage.distance_transform_edt(
        ~reference_training, return_distances=False, return_indices=True)
    fitting_rgb = reference_rgb[nearest[0], nearest[1]]
    reference_observed = np.log(reference_rgb @ [.2126, .7152, .0722])
    reference_base = ndimage.zoom(base, np.asarray(
        finest_shape) / mask.shape, order=1) * finest_shape[1] / mask.shape[1]
    resolutions = sorted(set(min(n, maximum) for n in (128, 256, maximum)))
    for resolution in resolutions:
        scale = resolution / max(mask.shape)
        shape = tuple(max(8, round(n * scale)) for n in mask.shape)
        ratio = np.asarray(shape) / mask.shape
        pixel_scale = ratio[1]
        current_mask = ndimage.zoom(mask, ratio, order=0)
        current_base = ndimage.zoom(base, ratio, order=1) * pixel_scale
        rgb = ndimage.zoom(
            fitting_rgb, (* (np.asarray(shape) / finest_shape), 1), order=1)
        observed = np.log(rgb @ [.2126, .7152, .0722])
        training = current_mask if resolution < maximum else reference_training
        testing = reference_testing
        prior, chroma = material_prior(rgb, observed, np.log(
            shade(current_base, lighting)), training)
        if fixed_material:
            material = np.broadcast_to(np.asarray(albedo, float), mask.shape)
            material = np.log(np.maximum(
                ndimage.zoom(material, ratio, order=1), .003))
            prior = material.copy()
        else:
            material = prior.copy() if previous_material is None else ndimage.zoom(
                previous_material, np.asarray(shape) / previous_material.shape, order=1)[:shape[0], :shape[1]]
        if previous is None:
            height = np.zeros(shape)
        else:
            height = ndimage.zoom(previous, np.asarray(
                shape) / previous.shape, order=1)[:shape[0], :shape[1]]
            height *= pixel_scale / previous_scale
        if not fixed_light:
            lighting, calibration = fit_light(
                observed, prior, current_base, training, lighting)
            if initial_identifiability is None:
                initial_identifiability = calibration
        # A fair competing explanation uses the same material/light model on
        # the unchanged coarse surface, without access to withheld intensities.
        flat_material = prior.copy()
        flat_light = lighting.copy()
        for _ in range(3):
            if not fixed_light:
                flat_light, _ = fit_light(
                    observed, flat_material, current_base, training, flat_light)
            if not fixed_material:
                flat_material, _ = fit_material(observed - np.log(shade(current_base, flat_light)),
                                                flat_material, prior, chroma, training, current_mask)
        best = None
        for outer in range(6):
            basis = Basis(shape, control_shape(
                shape, 12 if outer < 2 else 6, maximum=128))
            height, fit, coefficients = fit_height(current_base, height, basis, material, observed,
                                                   training, lighting, current_mask, max_depth_px * pixel_scale, iterations)
            if not fixed_light:
                lighting, calibration = fit_light(
                    observed, material, current_base + height, training, lighting)
            if not fixed_material:
                material, material_info = fit_material(observed - np.log(shade(current_base + height, lighting)),
                                                       material, prior, chroma, training, current_mask)
            else:
                material_info = []
            refined_height = ndimage.zoom(height, np.asarray(
                finest_shape) / shape, order=1) * finest_shape[1] / shape[1]
            refined_material = ndimage.zoom(
                material, np.asarray(finest_shape) / shape, order=1)
            prediction = refined_material + \
                np.log(shade(reference_base + refined_height, lighting))
            error = float(np.mean(
                (prediction[reference_validation] - reference_observed[reference_validation])**2))
            history.append(dict(resolution=list(shape), outer=outer, validation_error=error,
                                material_cg=material_info, lighting=lighting.tolist(), **fit))
            if best is None or error < best['error']:
                best = dict(error=error, height=height.copy(), material=material.copy(), lighting=lighting.copy(),
                            coefficients=coefficients.copy(), basis=basis, fit=fit)
            if outer >= 2 and fit['converged'] and abs(error - history[-2]['validation_error']) < 1e-7:
                break
        height, material, lighting = best['height'], best['material'], best['lighting']
        previous, previous_material, previous_scale = height, material, pixel_scale
        final_coefficients = best['coefficients']
    before = flat_material + \
        np.log(shade(current_base, flat_light)) - reference_observed
    after = material + \
        np.log(shade(current_base + height, lighting)) - reference_observed
    baseline = float(np.mean(before[testing]**2))
    error = float(np.mean(after[testing]**2))
    improvement = 1 - error / max(baseline, 1e-12)
    accepted = baseline > 1e-5 and improvement > .05
    depth = depth_information(height, current_base, lighting, reference_observed, material, testing, chroma,
                              fixed_light=fixed_light, fixed_material=fixed_material)
    result = ndimage.zoom(
        height, 1 / ratio, order=1)[:mask.shape[0], :mask.shape[1]] / pixel_scale
    result *= mask
    report = {'method': 'alternating continuous spline shape / diffuse light / edge-aware reflectance',
              'accepted': bool(accepted), 'held_out_gain': float(improvement), 'material_only_error': baseline,
              'surface_error': error, 'light': lighting[:3].tolist(), 'ambient': float(lighting[3]),
              'light_source': 'provided' if fixed_light else 'jointly_fitted_with_explicit_gauge',
              'lighting_calibration': initial_identifiability, 'converged': bool(best['fit']['converged']),
              'iterations': int(sum(item['iterations'] for item in history)), 'history': history,
              'solve_resolution': list(shape), 'source_resolution': list(mask.shape), 'depth_bound_px': float(max_depth_px),
              'validation_protocol': 'withheld finest-grid intensities removed before all pyramid, lighting and material fits',
              'integrability': 'continuous spline height gradient',
              'absolute_depth_status': 'conditional_on_calibration' if fixed_light and fixed_material else 'not_identified',
              'depth_information': depth,
              'uncertainty': 'single-image lighting/albedo (reflectance) ambiguity; physical scale must be independently established'}
    if diagnostics is not None:
        diagnostics.update(mask=mask, coarse_height_px=base, hypothesis_height_px=result,
                           accepted_height_px=result if accepted else np.zeros_like(
                               result),
                           log_material=ndimage.zoom(
                               material, 1 / ratio, order=1)[:mask.shape[0], :mask.shape[1]],
                           observed_log_luminance=np.log(
                               linear_image(image) @ [.2126, .7152, .0722]),
                           predicted_log_shading=ndimage.zoom(np.log(shade(
                               current_base + height, lighting)), 1 / ratio, order=1)[:mask.shape[0], :mask.shape[1]],
                           spline_controls_px=final_coefficients / pixel_scale, knots_u=best['basis'].u_knots, knots_v=best['basis'].v_knots)
    return (result if accepted else np.zeros_like(result)), report
