"""Native Open CASCADE trimmed-surface export; no fabricated watertight solids."""
import numpy as np


def available():
    try:
        import OCP
        return True
    except ImportError:
        return False


def contains(loop, point):
    x, y = np.asarray(loop).T
    xx, yy = np.roll(x, -1), np.roll(y, -1)
    px, py = point
    denominator = np.where(abs(yy - y) > 1e-15, yy - y, 1e-15)
    return bool(np.count_nonzero(((y > py) != (yy > py)) & (px < (xx - x) * (py - y) / denominator + x)) % 2)


def loop_groups(loops):
    arrays = [np.asarray(loop, float) for loop in loops if len(loop) >= 4]
    levels = [sum(contains(other, loop[0]) for j, other in enumerate(arrays) if i != j)
              for i, loop in enumerate(arrays)]
    return [(loop, [hole for j, hole in enumerate(arrays) if levels[j] == levels[i] + 1 and contains(loop, hole[0])])
            for i, loop in enumerate(arrays) if levels[i] % 2 == 0]


def native_surface(document):
    from OCP.Geom import Geom_BSplineSurface
    from OCP.gp import gp_Pnt
    from OCP.collections import Array2_gp_Pnt, Array2_double, Array1_double, Array1_int
    points = np.asarray(document['control_points_vu'], float)
    weights = np.asarray(document['weights_vu'], float)
    if points.shape != (*weights.shape, 3) or weights.ndim != 2:
        raise ValueError(
            'A rectangular 3D control net and matching weight grid are required')
    if np.any(weights <= 0) or not np.isfinite(weights).all() or not np.isfinite(points).all():
        raise ValueError(
            'Finite control points and positive rational weights required')
    scale = {'metres': 1000., 'millimetres': 1.}.get(document['units'])
    if scale is None:
        raise ValueError('Explicit supported CAD units required')
    nv, nu = weights.shape
    poles, rational = Array2_gp_Pnt(1, nu, 1, nv), Array2_double(1, nu, 1, nv)
    for v in range(nv):
        for u in range(nu):
            poles.SetValue(u + 1, v + 1, gp_Pnt(*(points[v, u] * scale)))
            rational.SetValue(u + 1, v + 1, float(weights[v, u]))

    def knot_arrays(values):
        unique, counts = np.unique(values, return_counts=True)
        real, integer = Array1_double(
            1, len(unique)), Array1_int(1, len(unique))
        for i, (value, count) in enumerate(zip(unique, counts), 1):
            real.SetValue(i, float(value))
            integer.SetValue(i, int(count))
        return real, integer
    uk, um = knot_arrays(document['knots_u'])
    vk, vm = knot_arrays(document['knots_v'])
    return Geom_BSplineSurface(poles, rational, uk, vk, um, vm,
                               int(document['degree_u']), int(document['degree_v']), False, False)


def wire_on_surface(loop, surface, positive=True):
    from OCP.Geom2d import Geom2d_BSplineCurve
    from OCP.gp import gp_Pnt2d
    from OCP.collections import Array1_gp_Pnt2d, Array1_double, Array1_int
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeWire
    loop = np.asarray(loop, float)
    if not np.allclose(loop[0], loop[-1]):
        loop = np.r_[loop, loop[:1]]
    signed = np.sum(loop[:-1, 0] * loop[1:, 1] - loop[1:, 0] * loop[:-1, 1])
    if (signed > 0) != positive:
        loop = loop[::-1]
    # Consecutive raster-boundary duplicates do not define a curve segment.
    keep = np.r_[True, np.linalg.norm(np.diff(loop, axis=0), axis=1) > 1e-10]
    loop = loop[keep]
    if len(loop) < 4:
        raise ValueError('Degenerate CAD trim loop')
    count = len(loop)
    poles = Array1_gp_Pnt2d(1, count)
    knots, multiplicity = Array1_double(1, count), Array1_int(1, count)
    for i, (u, v) in enumerate(loop, 1):
        poles.SetValue(i, gp_Pnt2d(float(u), float(v)))
        knots.SetValue(i, float(i - 1))
        multiplicity.SetValue(i, 2 if i in (1, count) else 1)
    curve = Geom2d_BSplineCurve(poles, knots, multiplicity, 1, False)
    edge = BRepBuilderAPI_MakeEdge(curve, surface)
    if not edge.IsDone():
        raise ValueError('CAD trim edge construction failed')
    wire = BRepBuilderAPI_MakeWire(edge.Edge())
    if not wire.IsDone():
        raise ValueError('CAD trim wire construction failed')
    return wire.Wire()


def export_step(documents, destination):
    """Export validated trimmed NURBS faces. Open charts remain open charts."""
    from pathlib import Path
    from OCP.BRep import BRep_Builder
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.BRepCheck import BRepCheck_Analyzer
    from OCP.BRepLib import BRepLib
    from OCP.TopoDS import TopoDS_Compound
    from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs
    from OCP.IFSelect import IFSelect_RetDone
    compound = TopoDS_Compound()
    builder = BRep_Builder()
    builder.MakeCompound(compound)
    count = 0
    for document in documents:
        if not document.get('fit', {}).get('accepted', False):
            raise ValueError(
                'An out-of-tolerance surface cannot be exported as accepted CAD')
        surface = native_surface(document)
        for outer, holes in loop_groups(document['trim_loops_uv']):
            face = BRepBuilderAPI_MakeFace(
                surface, wire_on_surface(outer, surface), True)
            for hole in holes:
                face.Add(wire_on_surface(hole, surface, positive=False))
            if not face.IsDone():
                raise ValueError('Trimmed CAD face construction failed')
            shape = face.Face()
            BRepLib.BuildCurves3d_s(shape, 1e-5)
            if not BRepCheck_Analyzer(shape).IsValid():
                raise ValueError(
                    'CAD kernel rejected trimmed surface topology')
            builder.Add(compound, shape)
            count += 1
    if not count:
        raise ValueError('No accepted CAD surface faces')
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    writer = STEPControl_Writer()
    if writer.Transfer(compound, STEPControl_AsIs) != IFSelect_RetDone or writer.Write(str(destination)) != IFSelect_RetDone:
        raise RuntimeError('STEP exchange failed')
    return {'path': str(destination), 'faces': count, 'kernel_valid': True,
            'units': 'millimetres', 'closed_solid': False, 'representation': 'trimmed NURBS surface compound'}
