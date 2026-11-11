"""Shared screen-space error budgets and pre-paint mesh simplification."""
import numpy as np


def refresh_normals(obj, sharp_angle=35):
    """Discard stale split normals after topology changes, then mark sharp edges."""
    from .core import smooth
    if obj.data.has_custom_normals:
        obj.data.normals_split_custom_set([(0, 0, 0)] * len(obj.data.loops))
    smooth(obj, sharp_angle)


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


def decimate_to_error(obj, tol, min_tris=120, samples=2500):
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

    def trial(ratio):
        o2 = obj.copy()
        o2.data = me.copy()
        bpy.context.scene.collection.objects.link(o2)
        m_ = o2.modifiers.new("d", "DECIMATE")
        m_.ratio = ratio
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
        n = sum(len(p_.vertices) - 2 for p_ in o2.data.polygons)
        mesh2 = o2.data
        bpy.data.objects.remove(o2)
        bpy.data.meshes.remove(mesh2)
        return err, n

    lo, hi = max(min_tris / tris0, 0.002), 1.0
    best = 1.0
    best_error = 0.0
    for _ in range(8):
        mid = (lo * hi) ** 0.5
        err, n = trial(mid)
        if err <= tol:
            best, hi = mid, mid
            best_error = err
        else:
            lo = mid
    if best < 1.0:
        m_ = obj.modifiers.new("to_error", "DECIMATE")
        m_.ratio = best
        apply_mods(obj)
    err = best_error if best < 1.0 else 0.0
    return sum(len(p_.vertices) - 2 for p_ in obj.data.polygons), err
