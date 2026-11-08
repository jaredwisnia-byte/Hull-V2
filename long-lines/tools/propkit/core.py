"""Geometry building blocks for prop recipes.

Every function adds one part to the current prop and returns the Blender object.
Units are metres, Z is up, the prop's front faces -Y (it becomes +Z in Godot),
and the prop's origin is its bottom centre (floor contact at z = 0).
"""

import math

import bmesh
import bpy
from mathutils import Euler, Matrix, Vector

PARTS = []


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    PARTS.clear()


def link(obj):
    bpy.context.collection.objects.link(obj)
    PARTS.append(obj)
    return obj


def select_only(obj):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def apply_mods(obj):
    select_only(obj)
    for m in list(obj.modifiers):
        bpy.ops.object.modifier_apply(modifier=m.name)


def smooth(obj, angle=40):
    select_only(obj)
    bpy.ops.object.shade_smooth()
    if hasattr(obj.data, "set_sharp_from_angle"):
        obj.data.set_sharp_from_angle(angle=math.radians(angle))
    else:  # Blender 4.0
        obj.data.use_auto_smooth = True
        obj.data.auto_smooth_angle = math.radians(angle)
    return obj


def _finish(obj, mat, loc, rot, bevel, segments, angle):
    obj.location = loc
    obj.rotation_euler = rot
    if mat is not None:
        obj.data.materials.append(mat)
    if bevel > 0:
        b = obj.modifiers.new("bevel", "BEVEL")
        b.width = bevel
        b.segments = segments
        b.limit_method = "ANGLE"
        apply_mods(obj)
    return smooth(obj, angle)


def mesh_obj(name, bm):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return link(bpy.data.objects.new(name, me))


def box(size, loc=(0, 0, 0), mat=None, bevel=0.004, segments=3, rot=(0, 0, 0), name="box"):
    """A box of `size` centred at `loc`. Bevelled by default: nothing is razor sharp."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co = Vector((v.co.x * size[0], v.co.y * size[1], v.co.z * size[2]))
    bevel = min(bevel, min(size) * 0.45)
    return _finish(mesh_obj(name, bm), mat, loc, rot, bevel, segments, 40)


def floor_box(size, x=0, y=0, z=0, **kw):
    """A box resting on z (its bottom at z)."""
    return box(size, (x, y, z + size[2] / 2), **kw)


def cyl(r, depth, loc=(0, 0, 0), mat=None, verts=24, rot=(0, 0, 0), r_top=None, bevel=0.0,
        flutes=0, name="cyl"):
    """A cylinder (or cone with r_top) along local Z, centred at loc."""
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=True, segments=verts, radius1=r,
                          radius2=r if r_top is None else r_top, depth=depth)
    if flutes:
        for v in bm.verts:
            rr = math.hypot(v.co.x, v.co.y)
            if rr > min(r, r_top or r) * 0.5:
                a = math.atan2(v.co.y, v.co.x)
                k = 1.0 - 0.07 * (0.5 + 0.5 * math.cos(a * flutes))
                v.co.x *= k
                v.co.y *= k
    bevel = min(bevel, depth * 0.45, r * 0.45)
    return _finish(mesh_obj(name, bm), mat, loc, rot, bevel, 2, 50)


def lathe(profile, loc=(0, 0, 0), mat=None, verts=32, rot=(0, 0, 0), name="lathe", angle=60):
    """Spins a list of (radius, z) points around Z: bottles, cans, lamps, bowls, mugs."""
    bm = bmesh.new()
    rings = []
    for r, z in profile:
        ring = []
        for i in range(verts):
            a = 2 * math.pi * i / verts
            ring.append(bm.verts.new((math.cos(a) * r, math.sin(a) * r, z)))
        rings.append(ring)
    for j in range(len(rings) - 1):
        for i in range(verts):
            a, b = rings[j][i], rings[j][(i + 1) % verts]
            c, d = rings[j + 1][(i + 1) % verts], rings[j + 1][i]
            bm.faces.new((a, b, c, d))
    if profile[0][0] > 1e-4:
        bm.faces.new(list(reversed(rings[0])))
    if profile[-1][0] > 1e-4:
        bm.faces.new(rings[-1])
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    obj = mesh_obj(name, bm)
    return _finish(obj, mat, loc, rot, 0, 0, angle)


def tube(points, r, mat=None, sides=8, name="tube"):
    """A round tube along a polyline (pipes, cords, handles, rods)."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    vs = [bm.verts.new(p) for p in points]
    for a, b in zip(vs, vs[1:]):
        bm.edges.new((a, b))
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(obj)
    obj.modifiers.new("skin", "SKIN")
    for v in obj.data.skin_vertices[0].data:
        v.radius = (r, r)
    s = obj.modifiers.new("sub", "SUBSURF")
    s.levels = 1
    if mat is not None:
        obj.data.materials.append(mat)
    apply_mods(obj)
    PARTS.append(obj)
    return smooth(obj, 80)


def rod(a, b, r, mat=None, verts=12, name="rod"):
    """A straight cylinder from point a to point b."""
    a, b = Vector(a), Vector(b)
    d = b - a
    rot = Vector((0, 0, 1)).rotation_difference(d.normalized()).to_euler()
    return cyl(r, d.length, tuple((a + b) / 2), mat, verts=verts, rot=tuple(rot), name=name)


def text(body, size, loc, mat, rot=(math.radians(90), 0, 0), extrude=0.001, align="CENTER", name="text"):
    cu = bpy.data.curves.new(name, "FONT")
    cu.body = body
    cu.size = size
    cu.extrude = extrude
    cu.align_x = align
    obj = link(bpy.data.objects.new(name, cu))
    obj.location = loc
    obj.rotation_euler = rot
    select_only(obj)
    bpy.ops.object.convert(target="MESH")
    obj.data.materials.clear()
    obj.data.materials.append(mat)
    return obj


def label_card(size, loc, mat, rot=(0, 0, 0), name="label"):
    """A thin box whose front face (-Y) shows an image material's label (0..1 planar)."""
    obj = box((size[0], size[1], size[2]), loc, mat, bevel=min(size) * 0.3, rot=rot, name=name)
    planar_uv(obj, 0, 2, size[0], size[2])
    return obj


def planar_uv(obj, ax_u, ax_v, w, h, flip_u=False):
    """Stores 0..1 planar coordinates (object space) in a 'label_uv' attribute so an
    image survives joining and re-unwrapping."""
    me = obj.data
    attr = me.color_attributes.get("label_uv") or me.color_attributes.new("label_uv", "FLOAT_COLOR", "POINT")
    for i, v in enumerate(me.vertices):
        u = v.co[ax_u] / w + 0.5
        if flip_u:
            u = 1.0 - u
        attr.data[i].color = (u, v.co[ax_v] / h + 0.5, 0, 1)
    return obj


def wrap_uv(obj, h, z0=0.0):
    """Cylindrical 0..1 coordinates around Z (labels on cans, bottles, jars)."""
    me = obj.data
    attr = me.color_attributes.get("label_uv") or me.color_attributes.new("label_uv", "FLOAT_COLOR", "POINT")
    for i, v in enumerate(me.vertices):
        u = (math.atan2(v.co.x, -v.co.y) / (2 * math.pi)) % 1.0
        attr.data[i].color = (u, (v.co.z - z0) / h, 0, 1)
    return obj


def squircle(x, y, n=6.0):
    if x == 0 and y == 0:
        return 0.0, 0.0
    m = max(abs(x), abs(y))
    r = (abs(x) ** n + abs(y) ** n) ** (1.0 / n)
    return x * m / r, y * m / r


def round_y_edges(obj, radius, segments=6):
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    edges = [e for e in bm.edges if abs((e.verts[0].co - e.verts[1].co).normalized().y) > 0.9]
    bmesh.ops.bevel(bm, geom=edges, offset=radius, segments=segments, profile=0.5, affect="EDGES")
    bm.to_mesh(obj.data)
    bm.free()


def cushion(size, loc, mat, puff=0.25, rot=(0, 0, 0), name="cushion"):
    """A soft, rounded block: cushions, pillows, mattresses, folded clothes."""
    obj = box(size, loc, mat, bevel=min(size) * 0.45, segments=4, rot=rot, name=name)
    s = obj.modifiers.new("sub", "SUBSURF")
    s.levels = 1
    if puff:
        c = obj.modifiers.new("cast", "CAST")
        c.factor = puff
        c.cast_type = "SPHERE"
    apply_mods(obj)
    return smooth(obj, 80)


def jitter(obj, amount, seed=1):
    """Random vertex jitter: crumpled paper, lumpy fabric, old soft things."""
    import random
    rnd = random.Random(seed)
    for v in obj.data.vertices:
        v.co += Vector((rnd.uniform(-1, 1), rnd.uniform(-1, 1), rnd.uniform(-1, 1))) * amount
    return obj


def sag(obj, amount, axis="z"):
    """Pushes the middle of the top surface down (worn seats, old mattresses)."""
    xs = [v.co.x for v in obj.data.vertices]
    ys = [v.co.y for v in obj.data.vertices]
    zs = [v.co.z for v in obj.data.vertices]
    cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
    hx, hy, top = (max(xs) - min(xs)) / 2 or 1, (max(ys) - min(ys)) / 2 or 1, max(zs)
    for v in obj.data.vertices:
        f = max(0.0, 1 - ((v.co.x - cx) / hx) ** 2) * max(0.0, 1 - ((v.co.y - cy) / hy) ** 2)
        if v.co.z > top - 0.03:
            v.co.z -= amount * f
    return obj
