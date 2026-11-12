"""Deterministic review of the evidence used by the factory presentation.

This reads stage data, not rendered pixels. It does not certify geometry,
change thresholds, edit code or silently accept a rejected proposal.
"""
from pathlib import Path
import json
import numpy as np


def inspect(result, measured, diagnostics=None):
    findings = []

    def flag(code, station, severity, summary, evidence, next_check):
        findings.append(dict(code=code, station=station, severity=severity, summary=summary,
                             evidence=evidence, next_check=next_check))
    relief = measured.get('relief', {})
    for view, report in relief.get('views', {}).items():
        policy = report.get('boundary_policy')
        used = report.get('boundary_pixels_used')
        total = report.get('boundary_pixels')
        if policy == 'achromatic' and used is not None and total is not None and used < total:
            flag('boundary_evidence_excluded', 6, 'review', view + ': colour-linked boundaries receive no edge-preservation weight',
                 {'used': used, 'traced': total}, 'Compare all-boundary weighting without changing edge thresholds.')
        selection = report.get('relief_selection', {})
        if selection.get('provisional_pixels', 0):
            flag('provisional_relief_retained', 9, 'review', view + ': uncertain relief is retained as a proposal',
                 {'pixels': selection['provisional_pixels'], 'regions': selection.get('provisional_regions')},
                 'Resolve with independent views or calibration; do not treat uncertainty as zero geometry.')
        dropped = [r['region_id'] for r in selection.get('regions', []) if r.get(
            'initially_supported') and not r.get('applied')]
        if dropped:
            flag('composition_rejected_patches', 9, 'review', view + ': locally supported proposals did not survive composition',
                 {'region_ids': dropped}, 'Inspect the composed normals, boundary blend and regional residuals.')
        if selection.get('final_test_pass') is False or (not selection and report.get('needs_review')):
            flag('unseen_pixel_check_failed', 9, 'review', view + ': final unseen-pixel check needs review',
                 {'gain': report.get('held_out_gain'),
                  'selection_mode': selection.get('mode')},
                 'Inspect residual location and lighting/material assumptions; do not tune on final test pixels.')
        if diagnostics is not None:
            path = Path(diagnostics) / (view + '.npz')
            if path.is_file():
                with np.load(path, allow_pickle=False) as arrays:
                    if {'mask', 'hypothesis_height_px', 'accepted_height_px'} <= set(arrays.files):
                        mask = arrays['mask']
                        proposal = arrays['hypothesis_height_px'][mask]
                        applied = arrays['accepted_height_px'][mask]
                        if proposal.size and np.ptp(proposal) > .15 and not np.any(abs(applied) > 1e-8):
                            flag('proposal_entirely_withheld', 9, 'review', view + ': non-flat proposal became zero relief correction',
                                 {'proposal_range_px': float(
                                     np.ptp(proposal))},
                                 'Render the unvalidated proposal as clay and inspect regional error maps.')
    pre = {r['id']: r for r in relief.get(
        'pre_reduction_validation', {}).get('probes', [])}
    post = result.get('metrics', {}).get(
        'surface_features', {}).get('probes', [])
    lost = [r['id'] for r in post if pre.get(r['id'], {}).get(
        'retained') and not r.get('retained')]
    if lost:
        flag('features_lost_after_dense_stage', 11, 'error', 'Features retained on the dense surface fail after reduction/export',
             {'lost_count': len(lost), 'probe_ids': lost}, 'Track these same cross-sections after reduction, baking and export separately.')
    cross = relief.get('cross_view_relief', {})
    if cross.get('needs_review'):
        flag('cross_view_support_incomplete', 10, 'review', 'Independent view support remains incomplete',
             {'supported': cross.get('supported_regions', 0), 'regions': len(
                 cross.get('regions', []))},
             'Inspect visibility and region correspondence before claiming shared physical detail.')
    construction = relief.get('construction_volumes', {})
    if construction.get('composition_applied') is False:
        flag('construction_field_fallback', 10, 'review', 'Boolean recomposition was not adopted',
             {'root_shift_cells': construction.get(
                 'maximum_root_shift_cells'), 'limit': construction.get('allowed_root_shift_cells')},
             'Preserve the fitted surface while fixing sampled construction-field distances.')
    for name, part in measured.get('surface_details', {}).items():
        part_result = {'metrics': {'surface_features': result.get(
            'metrics', {}).get('part_surface_features', {}).get(name, {})}}
        child = inspect(part_result, {'relief': part},
                        part.get('diagnostic_folder'))
        for finding in child['findings']:
            findings.append(
                dict(finding, part=name, summary=name + ': ' + finding['summary']))
    failures = result.get('fails', [])
    if failures:
        flag('final_quality_failed', 14, 'error', 'The exported asset failed its existing quality gate',
             {'failure_count': len(failures), 'normal_failures': [
                 s for s in failures if 'normal' in s.lower()]},
             'Retain review status; inspect the recorded failures rather than the textured appearance alone.')
    return {'status': 'needs_review' if findings else 'no_flagged_issue',
            'method': 'deterministic stage-evidence audit', 'uses_llm': False, 'inspects_render_pixels': False,
            'physical_geometry_verified': False, 'findings': findings,
            'limits': 'Checks structured stage evidence behind the slideshow; not human-like visual judgement or ground truth.'}


def write(report, destination):
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2))
    return str(path)
