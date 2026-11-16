"""Tolerance-driven CAD tessellation and a thin Blender adapter.

The B-rep is in millimetres at the drawing's corner origin. Blender receives
metres, centred in X/Y, Z up from zero. No voxel field or painted relief enters
this station. OpenCascade meshing is single-threaded and its polygon cache is
cleared before each resolution, so the requested deflection is actually used.
"""
import hashlib
import math
from collections import defaultdict
from pathlib import Path

import numpy as np

ANGULAR_DEFLECTION_RAD = 0.5
NORMAL_ATTRIBUTE = 'cad_surface_normal'
FACE_ATTRIBUTE = 'cad_face_id'


def _face_triangulation(face, face_id):
    """Read an existing cache; never silently remesh at another deflection."""
    from OCP.BRep import BRep_Tool
    from OCP.TopLoc import TopLoc_Location
    location = TopLoc_Location()
    mesh = BRep_Tool.Triangulation_s(face.wrapped, location)
    if mesh is None or mesh.NbTriangles() == 0:
        raise RuntimeError('CAD face %d triangulation is missing or its cache was invalidated; '
                           'mesh after geometry helpers' % face_id)
    return mesh, location


def tessellate(solid, size_m, tolerance_m):
    """Return welded triangles, B-rep face IDs and analytic corner normals.

    Coordinates are canonicalized to 1 nm (1e-6 mm), well below even the
    engineering tolerance. All B-rep boundaries remain identifiable; analytic
    normals keep tangent face joins visually continuous across those boundaries.
    """
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.BRepLProp import BRepLProp_SLProps
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.BRepTools import BRepTools
    from OCP.TopAbs import TopAbs_REVERSED

    if not math.isfinite(tolerance_m) or tolerance_m <= 0:
        raise ValueError('CAD tessellation tolerance must be positive metres')
    BRepTools.Clean_s(solid.wrapped)
    positions, lookup, triangles = [], {}, []
    fallback_nodes, degenerate_triangles = 0, 0
    def face_key(face):
        box = face.bounding_box()
        return tuple(round(v, 6) for v in (*box.min, *box.max, *face.center(), face.area))

    # build123d's bounding-box helper clears cached triangulations. Freeze every
    # geometric key before meshing, and use the original position to break ties.
    keyed_faces = [(face_key(face), position, face)
                   for position, face in enumerate(solid.faces())]
    faces = [face for _, _, face in sorted(keyed_faces, key=lambda item: (item[0], item[1]))]
    mesher = BRepMesh_IncrementalMesh(
        solid.wrapped, tolerance_m * 1000, False, ANGULAR_DEFLECTION_RAD, False)
    if not mesher.IsDone():
        raise RuntimeError('OpenCascade tessellation did not complete')
    for face_id, face in enumerate(faces):
        mesh, location = _face_triangulation(face, face_id)
        reversed_face = face.wrapped.Orientation() == TopAbs_REVERSED
        surface = BRepAdaptor_Surface(face.wrapped)
        node_ids, normals = {}, {}
        for index in range(1, mesh.NbNodes() + 1):
            point = mesh.Node(index).Transformed(location.Transformation())
            key = tuple(0.0 if round(v, 6) == 0 else round(v, 6)
                        for v in (point.X(), point.Y(), point.Z()))
            if key not in lookup:
                lookup[key] = len(positions)
                positions.append(key)
            node_ids[index] = lookup[key]
            normal = None
            if mesh.HasUVNodes():
                uv = mesh.UVNode(index)
                properties = BRepLProp_SLProps(surface, uv.X(), uv.Y(), 1, 1e-9)
                if properties.IsNormalDefined():
                    n = properties.Normal()
                    normal = np.asarray((n.X(), n.Y(), n.Z())) * (-1 if reversed_face else 1)
            if normal is None:
                fallback_nodes += 1
            normals[index] = normal
        for index in range(1, mesh.NbTriangles() + 1):
            nodes = list(mesh.Triangle(index).Get())
            if reversed_face:
                nodes[1], nodes[2] = nodes[2], nodes[1]
            ids = [node_ids[node] for node in nodes]
            points = np.asarray([positions[i] for i in ids])
            cross = np.cross(points[1] - points[0], points[2] - points[0])
            length = np.linalg.norm(cross)
            if len(set(ids)) < 3 or length <= 1e-15:
                degenerate_triangles += 1
                continue
            geometric = cross / length
            corner_normals = [normals[node] if normals[node] is not None else geometric for node in nodes]
            pivot = ids.index(min(ids))
            ids = ids[pivot:] + ids[:pivot]
            corner_normals = corner_normals[pivot:] + corner_normals[:pivot]
            triangles.append((face_id, ids, corner_normals))
    if not triangles:
        raise ValueError('CAD solid produced no nondegenerate triangles')
    used = {index for _, ids, _ in triangles for index in ids}
    permutation = sorted(used, key=positions.__getitem__)
    remap = {old: new for new, old in enumerate(permutation)}
    vertices = np.asarray([positions[i] for i in permutation], dtype=np.float64) / 1000
    vertices -= np.asarray((size_m['width'] / 2, size_m['depth'] / 2, 0))
    canonical = []
    for face_id, ids, normals in triangles:
        ids = [remap[i] for i in ids]
        pivot = ids.index(min(ids))
        canonical.append((face_id, ids[pivot:] + ids[:pivot], normals[pivot:] + normals[:pivot]))
    triangles = canonical
    triangles.sort(key=lambda row: (row[0], tuple(row[1])))
    indices = np.asarray([row[1] for row in triangles], dtype=np.int32)
    corner_normals = np.asarray([row[2] for row in triangles], dtype=np.float64)
    face_ids = np.asarray([row[0] for row in triangles], dtype=np.int32)
    digest = hashlib.sha256(vertices.tobytes() + indices.tobytes() + corner_normals.tobytes()).hexdigest()
    return {'vertices': vertices, 'triangles': indices, 'normals': corner_normals,
            'face_ids': face_ids, 'report': {
                'tolerance_m': tolerance_m, 'angular_deflection_rad': ANGULAR_DEFLECTION_RAD,
                'parallel': False, 'vertices': len(vertices), 'triangles': len(indices),
                'brep_faces': len(faces), 'normal_fallback_nodes': fallback_nodes,
                'degenerate_triangles_discarded': degenerate_triangles, 'mesh_sha256': digest}}


def restore_normals(obj):
    """Restore source face normals after the existing finish station's BMesh pass.

    Corner/face attributes survive triangulation and UV operations. Every B-rep
    boundary is marked sharp, including part/feature seams. Tangent boundaries
    retain matching analytic normals; they do not acquire an artificial crease.
    """
    mesh = obj.data
    normals = mesh.attributes.get(NORMAL_ATTRIBUTE)
    face_ids = mesh.attributes.get(FACE_ATTRIBUTE)
    if normals is None or face_ids is None or len(normals.data) != len(mesh.loops):
        raise ValueError('CAD normal provenance was lost during mesh finishing')
    owners = defaultdict(set)
    for polygon in mesh.polygons:
        polygon.use_smooth = True
        for loop in polygon.loop_indices:
            owners[mesh.loops[loop].edge_index].add(face_ids.data[polygon.index].value)
    mesh.set_sharp_from_angle(angle=math.radians(30))
    for edge in mesh.edges:
        if len(owners[edge.index]) > 1:
            edge.use_edge_sharp = True
    mesh.normals_split_custom_set([tuple(value.vector) for value in normals.data])
    mesh.update()


def to_object(data, name, register=True):
    """Blender adapter; importing this module does not require Blender."""
    import bpy
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(data['vertices'].tolist(), [], data['triangles'].tolist())
    mesh.update()
    normal_attribute = mesh.attributes.new(NORMAL_ATTRIBUTE, 'FLOAT_VECTOR', 'CORNER')
    normal_attribute.data.foreach_set('vector', data['normals'].reshape(-1).tolist())
    face_attribute = mesh.attributes.new(FACE_ATTRIBUTE, 'INT', 'FACE')
    face_attribute.data.foreach_set('value', data['face_ids'].tolist())
    obj = bpy.data.objects.new(name, mesh)
    if register:
        from .core import link
        link(obj)
    else:
        bpy.context.collection.objects.link(obj)
    obj['cad_surface_normals'] = True
    obj['bounded_surface_error'] = True  # standardize reports budget excess; never decimates the solid
    restore_normals(obj)
    return obj


def build(record, masks, tolerance_m, name, destination):
    """One B-rep supplies the engineering export and both mesh resolutions."""
    from OCP.BRepCheck import BRepCheck_Analyzer
    from . import cad_model
    destination = Path(destination)
    solid, construction = cad_model.build_solid(record, masks)
    if solid is None or not BRepCheck_Analyzer(solid.wrapped).IsValid():
        raise ValueError('CAD construction produced an invalid B-rep')
    if len(solid.solids()) != 1:
        raise ValueError('CAD image-only construction currently requires one drawn body')
    construction['mesh_source'] = 'cad'
    exported = cad_model.export(record, masks, destination, name, prebuilt=(solid, construction))
    low = tessellate(solid, record['size_m'], tolerance_m)
    high = tessellate(solid, record['size_m'], min(.0002, tolerance_m / 2))
    obj = to_object(low, name)
    source = to_object(high, name + '__high', register=False)
    obj['dense_source_name'] = source.name
    obj['hull_frame'] = [record['size_m'][key] for key in ('width', 'depth', 'height')]
    return obj, {'construction': 'cad', **low['report'], 'high': high['report'],
                 'source_step': exported['step'], 'construction_report': str(destination / (name + '_cad.json'))}
