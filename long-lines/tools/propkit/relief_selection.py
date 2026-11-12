"""Region-aware relief selection with continuous composition and untouched tests.

Selection/acceptance assess an appearance model, not physical depth truth.
"""
import numpy as np
from scipy.sparse.linalg import LinearOperator, cg


def gain(before, after, mask):
    if np.count_nonzero(mask) < 6:
        return None
    baseline = float(np.mean(before[mask]))
    return float(1 - np.mean(after[mask]) / max(baseline, 1e-12)) if baseline > 1e-5 else None


def extend_supported(height, selected, mask):
    """Keep supported samples fixed; extend smoothly to the coarse surface.

    Unknown pixels receive a screened harmonic continuation, not inferred detail.
    A failed linear solve must not be mistaken for accepted geometry.
    """
    from .shading import gradients, adjoint
    known = np.where(selected, height, 0.)
    unknown = mask & ~selected
    if not np.any(selected) or not np.any(unknown):
        return known, True
    shape = height.shape
    radius = max(4., min(32., min(shape) * .15))
    screening = 1. / radius**2

    def laplace(value):
        return adjoint(*gradients(value))

    def product(vector):
        value = vector.reshape(shape)
        return (unknown * (laplace(unknown * value) + screening * value)
                + (~unknown) * value).ravel()
    degree = np.full(shape, 4.)
    degree[[0, -1], :] -= 1
    degree[:, [0, -1]] -= 1
    diagonal = np.where(unknown, degree + screening, 1.)
    operator = LinearOperator(
        (height.size, height.size), matvec=product, dtype=float)
    preconditioner = LinearOperator(
        operator.shape, matvec=lambda x: x / diagonal.ravel(), dtype=float)
    solution, info = cg(operator, (-unknown.astype(float) * laplace(known)).ravel(), M=preconditioner,
                        rtol=1e-7, atol=0., maxiter=400)
    if info != 0 or not np.all(np.isfinite(solution)):
        return np.zeros(shape), False
    extended = known + unknown * solution.reshape(shape)
    return extended, True


def select(base, height, material, lighting, flat_material, flat_light, observed, labels, mask,
           selection, acceptance, testing, threshold=.05):
    from .joint_shading import shade
    flat_prediction = flat_material + np.log(shade(base, flat_light))
    proposal_prediction = material + np.log(shade(base + height, lighting))
    before = (flat_prediction - observed)**2
    proposed = (proposal_prediction - observed)**2
    overall_selection = gain(before, proposed, selection & mask)
    overall_acceptance = gain(before, proposed, acceptance & mask)
    records = []
    supported = []
    for identifier in np.unique(labels[labels > 0]):
        region = (labels == identifier) & mask
        first = gain(before, proposed, selection & region)
        second = gain(before, proposed, acceptance & region)
        keep = first is not None and second is not None and first > threshold and second > threshold
        records.append({'region_id': int(identifier), 'pixels': int(region.sum()),
                        'selection_gain': first, 'acceptance_gain': second, 'initially_supported': bool(keep)})
        if keep:
            supported.append(int(identifier))
    whole = overall_selection is not None and overall_acceptance is not None and overall_selection > threshold and overall_acceptance > threshold
    passes = 0
    if whole:
        applied = height.copy()
        applied_material = material.copy()
        applied_prediction = proposal_prediction
        applied_ids = list(map(int, np.unique(labels[labels > 0])))
        mode = 'whole_view'
    else:
        # Convert the baseline material into the proposal lighting frame so
        # regions outside the proposal reproduce the baseline prediction.
        adapted_flat = flat_prediction - np.log(shade(base, lighting))
        active = supported.copy()

        def compose(ids):
            selected = np.isin(labels, ids) & mask
            combined_height, converged = extend_supported(
                height, selected, mask)
            if not converged:
                raise RuntimeError(
                    'Relief continuation did not converge; no regional surface was accepted.')
            # Keep the fitted appearance inside supported regions. Outside uses
            # the material-only explanation under the same lighting frame.
            combined_material = np.where(selected, material, adapted_flat)
            prediction = combined_material + \
                np.log(shade(base + combined_height, lighting))
            return combined_height, combined_material, prediction
        for passes in range(1, 5):
            applied, applied_material, applied_prediction = compose(active)
            errors = (applied_prediction - observed)**2
            retained = []
            for identifier in active:
                region = (labels == identifier) & mask
                first = gain(before, errors, selection & region)
                second = gain(before, errors, acceptance & region)
                if first is not None and second is not None and first > threshold and second > threshold:
                    retained.append(identifier)
            if retained == active:
                break
            active = retained
        else:
            active = []
            applied, applied_material, applied_prediction = compose(active)
        applied_ids = active
        mode = 'regional' if active else 'none'
    applied_error = (applied_prediction - observed)**2
    for record in records:
        region = (labels == record['region_id']) & mask
        record['applied'] = record['region_id'] in applied_ids
        record['composed_acceptance_gain'] = gain(
            before, applied_error, acceptance & region)
        # Report-only test evaluation; it cannot alter region selection.
        record['final_test_gain'] = gain(
            before, applied_error, testing & region)
    final_gain = gain(before, applied_error, testing & mask)
    report = {'mode': mode, 'whole_view_selection_gain': overall_selection,
              'whole_view_acceptance_gain': overall_acceptance, 'initially_supported_regions': len(supported),
              'applied_regions': len(applied_ids), 'composition_passes': passes, 'regions': records,
              'composition_method': 'screened harmonic continuation; supported samples fixed',
              'extension_is_validated_detail': False,
              'final_test_gain': final_gain, 'final_test_pass': final_gain is not None and final_gain > threshold,
              'threshold': threshold, 'physical_depth_verified': False,
              'protocol': 'choose on fold 0; verify composition on fold 2; report-only final fold 1'}
    return applied, applied_material, report, {
        'material_only_error_map': before, 'proposal_error_map': proposed, 'applied_error_map': applied_error,
        'applied_region_labels': np.where(np.isin(labels, applied_ids), labels, 0)}
