"""Parts from the drawing as their own solids, joined to the body (docs/DRAFTSMAN_PIPELINE.md, stage 5).

The body is a smoothed field of a few millimetres per voxel; it cannot hold a key cap or the gap
between two keys. The draftsman stage confirms such parts along projection lines, so they are built
here as solids at their measured place and size and merged with the body by an exact boolean union,
before texturing: the views are projected onto them like onto everything else.

Coordinates: the drawing's body coordinates run 0..1 over width (x), depth (y, front = 0) and height
(z, ground = 0); the hull object is centred in x and y with its base at z = 0 (propkit/hull.py).
"""


def _box(name, x0, x1, y0, y1, z0, z1):
    import bpy
    import bmesh
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    v = [bm.verts.new((x, y, z)) for z in (z0, z1) for y in (y0, y1) for x in (x0, x1)]
    for f in ((0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)):
        bm.faces.new([v[i] for i in f])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def add_rows(obj, rows, W, D, H, report=None):
    """Each instance of each validated row (propkit/draftsman.validated_rows) as a solid block from the
    gap floor to the top of its band, merged with the body."""
    import bpy
    if not rows:
        return obj
    parts = []
    for r, row in enumerate(rows):
        if row.get('along') != 'x' or 'y' not in row['band'] or 'z' not in row['band']:
            continue                     # rows along depth or height: not built here yet
        y0, y1 = row['band']['y']
        z0, z1 = row['band']['z']
        floor = row.get('floor', z0 - (z1 - z0))
        for i, (x0, x1) in enumerate(row['instances']):
            parts.append(_box('part_r%d_%d' % (r, i), -W / 2 + x0 * W, -W / 2 + x1 * W,
                              -D / 2 + y0 * D, -D / 2 + y1 * D, floor * H, z1 * H))
    if not parts:
        return obj
    # one object of all parts, one exact union with the body
    bpy.ops.object.select_all(action='DESELECT')
    for p in parts:
        p.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.object.join()
    joined = parts[0]
    mod = obj.modifiers.new('parts_union', 'BOOLEAN')
    mod.operation = 'UNION'
    mod.solver = 'EXACT'
    mod.object = joined
    bpy.context.view_layer.objects.active = obj
    before = len(obj.data.polygons)
    bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.data.objects.remove(joined, do_unlink=True)
    if report is not None:
        report['part_solids'] = {'rows': len(rows), 'blocks': len(parts),
                                 'faces_before': before, 'faces_after': len(obj.data.polygons)}
    return obj
