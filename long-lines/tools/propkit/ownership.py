"""Physical part identity through joining/baking and standalone export.

Integer face ownership is captured before joining; triangle centroids bridge the
library GLB round trip without assuming exporter vertex/triangle ordering.
"""
import json
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree


def tag_parts(parts):
    reject_duplicate_geometry(parts)
    owners = []
    for index, part in enumerate(parts):
        identifier = part.get('physical_region_id', part.name)
        if identifier in owners:
            raise ValueError('Duplicate physical part identity: ' + identifier)
        owners.append(identifier)
        attribute = part.data.attributes.get('hull_owner')
        if attribute:
            part.data.attributes.remove(attribute)
        attribute = part.data.attributes.new('hull_owner', 'INT', 'FACE')
        attribute.data.foreach_set('value', np.full(
            len(part.data.polygons), index, dtype=np.int32))
    return owners


def reject_duplicate_geometry(parts, tolerance=1e-6):
    """Reject near-coincident copies before baking, regardless of their names.

    Small contact patches between legitimate components do not constitute a
    duplicate. Both complete surfaces must coincide within metric tolerance.
    """
    clouds = []
    for part in parts:
        cloud = np.asarray([tuple(part.matrix_world @ v.co)
                           for v in part.data.vertices])
        if not len(cloud):
            raise ValueError('Empty physical part: ' + part.name)
        clouds.append(cloud)
    for i, a in enumerate(clouds):
        for j, b in enumerate(clouds[:i]):
            if np.max(abs(a.min(0) - b.min(0))) > tolerance or np.max(abs(a.max(0) - b.max(0))) > tolerance:
                continue
            if max(cKDTree(a).query(b)[0].max(), cKDTree(b).query(a)[0].max()) < tolerance:
                raise ValueError('Duplicate geometry: ' +
                                 parts[i].name + ' and ' + parts[j].name)


def save_mesh_ownership(obj, owners, path):
    mesh = obj.data
    mesh.calc_loop_triangles()
    attribute = mesh.attributes.get('hull_owner')
    if not attribute:
        raise ValueError('Physical ownership lost during manufacturing')
    centers = []
    normals = []
    assignments = []
    for triangle in mesh.loop_triangles:
        center = np.mean([tuple(obj.matrix_world @ mesh.vertices[i].co)
                         for i in triangle.vertices], axis=0)
        centers.append(tuple(center))
        points = np.asarray(
            [tuple(obj.matrix_world @ mesh.vertices[i].co) for i in triangle.vertices])
        normal = np.cross(points[1] - points[0], points[2] - points[0])
        normals.append((normal / max(np.linalg.norm(normal), 1e-12)).tolist())
        assignments.append(attribute.data[triangle.polygon_index].value)
    document = {'owners': owners, 'triangle_centroids_m': centers, 'triangle_normals': normals, 'triangle_owners': assignments,
                'identity_source': 'manufactured physical parts; no runtime semantic relabelling'}
    Path(path).write_text(json.dumps(document))
    return document


def split_standalone(obj, document, tolerance=3e-6):
    import bpy
    import bmesh
    mesh = obj.data
    centers = np.array([np.mean([tuple(obj.matrix_world @ mesh.vertices[i].co) for i in face.vertices], axis=0)
                        for face in mesh.polygons])
    normals = np.asarray([tuple(obj.matrix_world.to_3x3().inverted(
    ).transposed() @ face.normal) for face in mesh.polygons])
    normals /= np.maximum(np.linalg.norm(normals,
                          axis=1, keepdims=True), 1e-12)
    assignment = match_ownership(document, centers, normals, tolerance)
    parts = []
    for index, name in enumerate(document['owners']):
        if not (assignment == index).any():
            continue
        part = obj.copy()
        part.data = obj.data.copy()
        part.name = name
        part['physical_part_id'] = name
        bpy.context.scene.collection.objects.link(part)
        bm = bmesh.new()
        try:
            bm.from_mesh(part.data)
            bm.faces.ensure_lookup_table()
            bm.faces.index_update()
            bmesh.ops.delete(bm, geom=[
                             face for face in bm.faces if assignment[face.index] != index], context='FACES')
            bm.to_mesh(part.data)
        finally:
            bm.free()
        parts.append(part)
    bpy.data.objects.remove(obj, do_unlink=True)
    return parts


def match_ownership(document, centers, normals, tolerance=3e-6):
    """Match oriented triangles; opposing internal caps have distinct owners.

    Ambiguous coincident triangles from different owners are an error, rather
    than whichever nearest-neighbour happened to be returned first.
    """
    original = np.c_[document['triangle_centroids_m'],
                     np.asarray(document['triangle_normals']) * .001]
    query = np.c_[centers, np.asarray(normals) * .001]
    distances, indices = cKDTree(original).query(
        query, k=min(2, len(original)))
    assignments = np.asarray(document['triangle_owners'])
    if distances.ndim == 1:
        distances = distances[:, None]
        indices = indices[:, None]
    if np.any(distances[:, 0] > tolerance):
        raise ValueError(
            'Cannot transfer part identity to changed export geometry')
    if distances.shape[1] > 1:
        ambiguous = (distances[:, 1] < tolerance) & (
            assignments[indices[:, 0]] != assignments[indices[:, 1]])
        if ambiguous.any():
            raise ValueError(
                'Duplicate coincident surfaces have ambiguous physical ownership')
    return assignments[indices[:, 0]]
