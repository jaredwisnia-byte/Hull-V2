"""Deterministic review of the evidence used by the factory presentation.

This reads stage data, not rendered pixels. It does not certify geometry,
change thresholds, edit code or silently accept a rejected proposal.
"""
from pathlib import Path
import json
import numpy as np


def inspect(result, measured, diagnostics=None):
    findings = []
    diagnostic_gauges = []

    def flag(code, station, severity, summary, evidence, next_check):
        findings.append(dict(code=code, station=station, severity=severity, summary=summary,
                             evidence=evidence, next_check=next_check))
    drawing = measured.get('source_drawing', {})
    changed_frames = drawing.get('reconciled_views_without_source_pixel_map', [])
    if changed_frames:
        flag('reconciled_view_lacks_source_pixel_map', 5, 'review',
             'Reconciliation altered build-input views without a source-pixel map',
             {'views': changed_frames, 'drawing': drawing.get('sheet')},
             'Map every build-input contour to the original source pixels before treating its inferred geometry as source-trace constrained.')
    conflicts = drawing.get('view_conflicts_in_use', [])
    if conflicts:
        flag('preflight_view_conflict_used_for_geometry', 5, 'review',
             'Preflight questions source views that the builder still uses for geometry',
             {'views': conflicts, 'drawing': drawing.get('sheet')},
             'Resolve source orientation or proportion, then rebuild and compare traced outlines before using these views as construction constraints.')
    openings = drawing.get('opening_candidates', [])
    if openings:
        flag('opening_mask_physical_meaning_unverified', 5, 'review',
             'Opposing source masks agree, but the accepted cuts may also be painted gaps',
             {'drawing': drawing.get('sheet'), 'candidates': openings},
             'Inspect each source region and clay cut from multiple views before treating it as a verified through-opening.')
    repeated_sources = {
        name: item['reused_source_regions']
        for name, item in drawing.get('part_drawings', {}).items()
        if item.get('reused_source_regions')}
    if repeated_sources:
        flag('companion_view_evidence_reused', 5, 'review',
             'One source drawing supplies multiple assigned directions for a companion part',
             {'parts': repeated_sources, 'drawing': drawing.get('sheet')},
             'Confirm orientation or obtain an independent view before treating those directions as separate 3D evidence.')
    section_audit = result.get('metrics', {}).get('drawing_section_audit', {})
    divergent = {
        view: {'outside_tolerance_count': data['outside_tolerance_count'],
               'severe_outlier_count': data.get('severe_outlier_count', 0),
               'sample_count': data['sample_count'],
               'max_error_in_height_units': data['max_error_in_height_units']}
        for view, data in section_audit.get('views', {}).items()
        if data.get('outside_tolerance_count', 0) >= 3 or
           data.get('severe_outlier_count', 0) >= 1}
    if divergent:
        flag('export_diverges_from_traced_sections', 15, 'review',
             'Exported width profiles differ persistently from source contour measurements',
             {'views': divergent, 'drawing': section_audit.get('drawing_path')},
             'Inspect the listed source trace IDs and exported silhouette rows; resolve view calibration or geometry before release.')
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
                        bound = report.get('depth_bound_px')
                        if bound and 'spline_controls_px' in arrays.files:
                            controls = arrays['spline_controls_px']
                            saturation = float(np.mean(abs(controls) >= .98 * bound))
                            diagnostic_gauges.append({'view': view, 'gauge': 'depth_bound_saturation',
                                                      'control_fraction': saturation, 'depth_bound_px': bound})
                            if saturation > .05:
                                flag('depth_bound_saturated', 9, 'review', view + ': the depth safety bound is actively clipping spline controls',
                                     {'control_fraction': saturation, 'depth_bound_px': bound},
                                     'Test bounded continuation on selection/acceptance folds with geometry safeguards; never tune on final test pixels.')
                        if {'coarse_height_px', 'final_shared_height_px'} <= set(arrays.files):
                            shared = (arrays['final_shared_height_px'] - arrays['coarse_height_px'])[mask]
                            energy = float(applied @ applied)
                            if energy > 1e-8:
                                transfer = float(applied @ shared / energy)
                                diagnostic_gauges.append({'view': view, 'gauge': 'proposal_to_shared_field',
                                                          'least_squares_gain': transfer,
                                                          'interpretation': 'representation transfer, not physical depth truth'})
                                if transfer < .8:
                                    flag('relief_attenuated_in_shared_field', 10, 'review', view + ': applied relief loses strength before mesh reduction',
                                         {'least_squares_gain': transfer},
                                         'Inspect component repair and view fusion separately; do not compensate by painting darker textures.')
    pre = {r['id']: r for r in relief.get(
        'pre_reduction_validation', {}).get('probes', [])}
    if relief.get('unmet_before_reduction'):
        audit = relief.get('probe_diagnostics', {})
        flag('features_missing_on_dense_surface', 10, 'error',
             'Source-derived detail is already missing before mesh reduction',
             {'probe_ids': relief['unmet_before_reduction'],
              'supported_unmet': audit.get('supported_unmet'),
              'unsupported_source': audit.get('unsupported_source'),
              'supported_first_loss_counts': audit.get('supported_first_loss_counts'),
              'diagnostic': audit.get('path')},
             'Inspect each source/proposal/shared-field/mesh cross-section. Retry only supported regions with an isolated quality gate.')
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
    folds = result.get('metrics', {}).get('extreme_folds', {})
    if folds.get('per_1k', 0) > folds.get('limit_per_1k', float('inf')):
        flag('extreme_local_folds', 14, 'error',
             'Exported surface contains many abrupt local folds', folds,
             'Inspect clay and wire views at the recorded fold locations; compare with source views before revising the field or reduction.')
    if failures:
        flag('final_quality_failed', 14, 'error', 'The exported asset failed its existing quality gate',
             {'failure_count': len(failures), 'normal_failures': [
                 s for s in failures if 'normal' in s.lower()]},
             'Retain review status; inspect the recorded failures rather than the textured appearance alone.')
    corrections = list(relief.get('topology', {}).get('correction_reviews', []))
    corrections.extend(result.get('correction_reviews', []))
    for part in measured.get('simplification', {}).get('parts', {}).values():
        corrections.extend(part.get('correction_reviews', []))
    if result.get('correction_review_failure'):
        corrections.append(result['correction_review_failure'])
        flag('unsafe_correction_blocked', 10, 'error', 'A correction exceeded its preservation budget',
             result['correction_review_failure'], 'Resolve the triggering problem locally; do not weaken preservation checks.')
    return {'status': 'needs_review' if findings else 'no_flagged_issue',
            'correction_reviews': corrections,
            'diagnostic_gauges': diagnostic_gauges,
            'method': 'deterministic stage-evidence audit', 'uses_llm': False, 'inspects_render_pixels': False,
            'physical_geometry_verified': False, 'findings': findings,
            'limits': 'Checks structured stage evidence behind the slideshow; not human-like visual judgement or ground truth.'}


def write(report, destination):
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2))
    return str(path)
