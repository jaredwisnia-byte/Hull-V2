"""Walks around a built prop and criticizes it.

    blender -b --factory-startup -P tools/critique.py -- PROP [VIEWS_FOLDER] [--out DIR]

1. Measures, by casting rays at the model from front, back, both sides and top:
   - silhouette match against the painted views (IoU per view), if a views folder
     with v_front.png etc. is given;
   - relief: how much real depth the front has (a fully flat front is a smell);
   - painted features: every round part detected in the painting (knobs, dials,
     buttons) is checked for real protrusion, and its depth compared with what the
     part rules say a real one should have;
   - floating or sunken parts: lowest point should sit on the floor (z = 0).
2. Renders a turnaround (8 angles plus 2 close-ups) to _critique.png for a person
   or Claude to look at, and writes _critique.json with the measurements and a list
   of complaints. Read docs/CRITIQUE.md for the review checklist.
"""
import json
import math
import os
import sys

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from propkit import part_rules  # noqa: E402

LIB = os.path.normpath(os.path.join(HERE, "..", "assets", "props"))
SRC = os.path.normpath(os.path.join(HERE, "..", "assets", "source_textures"))

args = sys.argv[sys.argv.index("--") + 1:]
name = args[0]
views_dir = os.path.join(SRC, args[1]) if len(args) > 1 and not args[1].startswith("--") else None
out_dir = args[args.index("--out") + 1] if "--out" in args else os.path.join(LIB, name)

bpy.ops.wm.read_factory_settings(use_empty=True)
d = os.path.join(LIB, name)
bpy.ops.import_scene.gltf(filepath=os.path.join(d, name + ".glb"))
objs = [o for o in bpy.data.objects if o.type == "MESH"]
dg = bpy.context.evaluated_depsgraph_get()
verts, polys = [], []
for o in objs:
    me = o.evaluated_get(dg).to_mesh()
    base = len(verts)
    verts += [o.matrix_world @ v.co for v in me.vertices]
    polys += [[base + i for i in p.vertices] for p in me.polygons]
tree = BVHTree.FromPolygons(verts, polys)
lo = Vector([min(v[i] for v in verts) for i in range(3)])
hi = Vector([max(v[i] for v in verts) for i in range(3)])
size = hi - lo
complaints, report = [], {"prop": name, "size_m": [round(s, 3) for s in size]}

# Rays: for each view, a grid of rays travelling into the object. Blender axes:
# front is -Y (camera at -Y looking +Y), right is +X, top is +Z.
VIEWS = {
    "front": (Vector((0, 1, 0)), lambda u, v: Vector((lo.x + u * size.x, lo.y - 1, lo.z + v * size.z))),
    "back": (Vector((0, -1, 0)), lambda u, v: Vector((hi.x - u * size.x, hi.y + 1, lo.z + v * size.z))),
    "right": (Vector((-1, 0, 0)), lambda u, v: Vector((hi.x + 1, lo.y + u * size.y, lo.z + v * size.z))),
    "left": (Vector((1, 0, 0)), lambda u, v: Vector((lo.x - 1, hi.y - u * size.y, lo.z + v * size.z))),
    "top": (Vector((0, 0, -1)), lambda u, v: Vector((lo.x + u * size.x, hi.y - v * size.y, hi.z + 1))),
}


def cast(view, n=160):
    direction, origin = VIEWS[view]
    aspect = {"front": size.z / size.x, "back": size.z / size.x, "right": size.z / size.y,
              "left": size.z / size.y, "top": size.y / size.x}[view]
    w, h = n, max(8, int(n * aspect))
    depth = np.full((h, w), np.nan)
    for j in range(h):
        for i in range(w):
            hit = tree.ray_cast(origin((i + 0.5) / w, 1 - (j + 0.5) / h), direction, 10)
            if hit[0] is not None:
                depth[j, i] = hit[3] - 1.0
    return depth


PAINT_ONLY = set()
try:
    from props import hull_props
    if name in hull_props.HULLS:
        PAINT_ONLY = set(hull_props.HULLS[name][3].get("paint_only", ()))
except Exception:
    pass


def silhouette_iou(depth, view):
    if not views_dir or view in PAINT_ONLY:
        return None
    p = os.path.join(views_dir, "v_%s.png" % view)
    if not os.path.exists(p):
        return None
    from propkit.hull import silhouette
    m, _ = silhouette(p)
    ref = np.asarray(Image.fromarray(m.astype(np.uint8) * 255).resize((depth.shape[1], depth.shape[0]))) > 127
    got = ~np.isnan(depth)
    # Parts that stick out beyond the painted outline in rows where the outline
    # is otherwise matched (knobs a sheet forgot to draw side-on) are noted, not
    # counted as the body's shape being wrong.
    extra = got & ~ref
    rows_ok = ref.any(1)
    small = ndimage.label(extra)[0]
    sizes = np.bincount(small.ravel())
    bumps = np.isin(small, [i for i, n in enumerate(sizes) if i and n < got.sum() * 0.03])
    core = got & ~(bumps & rows_ok[:, None])
    inter = (ref & core).sum()
    union = (ref | core).sum()
    if bumps.any():
        report.setdefault("parts_beyond_painted_outline", []).append(view)
    return round(float(inter / max(union, 1)), 3)


from scipy import ndimage  # noqa: E402

depths = {}
for v in VIEWS:
    depths[v] = cast(v)
    iou = silhouette_iou(depths[v], v)
    report.setdefault("silhouette_iou", {})[v] = iou
    if iou is not None and iou < 0.85:
        complaints.append("%s silhouette only matches the painting %.0f%%: shape is off from that side." % (v, iou * 100))

# Relief of the front: depth spread inside the silhouette.
fd = depths["front"]
inside = fd[~np.isnan(fd)]
relief_mm = float(np.percentile(inside, 95) - np.percentile(inside, 5)) * 1000 if inside.size else 0
report["front_relief_mm"] = round(relief_mm, 1)
if relief_mm < 5:
    complaints.append("The front is flat (%.1f mm of relief): painted details have no depth." % relief_mm)

# Painted round features: do they protrude, and by a believable amount?
feats = []
if views_dir and os.path.exists(os.path.join(views_dir, "v_front.png")):
    from propkit.hull import detect_circles, silhouette
    m, img = silhouette(os.path.join(views_dir, "v_front.png"))
    fh, fw = m.shape
    for cx, cy, r in detect_circles(img):
        diam = 2 * r / fw * size.x
        part = part_rules.classify_circle(diam)
        if part is None:
            continue
        want = part_rules.depth_for(part, diam)
        hh, ww = fd.shape
        i, j = int(cx / fw * ww), int(cy / fh * hh)
        rr = max(1, int(r / fw * ww * 0.5))
        centre = np.nanmin(fd[max(0, j - rr):j + rr + 1, max(0, i - rr):i + rr + 1])
        ring = fd[max(0, j - 3 * rr):j + 3 * rr + 1, max(0, i - 3 * rr):i + 3 * rr + 1]
        around = np.nanpercentile(ring, 80) if np.isfinite(ring).any() else centre
        got = float(around - centre)
        f = {"part": part, "diameter_mm": round(diam * 1000, 1), "protrudes_mm": round(got * 1000, 1),
             "expected_mm": round(want * 1000, 1)}
        feats.append(f)
        if got < want * 0.4:
            complaints.append("%s (%.0f mm across) is painted flat: it stands out %.0f mm, a real one about %.0f mm."
                              % (part, diam * 1000, got * 1000, want * 1000))
        elif got > want * 2.0:
            complaints.append("%s (%.0f mm) sticks out %.0f mm, far more than a real one (~%.0f mm)."
                              % (part, diam * 1000, got * 1000, want * 1000))
report["painted_features"] = feats

# Sits on the floor?
report["lowest_z_m"] = round(lo.z, 4)
if abs(lo.z) > 0.01:
    complaints.append("Lowest point is at z = %.3f m: it %s." % (lo.z, "floats" if lo.z > 0 else "sinks into the floor"))

# Holes seen from the front: empty pixels fully surrounded by surface.
from scipy import ndimage  # noqa: E402
filled = ndimage.binary_fill_holes(~np.isnan(fd))
holes = int((filled & np.isnan(fd)).sum())
report["front_holes_px"] = holes
if holes > fd.size * 0.002:
    complaints.append("There are see-through holes in the front (%d px)." % holes)

report["complaints"] = complaints

# Turnaround renders for eyeballing.
sc = bpy.context.scene
sc.render.engine = "CYCLES"
sc.cycles.samples = 12
sc.cycles.use_denoising = False
sc.view_settings.view_transform = "Standard"
sc.render.resolution_x = sc.render.resolution_y = 300
m = bpy.data.materials.new("crit")
m.use_nodes = True
nt = m.node_tree
b = nt.nodes["Principled BSDF"]
for fn, cs, sock in ((name + "_albedo.png", "sRGB", "Base Color"),):
    t = nt.nodes.new("ShaderNodeTexImage")
    t.image = bpy.data.images.load(os.path.join(d, fn))
    nt.links.new(t.outputs[0], b.inputs[sock])
nm = nt.nodes.new("ShaderNodeNormalMap")
t = nt.nodes.new("ShaderNodeTexImage")
t.image = bpy.data.images.load(os.path.join(d, name + "_normal.png"))
t.image.colorspace_settings.name = "Non-Color"
nt.links.new(t.outputs[0], nm.inputs["Color"])
nt.links.new(nm.outputs[0], b.inputs["Normal"])
for o in objs:
    o.data.materials.clear()
    o.data.materials.append(m)
w = bpy.data.worlds.new("w")
sc.world = w
w.use_nodes = True
w.node_tree.nodes["Background"].inputs["Color"].default_value = (0.12, 0.13, 0.15, 1)
w.node_tree.nodes["Background"].inputs["Strength"].default_value = 3.0   # fill: every side readable
key = bpy.data.objects.new("key", bpy.data.lights.new("key", "SUN"))
key.data.energy = 3.0
key.rotation_euler = (math.radians(50), 0, math.radians(-35))
sc.collection.objects.link(key)
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
sc.collection.objects.link(cam)
sc.camera = cam
centre = (lo + hi) / 2
radius = size.length / 2
tiles = []
shots = [(a, 18, 1.0) for a in range(0, 360, 45)] + [(-20, 8, 0.45), (200, 30, 0.5)]
for k, (az, el, zoom) in enumerate(shots):
    a, e = math.radians(az), math.radians(el)
    dist = radius / math.tan(cam.data.angle / 2) * 1.1 * zoom
    target = centre + (Vector((0, -size.y * 0.3, size.z * 0.1)) if zoom < 1 else Vector())
    cam.location = target + Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e))) * dist
    cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
    # The key light turns with the camera (over the viewer's shoulder), so the turnaround
    # compares the object's sides, not how far each one is from a fixed light.
    key.rotation_euler = (math.radians(50), 0, a - math.radians(35))
    p = os.path.join(out_dir, "_crit_%d.png" % k)
    sc.render.filepath = p
    bpy.ops.render.render(write_still=True)
    tiles.append(p)
sheet = Image.new("RGB", (5 * 300, 2 * 300 + 30 + 18 * (len(complaints) + 1)), (18, 18, 20))
dr = ImageDraw.Draw(sheet)
f = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
for k, p in enumerate(tiles):
    sheet.paste(Image.open(p), ((k % 5) * 300, (k // 5) * 300))
    os.remove(p)
y = 610
dr.text((8, y), "%s: %s" % (name, "no complaints" if not complaints else "%d complaints" % len(complaints)), font=f, fill=(240, 220, 170))
for c in complaints:
    y += 18
    dr.text((8, y), "- " + c, font=f, fill=(230, 150, 130))
sheet.save(os.path.join(out_dir, "_critique.png"))
with open(os.path.join(out_dir, "_critique.json"), "w") as fh:
    json.dump(report, fh, indent=1)
print("CRITIQUE", json.dumps(report))
