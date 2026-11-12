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


def extend_supported(height, selected, mask, prior=None):
    """Keep constraints fixed; integrate a smooth correction about a prior.

    With no prior, unknown pixels extend toward zero. With a proposal prior,
    uncertainty preserves existing detail instead of flattening it.
    A failed linear solve must not be mistaken for accepted geometry.
    """
    from .shading import gradients, adjoint
    prior = np.zeros_like(height) if prior is None else np.where(mask, prior, 0.)
    known = np.where(selected, height - prior, 0.)
    unknown = mask & ~selected
    if not np.any(selected) or not np.any(unknown):
        return prior + known, True
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
    extended = prior + known + unknown * solution.reshape(shape)
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
    flat_supported = []
    for identifier in np.unique(labels[labels > 0]):
        region = (labels == identifier) & mask
        first = gain(before, proposed, selection & region)
        second = gain(before, proposed, acceptance & region)
        keep = first is not None and second is not None and first > threshold and second > threshold
        records.append({'region_id': int(identifier), 'pixels': int(region.sum()),
                        'selection_gain': first, 'acceptance_gain': second, 'initially_supported': bool(keep)})
        # Lack of a relative improvement is ambiguity, not evidence of zero
        # relief. Only a near-exact material-only explanation on BOTH reserved
        # folds can explicitly replace a nonflat proposal with a flat region.
        reserved = [selection & region, acceptance & region]
        flat = all(np.count_nonzero(m) >= 6 and np.mean(before[m]) < 1e-5
                   and np.mean(proposed[m]) > 1e-5 for m in reserved)
        records[-1]['material_only_supported'] = bool(flat)
        if keep:
            supported.append(int(identifier))
        elif flat:
            flat_supported.append(int(identifier))
    whole = overall_selection is not None and overall_acceptance is not None and overall_selection > threshold and overall_acceptance > threshold
    passes = 0
    flat_global = all(np.count_nonzero(m & mask) >= 6 and
                      np.mean(before[m & mask]) < 1e-5 and np.mean(proposed[m & mask]) > 1e-5
                      for m in (selection, acceptance))
    if flat_global:
        applied = np.zeros_like(height)
        applied_material = flat_prediction - np.log(shade(base, lighting))
        applied_prediction = flat_prediction
        applied_ids = []
        mode = 'none'
        flat_supported = [r['region_id'] for r in records]
        for record in records:
            record['material_only_supported'] = True
    elif whole:
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
            flattened = np.isin(labels, flat_supported) & mask
            target = np.where(flattened, 0., height)
            combined_height, converged = extend_supported(
                target, selected | flattened, mask, prior=height)
            if not converged:
                raise RuntimeError(
                    'Relief continuation did not converge; no regional surface was accepted.')
            # A continuation may not invent a new depth sign or exceed the
            # original bounded proposal's range.
            combined_height = np.clip(combined_height, min(0., float(height.min())),
                                      max(0., float(height.max())))
            # Ambiguous geometry AND its fitted material stay provisional.
            # Replacing either with the flat explanation silently discards the
            # original hypothesis and invalidates its predicted shading.
            combined_material = np.where(flattened, adapted_flat, material)
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
    provisional_ids = [r['region_id'] for r in records
                       if r['region_id'] not in applied_ids and not r['material_only_supported']]
    provisional = np.isin(labels, provisional_ids) & mask & (abs(applied) > 1e-8)
    if provisional.any():
        mode = 'regional_with_provisional' if applied_ids else 'provisional'
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
              'composition_method': 'screened correction about the proposal; supported samples fixed',
              'provisional_regions': len(provisional_ids) if provisional.any() else 0,
              'provisional_pixels': int(provisional.sum()),
              'unsupported_region_policy': 'retain provisional proposal, not zero relief',
              'material_only_regions': len(flat_supported),
              'needs_review': bool(provisional.any()),
              'extension_is_validated_detail': False,
              'final_test_gain': final_gain, 'final_test_pass': final_gain is not None and final_gain > threshold,
              'threshold': threshold, 'physical_depth_verified': False,
              'protocol': 'choose on fold 0; verify composition on fold 2; report-only final fold 1'}
    return applied, applied_material, report, {
        'material_only_error_map': before, 'proposal_error_map': proposed, 'applied_error_map': applied_error,
        'applied_region_labels': np.where(np.isin(labels, applied_ids), labels, 0),
        'provisional_region_labels': np.where(provisional, labels, 0)}
