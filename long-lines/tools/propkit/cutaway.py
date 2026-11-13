"""Non-destructive surface cutaways for inspection, never replacement assets.

Cut boundaries stay open. The separate section drawing describes cut material;
blindly filling boundaries here could falsely cap a real hollow component.
"""


def export_surface_cutaway(objects, plane, destination):
    import bpy
    import bmesh
    from mathutils import Vector

    origin, normal, _, _ = plane.frame()
    selected = list(bpy.context.selected_objects)
    active = bpy.context.view_layer.objects.active
    temporary = []
    meshes = []
    try:
        bpy.ops.object.select_all(action='DESELECT')
        for source in objects:
            copied = source.copy()
            copied.data = source.data.copy()
            copied.name = source.name + '_surface_cutaway'
            bpy.context.scene.collection.objects.link(copied)
            temporary.append(copied)
            meshes.append(copied.data)
            mesh = bmesh.new()
            try:
                mesh.from_mesh(copied.data)
                local_origin = copied.matrix_world.inverted() @ Vector(origin)
                local_normal = copied.matrix_world.to_3x3().transposed() @ Vector(normal)
                bmesh.ops.bisect_plane(
                    mesh, geom=list(mesh.verts) +
                    list(mesh.edges)+list(mesh.faces),
                    plane_co=local_origin, plane_no=local_normal.normalized(),
                    dist=1e-7, clear_outer=True, clear_inner=False,
                )
                mesh.to_mesh(copied.data)
            finally:
                mesh.free()
            copied.select_set(True)
        bpy.ops.export_scene.gltf(filepath=str(
            destination), export_format='GLB', use_selection=True)
    finally:
        for obj in temporary:
            bpy.data.objects.remove(obj, do_unlink=True)
        for mesh in meshes:
            if mesh.users == 0:
                bpy.data.meshes.remove(mesh)
        for obj in selected:
            obj.select_set(True)
        bpy.context.view_layer.objects.active = active
    return str(destination)
