"""Material presets for prop recipes.

Every preset routes through `weathered()`: lighter chipped edges, dark grime in
crevices, dust on upward faces. That shared look is what makes props from
different recipes sit together. `BAKE` records the sockets the baker needs.
"""

import os

import bpy

BAKE = {}
_CACHE = {}


def reset():
    BAKE.clear()
    _CACHE.clear()


def _new(name):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return m, nt, bsdf, out


def _sock(nt, v):
    if isinstance(v, (int, float)):
        n = nt.nodes.new("ShaderNodeValue")
        n.outputs[0].default_value = v
        return n.outputs[0]
    if isinstance(v, tuple):
        n = nt.nodes.new("ShaderNodeRGB")
        n.outputs[0].default_value = v if len(v) == 4 else (*v, 1.0)
        return n.outputs[0]
    return v


def m_(nt, op, a, b=None, clamp=True):
    n = nt.nodes.new("ShaderNodeMath")
    n.operation = op
    n.use_clamp = clamp
    for i, v in enumerate((a, b)):
        if v is None:
            continue
        if isinstance(v, (int, float)):
            n.inputs[i].default_value = v
        else:
            nt.links.new(v, n.inputs[i])
    return n.outputs[0]


def mix(nt, fac, a, b):
    n = nt.nodes.new("ShaderNodeMix")
    n.data_type = "RGBA"
    if isinstance(fac, (int, float)):
        n.inputs["Factor"].default_value = fac
    else:
        nt.links.new(fac, n.inputs["Factor"])
    for sock, val in ((n.inputs[6], a), (n.inputs[7], b)):
        if isinstance(val, tuple):
            sock.default_value = val if len(val) == 4 else (*val, 1.0)
        else:
            nt.links.new(val, sock)
    return n.outputs[2]


def ramp(nt, fac, stops):
    n = nt.nodes.new("ShaderNodeValToRGB")
    cr = n.color_ramp
    cr.elements[0].position, cr.elements[0].color = stops[0][0], (*stops[0][1], 1)
    cr.elements[1].position, cr.elements[1].color = stops[-1][0], (*stops[-1][1], 1)
    for pos, col in stops[1:-1]:
        cr.elements.new(pos).color = (*col, 1)
    nt.links.new(fac, n.inputs["Fac"])
    return n.outputs["Color"]


def coords(nt, scale=(1, 1, 1)):
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = scale
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    return mp.outputs["Vector"]


def noise(nt, scale, vec=None, detail=4.0):
    n = nt.nodes.new("ShaderNodeTexNoise")
    n.inputs["Scale"].default_value = scale
    n.inputs["Detail"].default_value = detail
    if vec is not None:
        nt.links.new(vec, n.inputs["Vector"])
    return n.outputs["Fac"]


def ao(nt, dist, inside=False):
    n = nt.nodes.new("ShaderNodeAmbientOcclusion")
    n.inputs["Distance"].default_value = dist
    n.inside = inside
    n.samples = 16
    n.only_local = True
    return n.outputs["AO"]


def axis_part(nt, axis):
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    nt.links.new(tc.outputs["Object"], sep.inputs[0])
    return sep.outputs[axis]


def weathered(nt, col, edge=0.25, grime=0.45, dust=0.2, edge_col=(0.75, 0.68, 0.58)):
    col = _sock(nt, col)
    e = m_(nt, "SUBTRACT", 1.0, ao(nt, 0.006, inside=True))
    e = m_(nt, "MULTIPLY", m_(nt, "GREATER_THAN", e, 0.35), e)  # only real edges, not AO noise
    e = m_(nt, "POWER", e, 1.5)
    e = m_(nt, "MULTIPLY", e, m_(nt, "GREATER_THAN", noise(nt, 60.0, detail=6.0), 0.48))
    col = mix(nt, m_(nt, "MULTIPLY", e, edge * 4.0), col, edge_col)
    c = m_(nt, "SUBTRACT", 1.0, ao(nt, 0.04))
    c = m_(nt, "MULTIPLY", m_(nt, "GREATER_THAN", c, 0.12), c)
    col = mix(nt, m_(nt, "MULTIPLY", c, grime * 1.6), col, (0.05, 0.04, 0.03))
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(geo.outputs["Normal"], sep.inputs[0])
    up = m_(nt, "GREATER_THAN", sep.outputs["Z"], 0.8)
    col = mix(nt, m_(nt, "MULTIPLY", m_(nt, "MULTIPLY", up, noise(nt, 9.0)), dust), col, (0.55, 0.53, 0.5))
    return col


def bump(nt, height, strength, dist=0.002):
    b = nt.nodes.new("ShaderNodeBump")
    b.inputs["Strength"].default_value = strength
    b.inputs["Distance"].default_value = dist
    nt.links.new(height, b.inputs["Height"])
    return b.outputs["Normal"]


def register(name, m, bsdf, out, albedo, rough, metal, normal=None):
    nt = m.node_tree
    albedo, rough, metal = _sock(nt, albedo), _sock(nt, rough), _sock(nt, metal)
    nt.links.new(albedo, bsdf.inputs["Base Color"])
    nt.links.new(rough, bsdf.inputs["Roughness"])
    nt.links.new(metal, bsdf.inputs["Metallic"])
    if normal is not None:
        nt.links.new(normal, bsdf.inputs["Normal"])
    BAKE[name] = {"albedo": albedo, "rough": rough, "metal": metal, "out": out, "bsdf": bsdf, "mat": m}
    _CACHE[name] = m
    return m


def _cached(name):
    return _CACHE.get(name)


# ------------------------------------------------------------------ presets

WOODS = {
    "walnut": [(0.04, 0.019, 0.01), (0.09, 0.045, 0.021), (0.14, 0.073, 0.034), (0.18, 0.095, 0.045)],
    "oak": [(0.22, 0.13, 0.06), (0.36, 0.22, 0.11), (0.46, 0.3, 0.16), (0.52, 0.36, 0.2)],
    "maple": [(0.42, 0.27, 0.14), (0.55, 0.38, 0.21), (0.63, 0.46, 0.28), (0.7, 0.53, 0.34)],
    "pine": [(0.4, 0.26, 0.12), (0.56, 0.39, 0.2), (0.66, 0.5, 0.3), (0.72, 0.57, 0.36)],
    "mahogany": [(0.09, 0.03, 0.015), (0.18, 0.06, 0.03), (0.26, 0.1, 0.05), (0.32, 0.13, 0.07)],
    "floor": [(0.12, 0.06, 0.03), (0.22, 0.12, 0.06), (0.3, 0.17, 0.09), (0.36, 0.21, 0.11)],
}


def wood(tone="walnut", axis="Z", scale=8.0, dust=0.15, edge=0.3, gloss=0.42, name=None):
    """Wood grain. axis is the direction the grain runs across (Z = horizontal grain)."""
    name = name or "wood_%s_%s" % (tone, axis)
    if _cached(name):
        return _cached(name)
    m, nt, bsdf, out = _new(name)
    sc = {"X": (9, 1, 1), "Y": (1, 9, 1), "Z": (1, 1, 9)}[axis]
    v = coords(nt, sc)
    w = nt.nodes.new("ShaderNodeTexWave")
    w.wave_type = "BANDS"
    w.bands_direction = axis
    w.inputs["Scale"].default_value = scale
    w.inputs["Distortion"].default_value = 5.0
    w.inputs["Detail"].default_value = 4.0
    nt.links.new(v, w.inputs["Vector"])
    g = m_(nt, "ADD", m_(nt, "MULTIPLY", w.outputs["Fac"], 0.75), m_(nt, "MULTIPLY", noise(nt, 140, v, 3), 0.12))
    st = WOODS[tone]
    base = ramp(nt, g, [(0.0, st[0]), (0.45, st[1]), (0.8, st[2]), (1.0, st[3])])
    return register(name, m, bsdf, out, weathered(nt, base, edge, 0.5, dust), gloss, 0.0, bump(nt, g, 0.25))


def metal(col, rough=0.35, brushed=False, grime=0.5, name=None):
    name = name or "metal_%.2f_%.2f_%.2f_%d" % (col[0], col[1], col[2], brushed)
    if _cached(name):
        return _cached(name)
    m, nt, bsdf, out = _new(name)
    r, normal = rough, None
    if brushed:
        n = noise(nt, 3.0, coords(nt, (2, 400, 400)))
        r = m_(nt, "ADD", rough - 0.08, m_(nt, "MULTIPLY", n, 0.16))
        normal = bump(nt, n, 0.08)
    return register(name, m, bsdf, out, weathered(nt, col, 0.0, grime, 0.2), r, 1.0, normal)


def chrome():
    return metal((0.85, 0.85, 0.86), 0.16, grime=0.7, name="chrome")


def brass():
    return metal((0.72, 0.52, 0.22), 0.3, grime=0.8, name="brass")


def iron(col=(0.09, 0.09, 0.095)):
    return plain(col, 0.6, edge=0.15, grime=0.4, metal_v=0.6, name="iron")


def plain(col, rough=0.5, edge=0.15, grime=0.4, dust=0.2, metal_v=0.0, name=None):
    """Plastic, enamel, rubber, ceramic: a solid colour with the shared wear."""
    name = name or "plain_%.2f_%.2f_%.2f_%.2f" % (col[0], col[1], col[2], rough)
    if _cached(name):
        return _cached(name)
    m, nt, bsdf, out = _new(name)
    return register(name, m, bsdf, out, weathered(nt, col, edge, grime, dust), rough, metal_v)


def paint(col, under=(0.55, 0.5, 0.42), chips=0.5, rough=0.55, name=None):
    """Painted wood or metal, chipped at the edges to show the coat underneath."""
    name = name or "paint_%.2f_%.2f_%.2f" % col
    if _cached(name):
        return _cached(name)
    m, nt, bsdf, out = _new(name)
    blot = m_(nt, "GREATER_THAN", noise(nt, 18.0, detail=8.0), 0.7)
    base = mix(nt, m_(nt, "MULTIPLY", blot, chips * 0.3), col, under)
    return register(name, m, bsdf, out, weathered(nt, base, 0.35 * chips + 0.1, 0.5, 0.25, under), rough, 0.0)


def fabric(col, col2=(0.2, 0.15, 0.1), pattern="plain", scale=10.0, rough=0.95, dust=0.15, name=None):
    """Upholstery and textiles. Patterns: plain, plaid, stripes, floral, zigzag, tweed, chenille."""
    name = name or "fabric_%s_%.2f_%.2f_%.2f" % (pattern, col[0], col[1], col[2])
    if _cached(name):
        return _cached(name)
    m, nt, bsdf, out = _new(name)
    v = coords(nt, (scale, scale, scale))
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(v, sep.inputs[0])
    weave = noise(nt, 400.0, detail=2.0)
    if pattern == "plaid":
        a = m_(nt, "GREATER_THAN", m_(nt, "SINE", sep.outputs["X"], clamp=False), 0.3)
        b = m_(nt, "GREATER_THAN", m_(nt, "SINE", m_(nt, "ADD", sep.outputs["Z"], sep.outputs["Y"], clamp=False), clamp=False), 0.3)
        thin = m_(nt, "GREATER_THAN", m_(nt, "SINE", m_(nt, "MULTIPLY", sep.outputs["X"], 3.0, clamp=False), clamp=False), 0.9)
        f = m_(nt, "MULTIPLY", m_(nt, "ADD", a, b), 0.5)
        base = mix(nt, f, col, col2)
        base = mix(nt, m_(nt, "MULTIPLY", thin, 0.6), base, (0.75, 0.62, 0.35))
    elif pattern == "stripes":
        base = mix(nt, m_(nt, "GREATER_THAN", m_(nt, "SINE", sep.outputs["X"], clamp=False), 0.2), col, col2)
    elif pattern == "floral":
        vor = nt.nodes.new("ShaderNodeTexVoronoi")
        vor.inputs["Scale"].default_value = 1.0
        nt.links.new(v, vor.inputs["Vector"])
        base = mix(nt, m_(nt, "LESS_THAN", vor.outputs["Distance"], 0.28), col, col2)
    elif pattern == "zigzag":
        z = m_(nt, "SINE", m_(nt, "ADD", m_(nt, "MULTIPLY", sep.outputs["Z"], 2.0, clamp=False),
                             m_(nt, "ABSOLUTE", m_(nt, "SINE", sep.outputs["X"], clamp=False), clamp=False), clamp=False), clamp=False)
        base = ramp(nt, m_(nt, "MULTIPLY", m_(nt, "ADD", z, 1.0, clamp=False), 0.5),
                    [(0.0, col[:3]), (0.5, col2[:3]), (0.75, (0.85, 0.7, 0.4)), (1.0, col[:3])])
    elif pattern in ("tweed", "chenille"):
        base = mix(nt, m_(nt, "MULTIPLY", noise(nt, 120.0, detail=8.0), 0.7), col, col2)
    else:
        base = _sock(nt, col)
    base = mix(nt, m_(nt, "MULTIPLY", weave, 0.18), base, (0.0, 0.0, 0.0))
    return register(name, m, bsdf, out, weathered(nt, base, 0.05, 0.5, dust), rough, 0.0, bump(nt, weave, 0.15))


def glass(tint=(0.2, 0.35, 0.25), name=None):
    """Bottle and jar glass, baked as an opaque painted glass (Long Dark style)."""
    name = name or "glass_%.2f_%.2f_%.2f" % tint
    if _cached(name):
        return _cached(name)
    m, nt, bsdf, out = _new(name)
    z = axis_part(nt, "Z")
    hl = m_(nt, "MULTIPLY", m_(nt, "GREATER_THAN", noise(nt, 2.0), 0.6), 0.5)
    base = mix(nt, hl, tint, tuple(min(1.0, c * 2.2 + 0.25) for c in tint))
    return register(name, m, bsdf, out, weathered(nt, base, 0.0, 0.3, 0.3), 0.08, 0.0)


def image(path, rough=0.5, grime=0.35, edge=0.0, name=None, extension="EXTEND"):
    """A printed surface (label, box art, record sleeve, poster) mapped through the
    'label_uv' attribute that core.planar_uv / core.wrap_uv store."""
    name = name or "img_" + os.path.basename(path)
    if _cached(name):
        return _cached(name)
    m, nt, bsdf, out = _new(name)
    attr = nt.nodes.new("ShaderNodeAttribute")
    attr.attribute_type = "GEOMETRY"
    attr.attribute_name = "label_uv"
    img = nt.nodes.new("ShaderNodeTexImage")
    img.image = bpy.data.images.load(path, check_existing=True)
    img.extension = extension
    nt.links.new(attr.outputs["Vector"], img.inputs["Vector"])
    return register(name, m, bsdf, out, weathered(nt, img.outputs["Color"], edge, grime, 0.1), rough, 0.0)


def paper(col=(0.86, 0.83, 0.74), name=None):
    return plain(col, 0.9, edge=0.0, grime=0.3, dust=0.25, name=name or "paper_%.2f" % col[0])


def cardboard():
    if _cached("cardboard"):
        return _cached("cardboard")
    m, nt, bsdf, out = _new("cardboard")
    n = noise(nt, 30.0, detail=6)
    base = mix(nt, m_(nt, "MULTIPLY", n, 0.4), (0.5, 0.36, 0.2), (0.36, 0.25, 0.13))
    return register("cardboard", m, bsdf, out, weathered(nt, base, 0.15, 0.5, 0.25), 0.9, 0.0, bump(nt, n, 0.1))


SURFACES = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "assets", "surfaces"))


def painted(name, repeat_m=None, rough=0.6, edge=0.2, grime=0.4, dust=0.15, metal_v=0.0):
    """A painted surface tile (assets/surfaces/<name>.png, made by tools/make_tiles.py)
    wrapped onto any shape with box projection, plus the shared weathering. The same
    tiles dress walls and floors in the game, so props and rooms share one look."""
    key = "painted_%s_%s" % (name, repeat_m)
    if _cached(key):
        return _cached(key)
    import json
    cat = json.load(open(os.path.join(SURFACES, "..", "..", "data", "surfaces.json")))
    rep = repeat_m or float(cat.get(name, {}).get("repeat_m", 0.6))
    m, nt, bsdf, out = _new(key)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (1 / rep, 1 / rep, 1 / rep)
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    img = nt.nodes.new("ShaderNodeTexImage")
    fn = os.path.basename(cat.get(name, {}).get("file", name + ".jpg"))
    img.image = bpy.data.images.load(os.path.join(SURFACES, fn), check_existing=True)
    img.projection = "BOX"
    img.projection_blend = 0.25
    nt.links.new(mp.outputs["Vector"], img.inputs["Vector"])
    col = weathered(nt, img.outputs["Color"], edge, grime, dust)
    return register(key, m, bsdf, out, col, rough, metal_v, bump(nt, img.outputs["Color"], 0.12))
