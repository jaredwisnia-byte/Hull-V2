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

    def modifier_for(target, name, ratio):
        modifier = target.modifiers.new(name, 'DECIMATE')
        modifier.ratio = ratio
        if detail_group is not None:
            modifier.vertex_group = detail_group.name
            modifier.invert_vertex_group = True
            # Blender adds edge_length * factor to squared plane error. Its
            # factor therefore needs physical length units, like our tolerance.
            modifier.vertex_group_factor = tol * max(
                1., tol / max(float(np.median(protected['tolerance_m'])), 1e-9))
        return modifier

    def trial(ratio):
        o2 = obj.copy()
        o2.data = me.copy()
        bpy.context.scene.collection.objects.link(o2)
        modifier_for(o2, 'd', ratio)
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
        print('REDUCTION_TRIAL', {'triangles': n, 'surface_error_m': err,
              'feature_failures': local['fails'][:5] if protected is not None and protected.get('contrast_report') else [],
                                  'feature_error': feature_error}, flush=True)
        mesh2 = o2.data
        bpy.data.objects.remove(o2)
        bpy.data.meshes.remove(mesh2)
        return err, n, feature_error

    # Minimum complexity depends on geometry, not the density of its source grid.
    lo, hi = max(min_tris / tris0, 1e-6), 1.0
    best = 1.0
    best_error = 0.0
    for _ in range(8):
        mid = (lo * hi) ** 0.5
        err, n, feature_error = trial(mid)
        if err <= tol and feature_error <= 1:
            best, hi = mid, mid
            best_error = err
        else:
            lo = mid
    if best < 1.0:
        modifier_for(obj, 'to_error', best)
        apply_mods(obj)
    if detail_group is not None:
        stored_group = obj.vertex_groups.get('__hull_detail_guard')
        if stored_group is not None:
            obj.vertex_groups.remove(stored_group)
    err = best_error if best < 1.0 else 0.0
    return sum(len(p_.vertices) - 2 for p_ in obj.data.polygons), err
