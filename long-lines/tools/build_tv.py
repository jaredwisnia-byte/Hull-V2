"""Builds the hero television prop for Long Lines and bakes its textures.

A mid-1970s 19-inch table-model colour TV ("Westbury", an invented brand) in a
walnut-grain cabinet, on a tapered-leg stand, with rabbit ears and a doily.

Run headless:
    blender --background --factory-startup --python tools/build_tv.py

Writes to assets/props/tv/:
    tv.glb            one mesh, origin at the bottom centre, front facing +Z in Godot
    tv_albedo.png     base colour with crevice grime, edge wear and dust baked in
    tv_normal.png     tangent-space normal map (wood grain, brushing, knurling)
    tv_orm.png        R = 1, G = roughness, B = metallic
"""

import math
import os
import sys

import bmesh
import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.normpath(os.path.join(HERE, "..", "assets", "props", "tv"))
TEX_SIZE = int(os.environ.get("TV_TEX", "2048"))
SAMPLES = int(os.environ.get("TV_SAMPLES", "48"))

# ---------------------------------------------------------------- scene

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.unit_settings.system = "METRIC"
parts = []


def link(obj):
    bpy.context.collection.objects.link(obj)
    parts.append(obj)
    return obj


def select_only(obj):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def apply_mods(obj):
    select_only(obj)
    for m in list(obj.modifiers):
        bpy.ops.object.modifier_apply(modifier=m.name)


def shade_smooth(obj, angle=40):
    select_only(obj)
    bpy.ops.object.shade_smooth()
    if hasattr(obj.data, "set_sharp_from_angle"):
        obj.data.set_sharp_from_angle(angle=math.radians(angle))
    else:  # Blender 4.0
        obj.data.use_auto_smooth = True
        obj.data.auto_smooth_angle = math.radians(angle)


def round_y_edges(obj, radius, segments=6):
    """Rounds only the edges running front-to-back, so a frame seen from the
    front gets rounded corners without losing its depth."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    edges = [e for e in bm.edges if abs((e.verts[0].co - e.verts[1].co).normalized().y) > 0.9]
    bmesh.ops.bevel(bm, geom=edges, offset=radius, segments=segments, profile=0.5, affect="EDGES")
    bm.to_mesh(obj.data)
    bm.free()


def new_box(name, size, loc, mat, bevel=0.0, segments=3):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co.x *= size[0]
        v.co.y *= size[1]
        v.co.z *= size[2]
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    obj = link(bpy.data.objects.new(name, me))
    obj.location = loc
    obj.data.materials.append(mat)
    if bevel > 0:
        b = obj.modifiers.new("bevel", "BEVEL")
        b.width = bevel
        b.segments = segments
        b.limit_method = "ANGLE"
        b.harden_normals = False
        apply_mods(obj)
    shade_smooth(obj)
    return obj


def new_cyl(name, r, depth, loc, mat, verts=32, rot=(0, 0, 0), r_top=None, bevel=0.0, flutes=0):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=True, segments=verts,
                          radius1=r, radius2=r if r_top is None else r_top, depth=depth)
    if flutes:
        # Knurled knob: pull every other rim vertex in.
        for v in bm.verts:
            rr = math.hypot(v.co.x, v.co.y)
            if rr > r * 0.5:
                a = math.atan2(v.co.y, v.co.x)
                k = 1.0 - 0.07 * (0.5 + 0.5 * math.cos(a * flutes))
                v.co.x *= k
                v.co.y *= k
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    obj = link(bpy.data.objects.new(name, me))
    obj.location = loc
    obj.rotation_euler = rot
    obj.data.materials.append(mat)
    if bevel > 0:
        b = obj.modifiers.new("bevel", "BEVEL")
        b.width = bevel
        b.segments = 2
        b.limit_method = "ANGLE"
        apply_mods(obj)
    shade_smooth(obj, 50)
    return obj


def squircle(x, y, n=6.0):
    """Maps a point on the unit square to a rounded rectangle (superellipse)."""
    if x == 0 and y == 0:
        return 0.0, 0.0
    m = max(abs(x), abs(y))
    r = (abs(x) ** n + abs(y) ** n) ** (1.0 / n)
    return x * m / r, y * m / r


def store_planar_uv(obj, axis_u, axis_v, origin, size, name="label_uv"):
    """Stores 0..1 planar coordinates as a colour attribute so a label image can
    be mapped onto this part even after everything is joined and re-unwrapped."""
    me = obj.data
    attr = me.color_attributes.new(name=name, type="FLOAT_COLOR", domain="POINT")
    for i, v in enumerate(me.vertices):
        p = v.co
        u = (p[axis_u] - origin[0]) / size[0] + 0.5
        w = (p[axis_v] - origin[1]) / size[1] + 0.5
        attr.data[i].color = (u, w, 0.0, 1.0)


# ---------------------------------------------------------------- materials

BAKE = {}  # material name -> {"albedo": socket, "rough": socket, "metal": socket, "out": node, "bsdf": node}


def new_mat(name):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return m, nt, bsdf, out


def ao(nt, dist, inside=False, samples=16):
    n = nt.nodes.new("ShaderNodeAmbientOcclusion")
    n.inputs["Distance"].default_value = dist
    n.inside = inside
    n.samples = samples
    n.only_local = True
    return n.outputs["AO"]


def math_node(nt, op, a, b=None, clamp=True):
    n = nt.nodes.new("ShaderNodeMath")
    n.operation = op
    n.use_clamp = clamp
    if isinstance(a, (int, float)):
        n.inputs[0].default_value = a
    else:
        nt.links.new(a, n.inputs[0])
    if b is not None:
        if isinstance(b, (int, float)):
            n.inputs[1].default_value = b
        else:
            nt.links.new(b, n.inputs[1])
    return n.outputs[0]


def mix_col(nt, fac, a, b):
    n = nt.nodes.new("ShaderNodeMix")
    n.data_type = "RGBA"
    n.blend_type = "MIX"
    if isinstance(fac, (int, float)):
        n.inputs["Factor"].default_value = fac
    else:
        nt.links.new(fac, n.inputs["Factor"])
    for sock, val in ((n.inputs[6], a), (n.inputs[7], b)):
        if isinstance(val, tuple):
            sock.default_value = val
        else:
            nt.links.new(val, sock)
    return n.outputs[2]


def ramp(nt, fac, stops):
    n = nt.nodes.new("ShaderNodeValToRGB")
    cr = n.color_ramp
    cr.elements[0].position, cr.elements[0].color = stops[0]
    cr.elements[1].position, cr.elements[1].color = stops[-1]
    for pos, col in stops[1:-1]:
        e = cr.elements.new(pos)
        e.color = col
    nt.links.new(fac, n.inputs["Fac"])
    return n.outputs["Color"]


def weathered(nt, base_col, edge_light=0.25, grime=0.45, dust=0.25):
    """Adds the painted-wear look: lighter worn edges, dark crevices, dust on top."""
    edge = ao(nt, 0.006, inside=True)                       # convex edges -> low AO inside
    edge_f = math_node(nt, "SUBTRACT", 1.0, edge)
    edge_f = math_node(nt, "POWER", edge_f, 1.5)
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 60.0
    noise.inputs["Detail"].default_value = 6.0
    chip = math_node(nt, "GREATER_THAN", noise.outputs["Fac"], 0.48)
    edge_f = math_node(nt, "MULTIPLY", edge_f, chip)
    edge_f = math_node(nt, "MULTIPLY", edge_f, edge_light * 4.0)
    col = mix_col(nt, edge_f, base_col, (0.75, 0.68, 0.58, 1.0))
    crev = ao(nt, 0.04)
    crev_f = math_node(nt, "SUBTRACT", 1.0, crev)
    crev_f = math_node(nt, "MULTIPLY", crev_f, grime * 1.6)
    col = mix_col(nt, crev_f, col, (0.05, 0.04, 0.03, 1.0))
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(geo.outputs["Normal"], sep.inputs[0])
    up = math_node(nt, "GREATER_THAN", sep.outputs["Z"], 0.8)
    dn = nt.nodes.new("ShaderNodeTexNoise")
    dn.inputs["Scale"].default_value = 9.0
    dust_f = math_node(nt, "MULTIPLY", up, dn.outputs["Fac"])
    dust_f = math_node(nt, "MULTIPLY", dust_f, dust)
    col = mix_col(nt, dust_f, col, (0.55, 0.53, 0.5, 1.0))
    return col


def bump(nt, height, strength):
    b = nt.nodes.new("ShaderNodeBump")
    b.inputs["Strength"].default_value = strength
    b.inputs["Distance"].default_value = 0.002
    nt.links.new(height, b.inputs["Height"])
    return b.outputs["Normal"]


def register(name, m, bsdf, out, albedo, rough, metal, normal=None):
    nt = m.node_tree
    if isinstance(albedo, tuple):
        bsdf.inputs["Base Color"].default_value = albedo
        rgb = nt.nodes.new("ShaderNodeRGB")
        rgb.outputs[0].default_value = albedo
        albedo = rgb.outputs[0]
    else:
        nt.links.new(albedo, bsdf.inputs["Base Color"])
    vals = {}
    for key, v in (("rough", rough), ("metal", metal)):
        if isinstance(v, (int, float)):
            val = nt.nodes.new("ShaderNodeValue")
            val.outputs[0].default_value = v
            v = val.outputs[0]
        vals[key] = v
    nt.links.new(vals["rough"], bsdf.inputs["Roughness"])
    nt.links.new(vals["metal"], bsdf.inputs["Metallic"])
    if normal is not None:
        nt.links.new(normal, bsdf.inputs["Normal"])
    BAKE[name] = {"albedo": albedo, "rough": vals["rough"], "metal": vals["metal"], "out": out, "bsdf": bsdf, "mat": m}
    return m


def mat_walnut():
    m, nt, bsdf, out = new_mat("walnut")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (1.0, 1.0, 9.0)   # grain runs horizontally
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    wave = nt.nodes.new("ShaderNodeTexWave")
    wave.wave_type = "BANDS"
    wave.bands_direction = "Z"
    wave.inputs["Scale"].default_value = 8.0
    wave.inputs["Distortion"].default_value = 5.0
    wave.inputs["Detail"].default_value = 4.0
    wave.inputs["Detail Scale"].default_value = 2.0
    nt.links.new(mp.outputs["Vector"], wave.inputs["Vector"])
    fine = nt.nodes.new("ShaderNodeTexNoise")
    fine.inputs["Scale"].default_value = 140.0
    fine.inputs["Detail"].default_value = 3.0
    nt.links.new(mp.outputs["Vector"], fine.inputs["Vector"])
    g = math_node(nt, "MULTIPLY", wave.outputs["Fac"], 0.75)
    g = math_node(nt, "ADD", g, math_node(nt, "MULTIPLY", fine.outputs["Fac"], 0.12))
    base = ramp(nt, g, [(0.0, (0.04, 0.019, 0.01, 1)), (0.45, (0.09, 0.045, 0.021, 1)), (0.8, (0.14, 0.073, 0.034, 1)), (1.0, (0.18, 0.095, 0.045, 1))])
    col = weathered(nt, base, edge_light=0.3, grime=0.5, dust=0.15)
    return register("walnut", m, bsdf, out, col, 0.42, 0.0, bump(nt, g, 0.25))


def mat_metal(name, col, rough, brushed=False, grime=0.5):
    m, nt, bsdf, out = new_mat(name)
    base = nt.nodes.new("ShaderNodeRGB")
    base.outputs[0].default_value = col
    r = rough
    normal = None
    if brushed:
        tc = nt.nodes.new("ShaderNodeTexCoord")
        mp = nt.nodes.new("ShaderNodeMapping")
        mp.inputs["Scale"].default_value = (2.0, 400.0, 400.0)
        nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
        n = nt.nodes.new("ShaderNodeTexNoise")
        n.inputs["Scale"].default_value = 3.0
        nt.links.new(mp.outputs["Vector"], n.inputs["Vector"])
        r = math_node(nt, "ADD", rough - 0.08, math_node(nt, "MULTIPLY", n.outputs["Fac"], 0.16))
        normal = bump(nt, n.outputs["Fac"], 0.08)
    c = weathered(nt, base.outputs[0], edge_light=0.0, grime=grime, dust=0.2)
    return register(name, m, bsdf, out, c, r, 1.0, normal)


def mat_plain(name, col, rough, edge=0.15, grime=0.4, dust=0.2, metal=0.0):
    m, nt, bsdf, out = new_mat(name)
    base = nt.nodes.new("ShaderNodeRGB")
    base.outputs[0].default_value = col
    c = weathered(nt, base.outputs[0], edge_light=edge, grime=grime, dust=dust)
    return register(name, m, bsdf, out, c, rough, metal)


def mat_screen():
    m, nt, bsdf, out = new_mat("screen")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Object"], sep.inputs[0])
    # Dead CRT: green-grey glass, lighter in the middle, with a soft painted
    # reflection of a window across the upper left (a Long Dark-style cheat).
    x = math_node(nt, "MULTIPLY", sep.outputs["X"], 4.5, clamp=False)
    z = math_node(nt, "MULTIPLY", sep.outputs["Z"], 5.5, clamp=False)
    rr = math_node(nt, "ADD", math_node(nt, "MULTIPLY", x, x, clamp=False), math_node(nt, "MULTIPLY", z, z, clamp=False), clamp=False)
    center = math_node(nt, "SUBTRACT", 1.0, rr)
    base = mix_col(nt, center, (0.035, 0.045, 0.042, 1.0), (0.10, 0.125, 0.115, 1.0))
    diag = math_node(nt, "ADD", sep.outputs["X"], math_node(nt, "MULTIPLY", sep.outputs["Z"], 0.8, clamp=False), clamp=False)
    band = math_node(nt, "MULTIPLY", math_node(nt, "GREATER_THAN", diag, -0.02), math_node(nt, "LESS_THAN", diag, 0.05))
    band = math_node(nt, "MULTIPLY", band, math_node(nt, "GREATER_THAN", sep.outputs["Z"], 0.03))
    band = math_node(nt, "MULTIPLY", band, 0.35)
    col = mix_col(nt, band, base, (0.42, 0.48, 0.47, 1.0))
    crev = ao(nt, 0.03)
    col = mix_col(nt, math_node(nt, "SUBTRACT", 1.0, crev), col, (0.0, 0.0, 0.0, 1.0))
    return register("screen", m, bsdf, out, col, 0.06, 0.0)


def mat_label(name, image_path, fallback):
    m, nt, bsdf, out = new_mat(name)
    attr = nt.nodes.new("ShaderNodeAttribute")
    attr.attribute_type = "GEOMETRY"
    attr.attribute_name = "label_uv"
    img = nt.nodes.new("ShaderNodeTexImage")
    img.image = bpy.data.images.load(image_path)
    img.extension = "CLIP"
    nt.links.new(attr.outputs["Vector"], img.inputs["Vector"])
    c = weathered(nt, img.outputs["Color"], edge_light=0.0, grime=0.35, dust=0.0)
    return register(name, m, bsdf, out, c, 0.5, 0.0)


def mat_doily():
    m, nt, bsdf, out = new_mat("doily")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    vor = nt.nodes.new("ShaderNodeTexVoronoi")
    vor.inputs["Scale"].default_value = 70.0
    nt.links.new(tc.outputs["Object"], vor.inputs["Vector"])
    holes = math_node(nt, "LESS_THAN", vor.outputs["Distance"], 0.25)
    col = mix_col(nt, holes, (0.86, 0.83, 0.74, 1.0), (0.32, 0.18, 0.09, 1.0))
    col = weathered(nt, col, edge_light=0.0, grime=0.25, dust=0.25)
    return register("doily", m, bsdf, out, col, 0.9, 0.0, bump(nt, holes, 0.3))


WALNUT = mat_walnut()
ALU = mat_metal("aluminium", (0.62, 0.62, 0.6, 1), 0.38, brushed=True)
CHROME = mat_metal("chrome", (0.85, 0.85, 0.86, 1), 0.16, grime=0.7)
BRASS = mat_metal("brass", (0.72, 0.52, 0.22, 1), 0.3, grime=0.8)
BLACK = mat_plain("black_plastic", (0.025, 0.024, 0.023, 1), 0.45, edge=0.12)
BEZEL = mat_plain("bezel", (0.07, 0.065, 0.06, 1), 0.35, edge=0.04, grime=0.3)
GRILLE = mat_plain("grille", (0.11, 0.075, 0.05, 1), 0.85, edge=0.0, grime=0.6, dust=0.4)
HARDBOARD = mat_plain("hardboard", (0.17, 0.12, 0.08, 1), 0.85, edge=0.05, grime=0.4, dust=0.3)
RUBBER = mat_plain("rubber", (0.02, 0.02, 0.02, 1), 0.8, edge=0.0)
LAMP = mat_plain("lamp_red", (0.35, 0.03, 0.02, 1), 0.2, edge=0.0, grime=0.0, dust=0.0)
SCREEN = mat_screen()
DIAL = mat_label("dial_face", os.path.join(OUT, "src_dial.png"), (0.7, 0.7, 0.65, 1))
PLATE = mat_label("back_plate", os.path.join(OUT, "src_plate.png"), (0.6, 0.6, 0.55, 1))
DOILY = mat_doily()

# ---------------------------------------------------------------- the stand

TOP_Z = 0.43
new_box("stand_top", (0.74, 0.46, 0.03), (0, 0, TOP_Z - 0.015), WALNUT, bevel=0.008)
new_box("stand_apron", (0.68, 0.40, 0.06), (0, 0, TOP_Z - 0.06), WALNUT, bevel=0.004)
new_box("stand_shelf", (0.62, 0.34, 0.018), (0, 0, 0.13), WALNUT, bevel=0.004)
from mathutils import Euler
for sx in (-1, 1):
    for sy in (-1, 1):
        x, y = sx * 0.3, sy * 0.17
        tilt = math.radians(7)
        rot = (-sy * tilt * 0.6, sx * tilt, 0)
        axis = Euler(rot).to_matrix() @ Vector((0, 0, 1))
        top = Vector((x, y, TOP_Z - 0.06))
        L = 0.37
        centre = top - axis * (L / 2)
        new_cyl("leg", 0.012, L, tuple(centre), WALNUT, verts=16, rot=rot, r_top=0.021, bevel=0.002)
        foot = top - axis * (L - 0.012)
        new_cyl("ferrule", 0.0128, 0.03, tuple(foot), BRASS, verts=16, rot=rot, bevel=0.0015)

# ---------------------------------------------------------------- the cabinet

W, D, H = 0.68, 0.46, 0.50
Z0 = TOP_Z + 0.008
FRONT = -D / 2
for sx in (-1, 1):
    for sy in (-1, 1):
        new_cyl("tv_foot", 0.016, 0.01, (sx * 0.28, sy * 0.18, TOP_Z + 0.005), RUBBER, verts=12)
cab = new_box("cabinet", (W, D, H), (0, 0, Z0 + H / 2), WALNUT, bevel=0.028, segments=5)

# Front fascia: a dark bezel around the screen and an aluminium control panel.
SCR_W, SCR_H = 0.405, 0.315
SCR_X, SCR_Z = -0.075, Z0 + 0.265
fascia = new_box("fascia", (0.62, 0.02, 0.44), (0, FRONT - 0.009, Z0 + 0.25), BEZEL, bevel=0.006)
FRONT = FRONT - 0.019  # everything below sits on the fascia's front face
# Screen surround: a rounded frame (outer minus inner).
outer = new_box("surround", (SCR_W + 0.05, 0.026, SCR_H + 0.05), (SCR_X, FRONT - 0.013, SCR_Z), BLACK, bevel=0.0)
cutter = new_box("cutter", (SCR_W, 0.08, SCR_H), (SCR_X, FRONT - 0.013, SCR_Z), BLACK, bevel=0.0)
round_y_edges(outer, 0.03)
round_y_edges(cutter, 0.022)
boo = outer.modifiers.new("cut", "BOOLEAN")
boo.object = cutter
boo.operation = "DIFFERENCE"
boo.solver = "EXACT"
apply_mods(outer)
bpy.data.objects.remove(cutter)
parts.remove(cutter)
b = outer.modifiers.new("soft", "BEVEL")
b.width = 0.004
b.segments = 2
b.limit_method = "ANGLE"
apply_mods(outer)
shade_smooth(outer)

# The CRT face: a rounded rectangle that bulges outward.
bm = bmesh.new()
nx, nz = 36, 28
grid = []
for j in range(nz + 1):
    row = []
    for i in range(nx + 1):
        u = i / nx * 2 - 1
        w = j / nz * 2 - 1
        su, sw = squircle(u, w, 5.0)
        bulge = 0.016 * (1 - min(1.0, (su * su * 0.9 + sw * sw * 0.9)))
        row.append(bm.verts.new((su * SCR_W / 2, -bulge, sw * SCR_H / 2)))
    grid.append(row)
for j in range(nz):
    for i in range(nx):
        bm.faces.new((grid[j][i], grid[j][i + 1], grid[j + 1][i + 1], grid[j + 1][i]))
bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
me = bpy.data.meshes.new("screen")
bm.to_mesh(me)
bm.free()
screen = link(bpy.data.objects.new("screen", me))
screen.location = (SCR_X, FRONT - 0.002, SCR_Z)
screen.data.materials.append(SCREEN)
for p in screen.data.polygons:
    if p.normal.y > 0:
        p.flip()
shade_smooth(screen, 80)

# Chrome script under the screen.
cu = bpy.data.curves.new("brand", "FONT")
cu.body = "Westbury"
cu.size = 0.034
cu.extrude = 0.0012
cu.bevel_depth = 0.0004
cu.align_x = "LEFT"
brand = link(bpy.data.objects.new("brand", cu))
brand.data.materials.append(CHROME)
brand.rotation_euler = (math.radians(90), 0, 0)
brand.location = (SCR_X - SCR_W / 2 - 0.005, FRONT - 0.001, Z0 + 0.034)
select_only(brand)
bpy.ops.object.convert(target="MESH")
brand.data.materials.clear()
brand.data.materials.append(CHROME)

# Control panel.
PX = 0.225
panel = new_box("panel", (0.125, 0.012, 0.415), (PX, FRONT - 0.0040, Z0 + 0.25), ALU, bevel=0.004)
# VHF channel dial with numbered ring and a big knurled knob.
dial = new_cyl("dial", 0.045, 0.008, (PX, FRONT - 0.0140, Z0 + 0.38), DIAL, verts=48, rot=(math.radians(90), 0, 0), bevel=0.0015)
store_planar_uv(dial, 0, 2, (0.0, 0.0), (0.09, 0.09))
new_cyl("vhf_knob", 0.024, 0.032, (PX, FRONT - 0.0320, Z0 + 0.38), BLACK, verts=40, rot=(math.radians(90), 0, 0), bevel=0.003, flutes=20)
new_box("vhf_pointer", (0.004, 0.006, 0.02), (PX, FRONT - 0.0490, Z0 + 0.39), ALU, bevel=0.0008)
# UHF knob, smaller.
new_cyl("uhf_ring", 0.03, 0.006, (PX, FRONT - 0.0120, Z0 + 0.275), CHROME, verts=40, rot=(math.radians(90), 0, 0), bevel=0.0012)
new_cyl("uhf_knob", 0.018, 0.026, (PX, FRONT - 0.0260, Z0 + 0.275), BLACK, verts=32, rot=(math.radians(90), 0, 0), bevel=0.002, flutes=16)
# Volume (pull switch), colour, tint.
for k, z in enumerate((0.195, 0.155, 0.115)):
    new_cyl("small_knob", 0.0115, 0.02, (PX - 0.02, FRONT - 0.0180, Z0 + z), BLACK, verts=24, rot=(math.radians(90), 0, 0), bevel=0.0015, flutes=12)
    new_box("knob_tick", (0.006, 0.004, 0.0015), (PX + 0.012, FRONT - 0.0110, Z0 + z), CHROME, bevel=0.0004)
new_cyl("pilot_lamp", 0.004, 0.006, (PX + 0.035, FRONT - 0.0120, Z0 + 0.195), LAMP, verts=12, rot=(math.radians(90), 0, 0))
# Speaker grille: slats in the bottom of the panel.
for i in range(9):
    new_box("slat", (0.105, 0.006, 0.0045), (PX, FRONT - 0.0110, Z0 + 0.045 + i * 0.0075), GRILLE, bevel=0.001)

# Back panel with vents and the maker's plate.
back = new_box("back", (W - 0.07, 0.01, H - 0.07), (0, D / 2 + 0.002, Z0 + H / 2), HARDBOARD, bevel=0.002)
for i in range(7):
    new_box("vent", (0.36, 0.012, 0.012), (0, D / 2 + 0.004, Z0 + H - 0.1 - i * 0.028), BLACK, bevel=0.002)
plate = new_box("plate", (0.16, 0.004, 0.04), (0.17, D / 2 + 0.009, Z0 + 0.1), PLATE, bevel=0.0)
store_planar_uv(plate, 0, 2, (0.0, 0.0), (0.16, 0.04))
# The plate is read from behind, so mirror it.
attr = plate.data.color_attributes["label_uv"]
for d_ in attr.data:
    c = d_.color
    d_.color = (1.0 - c[0], c[1], 0, 1)

# ---------------------------------------------------------------- on top

TOPS = Z0 + H
bm = bmesh.new()
bmesh.ops.create_circle(bm, cap_ends=True, segments=96, radius=0.14)
for v in bm.verts:
    a = math.atan2(v.co.y, v.co.x)
    rr = 0.13 + 0.01 * (0.5 + 0.5 * math.cos(a * 24))
    if v.co.length > 0.001:
        v.co.x = math.cos(a) * rr
        v.co.y = math.sin(a) * rr
bmesh.ops.triangulate(bm, faces=bm.faces)
ret = bmesh.ops.extrude_face_region(bm, geom=bm.faces[:])
for v in [e for e in ret["geom"] if isinstance(e, bmesh.types.BMVert)]:
    v.co.z += 0.002
me = bpy.data.meshes.new("doily")
bm.to_mesh(me)
bm.free()
doily = link(bpy.data.objects.new("doily", me))
doily.location = (-0.12, -0.04, TOPS - 0.0005)
doily.rotation_euler = (0, 0, 0.3)
doily.data.materials.append(DOILY)
shade_smooth(doily, 60)

# Rabbit ears and a UHF loop.
AX, AY = 0.16, 0.06
new_cyl("ant_base", 0.055, 0.03, (AX, AY, TOPS + 0.015), WALNUT, verts=32, r_top=0.04, bevel=0.006)
new_cyl("ant_cap", 0.03, 0.02, (AX, AY, TOPS + 0.038), CHROME, verts=24, bevel=0.004)
for side in (-1, 1):
    tilt_y = math.radians(32) * side
    tilt_x = math.radians(-14)
    d = Vector((math.sin(tilt_y), -math.sin(tilt_x), math.cos(tilt_y))).normalized()
    start = Vector((AX + side * 0.012, AY, TOPS + 0.045))
    seg = [(0.0042, 0.2), (0.0034, 0.2), (0.0026, 0.18)]
    t = 0.0
    for r, L in seg:
        c = start + d * (t + L / 2)
        rot = Vector((0, 0, 1)).rotation_difference(d).to_euler()
        new_cyl("ant_rod", r, L, tuple(c), CHROME, verts=10, rot=tuple(rot))
        t += L - 0.01
    tip = start + d * (t + 0.008)
    tip_obj = new_cyl("ant_tip", 0.006, 0.012, tuple(tip), CHROME, verts=12)
loop_me = bpy.data.meshes.new("loop")
bm = bmesh.new()
bmesh.ops.create_circle(bm, segments=40, radius=0.07)
me2 = bpy.data.meshes.new("loop_path")
bm.to_mesh(me2)
bm.free()
loop = bpy.data.objects.new("uhf_loop", me2)
bpy.context.collection.objects.link(loop)
loop.location = (AX, AY - 0.03, TOPS + 0.1)
loop.rotation_euler = (math.radians(90), 0, 0)
sk = loop.modifiers.new("skin", "SKIN")
for v in loop.data.skin_vertices[0].data:
    v.radius = (0.0028, 0.0028)
sub = loop.modifiers.new("sub", "SUBSURF")
sub.levels = 1
loop.data.materials.append(CHROME)
apply_mods(loop)
shade_smooth(loop, 80)
parts.append(loop)
new_box("loop_post", (0.006, 0.006, 0.04), (AX, AY - 0.03, TOPS + 0.02), CHROME, bevel=0.002)

# ---------------------------------------------------------------- join and unwrap

bpy.ops.object.select_all(action="DESELECT")
for p in parts:
    if p.name in bpy.data.objects:
        p.select_set(True)
bpy.context.view_layer.objects.active = cab
bpy.ops.object.convert(target="MESH")
bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
bpy.ops.object.join()
tv = bpy.context.view_layer.objects.active
tv.name = "Television"
# Origin at the bottom centre (the stand's feet sit at z = 0).
bpy.ops.object.origin_set(type="ORIGIN_CURSOR")
me = tv.data
for uv in list(me.uv_layers):
    me.uv_layers.remove(uv)
me.uv_layers.new(name="UVMap")
bpy.ops.object.mode_set(mode="EDIT")
bpy.ops.mesh.select_all(action="SELECT")
bpy.ops.uv.smart_project(angle_limit=math.radians(60), island_margin=0.004, area_weight=0.0, scale_to_bounds=True)
bpy.ops.uv.pack_islands(margin=0.004)
bpy.ops.object.mode_set(mode="OBJECT")
print("triangles:", sum(len(p.vertices) - 2 for p in me.polygons))

# ---------------------------------------------------------------- bake

scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.samples = SAMPLES
scene.cycles.use_denoising = False  # some Blender builds ship without OIDN; baking then fails silently
scene.render.bake.margin = 8
scene.render.bake.use_selected_to_active = False
select_only(tv)


def bake_image(name, colorspace):
    img = bpy.data.images.new(name, TEX_SIZE, TEX_SIZE, alpha=False, float_buffer=False)
    img.colorspace_settings.name = colorspace
    for info in BAKE.values():
        nt = info["mat"].node_tree
        node = nt.nodes.get("bake_target") or nt.nodes.new("ShaderNodeTexImage")
        node.name = "bake_target"
        node.image = img
        nt.nodes.active = node
    return img


def wire_emission(key):
    for info in BAKE.values():
        nt = info["mat"].node_tree
        em = nt.nodes.get("bake_emit") or nt.nodes.new("ShaderNodeEmission")
        em.name = "bake_emit"
        for l in list(em.inputs["Color"].links):
            nt.links.remove(l)
        nt.links.new(info[key], em.inputs["Color"])
        nt.links.new(em.outputs["Emission"], info["out"].inputs["Surface"])


def wire_bsdf():
    for info in BAKE.values():
        nt = info["mat"].node_tree
        nt.links.new(info["bsdf"].outputs["BSDF"], info["out"].inputs["Surface"])


def save(img, filename):
    import numpy as np
    a = np.empty(len(img.pixels), dtype=np.float32)
    img.pixels.foreach_get(a)
    print("  %s mean %.3f max %.3f" % (filename, a.mean(), a.max()))
    img.filepath_raw = os.path.join(OUT, filename)
    img.file_format = "PNG"
    img.save()
    print("saved", filename)


albedo = bake_image("tv_albedo", "sRGB")
wire_emission("albedo")
bpy.ops.object.bake(type="EMIT")
save(albedo, "tv_albedo.png")

rough = bake_image("tv_rough", "Non-Color")
wire_emission("rough")
bpy.ops.object.bake(type="EMIT")
metal = bake_image("tv_metal", "Non-Color")
wire_emission("metal")
bpy.ops.object.bake(type="EMIT")

normal = bake_image("tv_normal", "Non-Color")
wire_bsdf()
scene.cycles.samples = 8
bpy.ops.object.bake(type="NORMAL", normal_space="TANGENT")
save(normal, "tv_normal.png")

# Pack roughness and metallic into one ORM texture.
import numpy as np
n = TEX_SIZE * TEX_SIZE * 4
rp = np.empty(n, dtype=np.float32)
mp_ = np.empty(n, dtype=np.float32)
rough.pixels.foreach_get(rp)
metal.pixels.foreach_get(mp_)
px = np.ones(n, dtype=np.float32)
px[1::4] = rp[0::4]
px[2::4] = mp_[0::4]
orm = bpy.data.images.new("tv_orm", TEX_SIZE, TEX_SIZE, alpha=False)
orm.colorspace_settings.name = "Non-Color"
orm.pixels.foreach_set(px)
save(orm, "tv_orm.png")

# ---------------------------------------------------------------- export

for poly in me.polygons:
    poly.material_index = 0
me.materials.clear()
plain = bpy.data.materials.new("tv")
me.materials.append(plain)
select_only(tv)
bpy.ops.export_scene.gltf(filepath=os.path.join(OUT, "tv.glb"), export_format="GLB",
                          use_selection=True, export_materials="PLACEHOLDER", export_yup=True)
print("exported tv.glb")
