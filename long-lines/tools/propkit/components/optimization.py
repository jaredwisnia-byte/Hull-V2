"""Simplify before painting: remove planar subdivisions, then bound surface error."""
import math
import bmesh


def optimize(obj, tolerance):
    from .reconstruction import triangle_count
    from ..parts_layout import decimate_to_error
    before = triangle_count(obj)
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.dissolve_limit(bm, angle_limit=math.radians(.1), use_dissolve_boundaries=False,
                             verts=list(bm.verts), edges=list(bm.edges), delimit={'NORMAL'})
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()
    planar = triangle_count(obj)
    after, error = decimate_to_error(obj, tolerance, min_tris=12)
    return {'before':before, 'after_planar':planar, 'after':after, 'surface_error_m':error, 'tolerance_m':tolerance}
