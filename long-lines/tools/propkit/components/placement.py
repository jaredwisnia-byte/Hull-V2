"""Seat components on named parents; do not hard-code camera or stove dimensions."""
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree


def place(obj, spec, objects, frames, specs):
    offset = Vector(spec["position"])
    attachment = spec.get("attachment")
    if attachment and "landmarks" in attachment:
        from .alignment import solve
        parent = objects[attachment['parent']]
        parent_matrix = Matrix(parent.get('component_transform', Matrix.Identity(4)))
        source = [p['source'] for p in attachment['landmarks']]
        target = [list(parent_matrix @ Vector(p['target'])) for p in attachment['landmarks']]
        matrix, error = solve(source, target, attachment.get('tolerance_m', .001))
        transform = Matrix(matrix.tolist())
        for vertex in obj.data.vertices:
            vertex.co = transform @ vertex.co
        obj.data.update()
        return {'position':list(transform.translation), 'transform':[list(r) for r in transform],
                'parent':attachment['parent'], 'landmark_error_m':error, 'method':'rigid_landmarks'}
    if not attachment:
        for vertex in obj.data.vertices:
            vertex.co += offset
        obj.data.update()
        return {"position": list(offset)}
    parent_name = attachment["parent"]
    parent = objects[parent_name]
    face = attachment["face"]
    overlap = attachment.get("overlap", .001)
    directions = {"front": Vector((0, 1, 0)), "back": Vector((0, -1, 0)),
                  "right": Vector((-1, 0, 0)), "left": Vector((1, 0, 0)), "top": Vector((0, 0, -1))}
    if "pixel" in attachment:
        frame = frames[parent_name].get("front")
        if frame is None:
            raise ValueError("pixel attachment parent has no front reference")
        px, py = attachment["pixel"]
        x0, y0, _, _ = frame["box"]
        bx, by, _, _ = frame["bounds"]
        rows, cols = frame["shape"]
        u, v = (px - x0 - bx) / cols, (py - y0 - by) / rows
        if not (0 <= u <= 1 and 0 <= v <= 1):
            raise ValueError("attachment pixel lies outside parent silhouette frame")
        width, _, height = specs[parent_name]["dimensions"]
        origin = Vector(parent.get("component_origin", (0, 0, 0)))
        offset.x = (u - .5) * width + origin.x - (max(v.co.x for v in obj.data.vertices) + min(v.co.x for v in obj.data.vertices)) / 2
        offset.z = (1 - v) * height + origin.z
        offset.z -= (max(v.co.z for v in obj.data.vertices) + min(v.co.z for v in obj.data.vertices)) / 2
    # Cast through the part's center in the chosen attachment direction.
    center = offset + Vector([(min(v.co[i] for v in obj.data.vertices) + max(v.co[i] for v in obj.data.vertices)) / 2 for i in range(3)])
    axis = 2 if face == "top" else (1 if face in ("front", "back") else 0)
    points = [parent.matrix_world @ v.co for v in parent.data.vertices]
    tree = BVHTree.FromPolygons(points, [p.vertices for p in parent.data.polygons])
    span = max(max(p[i] for p in points) - min(p[i] for p in points) for i in range(3))
    direction = directions[face]
    center[axis] = max(p[axis] for p in points) + span if direction[axis] < 0 else min(p[axis] for p in points) - span
    hit, _, _, _ = tree.ray_cast(center, direction, 4 * span)
    if hit is None:
        raise ValueError(f"{spec['name']}: attachment ray misses {parent_name}")
    if direction[axis] > 0:
        offset[axis] = hit[axis] + overlap - max(v.co[axis] for v in obj.data.vertices)
    else:
        offset[axis] = hit[axis] - overlap - min(v.co[axis] for v in obj.data.vertices)
    for vertex in obj.data.vertices:
        vertex.co += offset
    obj.data.update()
    return {"position": list(offset), "parent": parent_name, "face": face,
            "surface_hit": list(hit), "overlap_m": overlap}
