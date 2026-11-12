"""Shared screen-space error budgets and pre-paint mesh simplification."""
import numpy as np


def refresh_normals(obj, sharp_angle=35, planar=False):
    """Discard stale split normals after topology changes, then mark sharp edges."""
    from .core import smooth
    if obj.data.has_custom_normals:
        obj.data.normals_split_custom_set([(0, 0, 0)] * len(obj.data.loops))
    smooth(obj, sharp_angle)
    if planar:
        # Interpolation across a long planar triangle must not manufacture
        # curvature from a distant bead. Curved narrow strips stay smooth.
        mesh = obj.data
        normals = np.asarray([tuple(p.normal) for p in mesh.polygons])
        centers = np.asarray([tuple(p.center) for p in mesh.polygons])
        areas = np.asarray([p.area for p in mesh.polygons])
        epsilon = max(max(obj.dimensions) * 1e-5, 1e-7)
        keys = np.c_[np.rint(
            normals * 1000), np.rint(np.einsum('ij,ij->i', normals, centers) / epsilon)]
        _, labels = np.unique(keys, axis=0, return_inverse=True)
        counts = np.bincount(labels)
        sums = np.bincount(labels, weights=areas)
        candidates = np.flatnonzero(
            (counts >= 4) & (sums >= areas.sum() * .005))
        for label in candidates:
            indices = np.flatnonzero(labels == label)
            vertices = np.unique(np.concatenate(
                [np.asarray(mesh.polygons[int(i)].vertices) for i in indices]))
            positions = np.array(
                [tuple(mesh.vertices[int(i)].co) for i in vertices])
            singular = np.linalg.svd(
                positions - positions.mean(0), compute_uv=False)
            if singular[1] < singular[0] * .1:
                continue
            for index in indices:
                mesh.polygons[int(index)].use_smooth = False


def screen_tolerance(standards, kind):
    """The surface error (m) a mesh may have: error_px pixels at the kind's near viewing distance."""
    import math
    sb = standards.get("screen_error_budget")
    if not sb:
        return None
    d = sb["near_m"].get(kind, sb["near_m"]["static"])
    px_per_m = sb["screen_px"][1] / \
        (2 * d * math.tan(math.radians(sb["vertical_fov_deg"]) / 2))
    return sb["error_px"] / px_per_m


def decimate_to_error(obj, tol, min_tris=120, samples=2500, protected=None):
    """Simplify a mesh as far as it can go while its surface stays within tol (metres) of the dense
    mesh (99th percentile, both ways: detail lost and corners cut). Binary search on
    the decimation ratio; returns (triangles, error)."""
    import bpy
    from mathutils.bvhtree import BVHTree
    from .core import apply_mods
    me = obj.data
    dense = np.array([v.co for v in me.vertices])
    if len(dense) > samples:
        dense = dense[np.random.default_rng(0).choice(
            len(dense), samples, replace=False)]
    tris0 = sum(len(p_.vertices) - 2 for p_ in me.polygons)
    if tris0 <= min_tris:
        return tris0, 0.0
    dense_tree = BVHTree.FromPolygons([v.co for v in me.vertices], [
                                      p_.vertices for p_ in me.polygons])
    detail_group = None
    if protected is not None and len(protected['points']):
        from scipy.spatial import cKDTree
        coordinates = np.asarray([tuple(v.co) for v in me.vertices])
        distance, nearest = cKDTree(protected['points']).query(coordinates)
        radius = np.maximum(protected['tolerance_m'][nearest] * 8, 1e-6)
        if 'support_m' in protected:
            radius = np.maximum(radius, np.asarray(
                protected['support_m'])[nearest])
        weight = np.exp(-(distance / radius)**2)
        detail_group = obj.vertex_groups.new(name='__hull_detail_guard')
        quantized = np.rint(weight * 32).astype(int)
        for level in range(1, 33):
            indices = np.flatnonzero(quantized == level).tolist()
            if indices:
                # Zero inverse influence locks edges outright. Keep this a soft
                # preference so source-grid density cannot become permanent.
                detail_group.add(indices, min(level / 32, .95), 'REPLACE')

    adjacency_edges = None
    repair_witnesses = []

    def focus_group(target, identifiers):
        """Concentrate a retry on measured failed features, never object classes."""
        if not identifiers or protected is None or 'ids' not in protected:
            return None
        selected = [i for i, key in enumerate(protected['ids'])
                    if key.rsplit('/', 1)[0] in identifiers]
        if not selected:
            return None
        from scipy.spatial import cKDTree
        points = np.asarray(protected['points'])[selected]
        distance, nearest = cKDTree(points).query(
            np.asarray([tuple(v.co) for v in target.data.vertices]))
        tolerances = np.asarray(protected['tolerance_m'])[selected]
        radius = np.maximum(tolerances[nearest] * 8, 1e-6)
        if 'support_m' in protected:
            radius = np.maximum(radius, np.asarray(
                protected['support_m'])[selected][nearest])
        levels = np.rint(np.exp(-(distance / radius)**2) * 32).astype(int)
        group = target.vertex_groups.new(name='__hull_local_retry')
        for level in range(1, 33):
            indices = np.flatnonzero(levels == level).tolist()
            if indices:
                group.add(indices, min(level / 32, .95), 'REPLACE')
        # Keep the actual dense triangles hit by failed samples. This is a
        # topology constraint on existing geometry, not a newly sculpted dent.
        # A few local triangles may remain dense; the rest of the surface can
        # still collapse according to its quadric error.
        locked = set()
        for point in list(points) + repair_witnesses:
            _, _, face, _ = dense_tree.find_nearest(tuple(point))
            if face is not None:
                locked.update(me.polygons[face].vertices)
        if locked:
            nonlocal adjacency_edges
            if adjacency_edges is None:
                adjacency_edges = np.asarray(
                    [tuple(e.vertices) for e in me.edges])
            # Preserve the local fan too: a new coarse neighbouring triangle
            # must not overhang and occlude an otherwise fixed probe triangle.
            for _ in range(2):
                touches = np.isin(adjacency_edges[:, 0], list(locked)) | np.isin(
                    adjacency_edges[:, 1], list(locked))
                locked.update(adjacency_edges[touches].ravel())
            group.add([int(i) for i in sorted(locked)], 1., 'REPLACE')
        return group

    def modifier_for(target, name, ratio, group=None):
        modifier = target.modifiers.new(name, 'DECIMATE')
        modifier.ratio = ratio
        if group is not None:
            modifier.vertex_group = group.name
            modifier.invert_vertex_group = True
            # Blender adds edge_length * factor to squared plane error. Its
            # factor therefore needs physical length units, like our tolerance.
            modifier.vertex_group_factor = tol * max(
                1., tol / max(float(np.median(protected['tolerance_m'])), 1e-9))
        return modifier

    reviews = []
    fold_limit = None
    if protected is not None and 'source_report' in protected:
        from .bake import STANDARDS
        fold_limit = STANDARDS['minimum_acceptable']['max_extreme_folds_per_1k']

    def trial(ratio, focus=None):
        o2 = obj.copy()
        o2.data = me.copy()
        bpy.context.scene.collection.objects.link(o2)
        group = detail_group if focus is None else focus_group(o2, focus)
        modifier_for(o2, 'd', ratio, group)
        apply_mods(o2)
        t = BVHTree.FromPolygons([v.co for v in o2.data.vertices], [
                                 p_.vertices for p_ in o2.data.polygons])
        simple = np.array([v.co for v in o2.data.vertices])
        if len(simple) > samples:
            simple = simple[np.random.default_rng(1).choice(
                len(simple), samples, replace=False)]
        # both ways: detail the simplified mesh lost, and corners it cut through
        e1 = np.percentile([(t.find_nearest(tuple(c))[3] or 0.0)
                           for c in dense], 99)
        e2 = np.percentile(
            [(dense_tree.find_nearest(tuple(c))[3] or 0.0) for c in simple], 99)
        err = float(max(e1, e2))
        feature_error = 0.
        if protected is not None and protected.get('contrast_report'):
            from .local_features import check_surface_features
            local = check_surface_features(simple if len(simple) == len(o2.data.vertices) else [tuple(v.co) for v in o2.data.vertices],
                                           [tuple(
                                               p.vertices) for p in o2.data.polygons], protected['contrast_report'],
                                           minimum_fraction=.8, maximum_fraction=1.2, tree=t, sampling_tolerance=True)
            feature_error = 2. if local['fails'] else 0.
            if protected.get('source_report'):
                source_check = check_surface_features(
                    [tuple(v.co) for v in o2.data.vertices],
                    [tuple(p.vertices) for p in o2.data.polygons],
                    protected['source_report'], tree=t)
                local['fails'].extend(source_check['fails'])
                if source_check['fails']:
                    feature_error = 2.
        elif protected is not None:
            distances = np.array([t.find_nearest(tuple(c))[3]
                                 for c in protected['points']])
            feature_error = float(
                np.max(distances / np.maximum(protected['tolerance_m'], 1e-9)))
        n = sum(len(p_.vertices) - 2 for p_ in o2.data.polygons)
        folds = None
        if fold_limit is not None:
            from .mesh_health import folded_edges
            folds = folded_edges([tuple(v.co) for v in o2.data.vertices],
                                 [tuple(p.vertices) for p in o2.data.polygons])
        failed = local['fails'] if protected is not None and protected.get(
            'contrast_report') else []
        if focus is not None and failed:
            from mathutils import Vector
            failing = {item.split(': ', 1)[-1] for item in failed}
            reach = float(
                np.ptp(np.asarray([tuple(v.co) for v in me.vertices]), axis=0).max() * 2)
            for probe in protected['contrast_report']['probes']:
                if probe['id'] not in failing:
                    continue
                direction = np.zeros(3)
                direction[probe['axis']] = probe['outward']
                for anchor in probe['anchors_m']:
                    point, _, _, _ = t.ray_cast(
                        Vector(np.asarray(anchor) + direction * reach), Vector(-direction), reach * 2)
                    if point is not None:
                        # A coarse face may occlude an intact groove. Protect
                        # its dense counterpart as well as the intended hit.
                        repair_witnesses.append(tuple(point))
        from .correction_review import assess
        after = {'triangles': n, 'surface_error_m': err,
                 'feature_error': feature_error}
        limits = {'surface_error_m': (0., tol), 'feature_error': (0., 1.)}
        if folds is not None:
            after['extreme_folds_per_1k'] = folds['per_1k']
            limits['extreme_folds_per_1k'] = (0., fold_limit)
        review = assess('excess mesh complexity', 'local-feature-aware quadric reduction',
                        {'triangles': tris0},
                        after, improve=['triangles'], limits=limits)
        review.update(focused_features=None if focus is None else sorted(focus),
                      failed_features=failed[:16], occlusion_witnesses=len(repair_witnesses))
        if protected is not None and protected.get('contrast_report'):
            review['failed_measurements'] = [
                p for p in local['probes'] if not p['retained']][:16]
        reviews.append(review)
        if not review['accepted']:
            feature_error = max(feature_error, 2.)
        print('REDUCTION_TRIAL', {'triangles': n, 'surface_error_m': err,
              'feature_failures': local['fails'][:5] if protected is not None and protected.get('contrast_report') else [],
                                  'feature_error': feature_error,
                                  'extreme_folds_per_1k': None if folds is None else folds['per_1k']}, flush=True)
        mesh2 = o2.data
        bpy.data.objects.remove(o2)
        bpy.data.meshes.remove(mesh2)
        return err, n, feature_error, failed

    # Minimum complexity depends on geometry, not the density of its source grid.
    lo, hi = max(min_tris / tris0, 1e-6), 1.0
    best = 1.0
    best_error = 0.0
    best_count = tris0
    best_focus = None
    for _ in range(8):
        mid = (lo * hi) ** 0.5
        err, n, feature_error, failed = trial(mid)
        if err <= tol and feature_error <= 1:
            best, hi = mid, mid
            best_error = err
            best_count = n
        else:
            lo = mid
    # Coarse retries protect only observed failures instead of retaining the
    # source grid everywhere. All original hard checks remain in force.
    if protected is not None and protected.get('contrast_report') and protected.get('ids'):
        focus = set()
        coarse = max(min_tris / tris0, best * .6)
        ratio = coarse
        previous_failures = float('inf')
        for attempt in range(6):
            err, n, feature_error, failed = trial(ratio, focus)
            if err <= tol and feature_error <= 1 and n < best_count:
                best, best_error, best_count, best_focus = ratio, err, n, set(
                    focus)
                break
            if not failed and err <= tol:
                break
            failing_ids = {item.split(': ', 1)[-1] for item in failed}
            stalled = failing_ids <= focus and len(failed) >= previous_failures
            if err > tol or stalled:
                if ratio > coarse:
                    break
                ratio = max(min_tris / tris0, best * .8)
            focus.update(failing_ids)
            previous_failures = len(failed)
    if best < 1.0:
        group = detail_group if best_focus is None else focus_group(
            obj, best_focus)
        modifier_for(obj, 'to_error', best, group)
        apply_mods(obj)
    if detail_group is not None:
        stored_group = obj.vertex_groups.get('__hull_detail_guard')
        if stored_group is not None:
            obj.vertex_groups.remove(stored_group)
    for group in list(obj.vertex_groups):
        if group.name.startswith('__hull_local_retry'):
            obj.vertex_groups.remove(group)
    import json
    obj['simplification_correction_reviews'] = json.dumps(reviews)
    err = best_error if best < 1.0 else 0.0
    return sum(len(p_.vertices) - 2 for p_ in obj.data.polygons), err


def reduce_assembly_part(obj, order, report):
    """Legacy assemblers share the same fixed error bound before texture projection."""
    if order.get('budget') == 'share':
        return
    if order.get('budget', 'screen') != 'screen':
        raise ValueError('Unknown reduction policy')
    from .bake import STANDARDS
    tolerance = screen_tolerance(STANDARDS, order.get('kind', 'static'))
    if tolerance is None or not np.isfinite(tolerance) or tolerance <= 0:
        raise ValueError('Screen reduction requires a positive finite error budget')
    before = sum(len(p.vertices)-2 for p in obj.data.polygons)
    triangles, error = decimate_to_error(obj, tolerance)
    obj['bounded_surface_error'] = True
    refresh_normals(obj)
    report.setdefault('reduction', []).append({'part': obj.name,
        'before': before, 'triangles': triangles, 'sampled_error_m': error,
        'tolerance_m': tolerance, 'stage': 'before texture projection'})
