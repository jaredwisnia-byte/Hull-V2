"""Visual hull: a 3D model from orthographic painted views (front, side, top...).

Each view's outline is cut out of a block of voxels; what survives every view is the
object. The surface is extracted with marching cubes, lightly smoothed, decimated,
and every face is painted from the view it faces. One call turns a sheet of views
into a textured prop, so any object drawn in front/side/top views needs no modelling.

    from propkit.hull import hull_prop
    hull_prop({"front": "front.png", "right": "right.png", "top": "top.png",
               "back": "back.png", "left": "left.png"}, height=0.5)

View conventions (as on a typical sheet): front = seen from the front; right = seen
from the object's right side, so the front is on the image's LEFT; left = seen from the
left side, front on the RIGHT; back = seen from behind; top = seen from above with the
front at the BOTTOM of the image. Only front and one side are required.
"""
import math

import bmesh
import bpy
import numpy as np
from PIL import Image
from scipy import ndimage
from skimage.measure import marching_cubes
from skimage.morphology import convex_hull_image
from skimage.feature import canny
from skimage.transform import hough_circle, hough_circle_peaks

from . import part_rules
from .core import cyl

from . import mats as M
from .core import apply_mods, link, smooth


def silhouette(path, thresh=30, convex=False):
    """Mask of the object in a view: differs from the border colour, biggest connected
    shape plus small shapes just beside it (legs, feet), holes filled.
    Returns (mask, cropped colour image)."""
    im = Image.open(path).convert("RGB")
    a = np.asarray(im).astype(np.int32)
    border = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])
    bg = np.median(border, axis=0)
    m = np.abs(a - bg).sum(2) > thresh
    m = ndimage.binary_closing(m, iterations=2)
    lab, n = ndimage.label(m)
    if n == 0:
        raise ValueError("no object found in " + path)
    sizes = ndimage.sum(m, lab, range(1, n + 1))
    main = int(np.argmax(sizes)) + 1
    keep = lab == main
    # Legs, feet and knobs often sit apart from the body behind a dark gap in the painting:
    # keep small shapes that touch the body's span and lie within a short gap of it.
    ys_, xs_ = np.nonzero(keep)
    my0, my1, mx0, mx1 = ys_.min(), ys_.max(), xs_.min(), xs_.max()
    gap = max(4, int(0.06 * (my1 - my0)))
    for i, sl in enumerate(ndimage.find_objects(lab), 1):
        if i == main or sizes[i - 1] < 0.002 * sizes[main - 1]:
            continue
        y0_, y1_, x0_, x1_ = sl[0].start, sl[0].stop - 1, sl[1].start, sl[1].stop - 1
        near_y = y0_ <= my1 + gap and y1_ >= my0 - gap
        near_x = x0_ <= mx1 + gap and x1_ >= mx0 - gap
        if near_x and near_y:
            keep |= lab == i
    m = keep
    # Dark parts of an object (screens, back panels) can match a dark sheet
    # background. Treat anything bounded by the object both along its row and
    # its column as solid; outer notches (between legs, under a lip) stay open.
    rows = np.zeros_like(m)
    cols = np.zeros_like(m)
    for i in np.nonzero(m.any(1))[0]:
        xs = np.nonzero(m[i])[0]
        rows[i, xs[0]:xs[-1] + 1] = True
    for j in np.nonzero(m.any(0))[0]:
        ys = np.nonzero(m[:, j])[0]
        cols[ys[0]:ys[-1] + 1, j] = True
    m = ndimage.binary_fill_holes(m | (rows & cols))
    if convex:
        m = convex_hull_image(m)
    ys, xs = np.nonzero(m)
    box = (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1)
    return m[box[1]:box[3], box[0]:box[2]], im.crop(box)


def detect_circles(img, min_score=0.5):
    """Round features in a painted view (knobs, dials, buttons): Hough circles on
    edges. Returns [(cx, cy, r)] in pixels, non-overlapping. Radii below 2.5% of the
    view's width are edge noise; where circles overlap the larger one wins (a knob's
    painted highlights make small false circles inside it)."""
    g = np.asarray(img.convert("L")).astype(float) / 255
    e = canny(g, sigma=1.5)
    w = g.shape[1]
    radii = np.arange(max(4, int(w * 0.025)), max(8, int(w * 0.09)))
    acc = hough_circle(e, radii)
    sc, cx, cy, r = hough_circle_peaks(acc, radii, total_num_peaks=16, min_xdistance=6, min_ydistance=6)
    cands = [(int(x), int(y), int(rr)) for s_, x, y, rr in zip(sc, cx, cy, r) if s_ >= min_score]
    cands.sort(key=lambda c: -c[2])
    out = []
    for x, y, rr in cands:
        if any((x - a) ** 2 + (y - b) ** 2 < (rr + c) ** 2 for a, b, c in out):
            continue
        out.append((x, y, rr))
    return out


def _sample(mask, u, v):
    """mask sampled at normalised coords u (0 left..1 right), v (0 top..1 bottom)."""
    h, w = mask.shape
    ix = np.clip((u * (w - 1)).round().astype(int), 0, w - 1)
    iy = np.clip((v * (h - 1)).round().astype(int), 0, h - 1)
    return mask[iy, ix]


HULL_REPORT = {}     # what the last hull_prop call carved with blades


def hull_prop(views, height, res=110, smooth_iters=4, decimate=0.35, rough=0.5, name="hull",
              convex=False, paint_only=(), features=True, sil_override=None, depth_m=None, grime=0.25,
              paint=True, width_m=None, blades=False, voxel_hook=None, mesh_hook=None, revolve=True, blur=0.7):
    """convex: fill each outline to its convex shape (boxy objects; dark areas can't
    punch holes). paint_only: views used for texture but not trusted to carve (e.g. a
    dark back panel on a dark sheet). width_m: the real width (views painted out of
    proportion are stretched to it). blades: carve hollows no outline shows (a seat between
    arms) from where the views' painted edges meet (propkit/blades.py). voxel_hook(keep, views,
    W, D, H) -> keep: a last say over the voxels before meshing (propkit/hull_assembly.py).
    mesh_hook(obj): edits the dense mesh before smoothing/decimation (propkit/edge_guide.py).
    blur: voxel smoothing before meshing (voxels); large gently sloped bodies (cars) need ~1.5 or their
    hoods and sides come out as terraces that catch stripes of paint.
    revolve: a part whose top view is round (an ellipse once handles/spouts are set aside) is built
    as a lathe shape, every slice an ellipse sized by the front and side outlines (propkit/revolve.py)."""
    # sil_override: {view: (mask, image)} from a part map, when the sheet set provides exact outlines.
    sil = dict(sil_override) if sil_override else {k: silhouette(p, convex=convex) for k, p in views.items()}
    # Raw (non-convex) side outlines keep small bumps such as knobs seen side-on.
    raw_sides = {k: v for k, v in sil.items() if k in ("right", "left")} if sil_override else \
        {k: silhouette(p) for k, p in views.items() if k in ("right", "left")}
    carve = {k: v for k, v in sil.items() if k not in paint_only}
    fm, fim = sil["front"]
    side_key = "right" if "right" in sil else "left"
    sm, _ = sil[side_key]
    H = height
    W = width_m or H * fm.shape[1] / fm.shape[0]
    D = depth_m or H * sm.shape[1] / sm.shape[0]
    nx = res
    ny = max(8, int(res * D / W))
    nz = max(8, int(res * H / W))
    x = (np.arange(nx) + 0.5) / nx  # 0 = left (-X), 1 = right (+X)
    y = (np.arange(ny) + 0.5) / ny  # 0 = front (-Y), 1 = back (+Y)
    z = (np.arange(nz) + 0.5) / nz  # 0 = bottom, 1 = top
    X, Yy, Z = np.meshgrid(x, y, z, indexing="ij")
    keep = _sample(fm, X, 1 - Z)
    if "back" in carve:
        keep &= _sample(carve["back"][0], 1 - X, 1 - Z)
    if "right" in carve:
        keep &= _sample(carve["right"][0], Yy, 1 - Z)
    if "left" in carve:
        keep &= _sample(carve["left"][0], 1 - Yy, 1 - Z)
    if "top" in carve:
        keep &= _sample(carve["top"][0], X, 1 - Yy)
    if blades:
        from . import blades as _blades
        HULL_REPORT.clear()
        keep = _blades.carve(keep, carve, HULL_REPORT)
    if revolve:
        from . import revolve as _revolve
        HULL_REPORT.pop("revolve", None)
        keep = _revolve.voxel_hook(HULL_REPORT)(keep, carve, W, D, H)
    if voxel_hook is not None:
        keep = voxel_hook(keep, carve, W, D, H)
    vol = np.pad(keep.astype(np.float32), 1)
    vol = ndimage.gaussian_filter(vol, blur)
    verts, faces, _, _ = marching_cubes(vol, 0.5)
    verts -= 1.0
    sx, sy, sz = W / nx, D / ny, H / nz
    bm = bmesh.new()
    bv = [bm.verts.new(((vx + 0.5) * sx - W / 2, (vy + 0.5) * sy - D / 2, (vz + 0.5) * sz)) for vx, vy, vz in verts]
    for a, b, c in faces:
        try:
            bm.faces.new((bv[a], bv[c], bv[b]))
        except ValueError:
            pass
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    obj = link(bpy.data.objects.new(name, me))
    if mesh_hook is not None:
        mesh_hook(obj)
    sm_mod = obj.modifiers.new("smooth", "SMOOTH")
    sm_mod.iterations = smooth_iters
    sm_mod.factor = 0.5
    dec = obj.modifiers.new("dec", "DECIMATE")
    dec.ratio = decimate
    apply_mods(obj)
    if not paint:   # texturing.project() colours it later (blended views, occlusion)
        obj["hull_frame"] = [W, D, H]
        smooth(obj, 50)
        return obj
    # Paint each face from the view it faces.
    order = ["front", "back", "right", "left", "top"]
    mats_ = {}
    for k in order:
        if k in sil:
            path = "/tmp/_hull_%s_%s.png" % (name, k)
            sil[k][1].save(path)
            mats_[k] = M.image(path, rough, grime, 0.05, name="%s_%s" % (name, k))
            obj.data.materials.append(mats_[k])
    slot = {k: i for i, k in enumerate([k for k in order if k in mats_])}
    attr = obj.data.color_attributes.new("label_uv", "FLOAT_COLOR", "CORNER")
    me = obj.data
    for poly in me.polygons:
        n = poly.normal
        cands = {"front": -n.y, "back": n.y, "right": n.x, "left": -n.x, "top": n.z}
        k = max((c for c in cands if c in slot), key=lambda c: cands[c])
        poly.material_index = slot[k]
        for li in poly.loop_indices:
            v = me.vertices[me.loops[li].vertex_index].co
            u_, w_ = (v.x + W / 2) / W, v.z / H
            if k == "back":
                u_ = 1 - u_
            elif k == "right":
                u_ = (v.y + D / 2) / D
            elif k == "left":
                u_ = 1 - (v.y + D / 2) / D
            elif k == "top":
                w_ = (v.y + D / 2) / D  # top view: front at the image bottom (v = 0)
            attr.data[li].color = (u_, w_, 0, 1)
    smooth(obj, 50)
    if features:
        add_features(sil, keep, W, D, H, mats_.get("front"), name, raw_sides)
    return obj


def side_evidence(sil, v, D):
    """How far something sticks out of the front at height v (0 top..1 bottom),
    read from a side view: the silhouette's front edge on that row versus the
    body's typical front edge. None if no side view."""
    for key, front_left in (("right", True), ("left", False)):
        if key not in sil:
            continue
        m = sil[key][0]
        h, w = m.shape
        def front_col(row):
            xs = np.nonzero(m[row])[0]
            if len(xs) == 0:
                return None
            return xs[0] if front_left else w - 1 - xs[-1]
        cols = [front_col(r) for r in range(int(h * 0.1), int(h * 0.9))]
        cols = [c for c in cols if c is not None]
        if not cols:
            return None
        body = float(np.median(cols))
        r0 = int(v * (h - 1))
        band = [front_col(r) for r in range(max(0, r0 - 2), min(h, r0 + 3))]
        band = [c for c in band if c is not None]
        if not band:
            return None
        return max(0.0, (body - min(band)) / w * D)
    return None


def add_features(sil, keep, W, D, H, front_mat, name, raw_sides=None):
    """Gives painted round parts on the front view real depth, using part_rules:
    each detected knob becomes a ridged cylinder standing proud of the surface by
    the amount a real knob of that size would, its cap showing the painted knob."""
    if front_mat is None:
        return []
    fm, fim = sil["front"]
    fh, fw = fm.shape
    nx, ny, nz = keep.shape
    made = []
    for cx, cy, r in detect_circles(fim):
        d = 2 * r / fw * W
        part = part_rules.classify_circle(d)
        if part is None:
            continue
        rule = part_rules.RULES[part]
        depth = part_rules.depth_for(part, d)
        source = "rule"
        seen = side_evidence(raw_sides or sil, cy / fh, D)
        if seen is not None and seen >= rule["min_depth"]:  # a distinct bump, not edge noise
            # The drawing shows how far it sticks out: trust it, within reason.
            depth = min(max(seen, rule["min_depth"]), rule["max_depth"])
            source = "drawing"
        x = (cx / fw - 0.5) * W
        z = (1 - cy / fh) * H
        ix = min(nx - 1, max(0, int(cx / fw * nx)))
        iz = min(nz - 1, max(0, int((1 - cy / fh) * nz)))
        col = np.nonzero(keep[ix, :, iz])[0]
        if len(col) == 0:
            continue
        y_front = -D / 2 + col[0] / ny * D
        k = cyl(d / 2 * 0.95, depth, (x, y_front - depth / 2 + 0.001, z), front_mat, 32,
                (math.radians(90), 0, 0), bevel=d * 0.08, flutes=rule["flutes"])
        attr = k.data.color_attributes.new("label_uv", "FLOAT_COLOR", "CORNER")
        for li, loop in enumerate(k.data.loops):
            v = k.data.vertices[loop.vertex_index].co  # local: cylinder axis is Z
            u_ = (cx + v.x / (d / 2) * r) / fw
            w_ = 1 - (cy - v.y / (d / 2) * r) / fh
            attr.data[li].color = (u_, w_, 0, 1)
        made.append({"part": part, "diameter_mm": round(d * 1000, 1), "depth_mm": round(depth * 1000, 1),
                     "at": [round(x, 3), round(z, 3)], "from": source})
    print("FEATURES", name, made)
    return made


def polygon_hull(masks, W, D, H, name="phull", bevel_frac=0.015, tolerance=1.0):
    """The visual hull built exactly: each view's outline (holes included) extruded into a prism,
    the prisms intersected. Flat faces, straight slopes, sharp edges, no voxel staircase; then a
    small bevel so nothing is razor sharp. masks: {view: bool array cropped to the object},
    conventions as hull_prop (right view: front at the left; top view: front at the bottom)."""
    from skimage.measure import approximate_polygon, find_contours
    L = 4 * max(W, D, H)

    def to2d(view, r, c, h, w):
        if view == "front":
            return (c / w - 0.5) * W, (1 - r / h) * H
        if view == "back":
            return (0.5 - c / w) * W, (1 - r / h) * H
        if view == "right":
            return (c / w - 0.5) * D, (1 - r / h) * H
        if view == "left":
            return (0.5 - c / w) * D, (1 - r / h) * H
        return (c / w - 0.5) * W, (0.5 - r / h) * D            # top

    def to3d(view, a, b, t):
        if view in ("front", "back"):
            return (a, t, b)
        if view in ("right", "left"):
            return (t, a, b)
        return (a, b, t)

    def prism(view, poly, nm):
        bm = bmesh.new()
        lo = [bm.verts.new(to3d(view, a, b, -L)) for a, b in poly]
        hi = [bm.verts.new(to3d(view, a, b, L)) for a, b in poly]
        n = len(poly)
        for j in range(n):
            bm.faces.new((lo[j], lo[(j + 1) % n], hi[(j + 1) % n], hi[j]))
        bm.faces.new(list(reversed(lo)))
        bm.faces.new(hi)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        me = bpy.data.meshes.new(nm)
        bm.to_mesh(me)
        bm.free()
        o = bpy.data.objects.new(nm, me)
        bpy.context.collection.objects.link(o)
        return o

    def boolean(target, cutter, op):
        md = target.modifiers.new("b", "BOOLEAN")
        md.operation = op
        md.solver = "EXACT"
        md.object = cutter
        bpy.ops.object.select_all(action="DESELECT")
        target.select_set(True)
        bpy.context.view_layer.objects.active = target
        bpy.ops.object.modifier_apply(modifier=md.name)
        bpy.data.objects.remove(cutter)

    result = None
    for view in ("front", "right", "top", "back", "left"):
        if view not in masks:
            continue
        m = masks[view]
        h, w = m.shape
        cs = find_contours(np.pad(m, 1).astype(float), 0.5)
        cs = [approximate_polygon(c, tolerance=tolerance)[:-1] for c in cs]
        cs = [c for c in cs if len(c) >= 3]
        if not cs:
            continue
        area = lambda c: 0.5 * abs(sum(c[i][0] * c[(i + 1) % len(c)][1] - c[(i + 1) % len(c)][0] * c[i][1] for i in range(len(c))))
        cs.sort(key=area, reverse=True)
        outer = prism(view, [to2d(view, r - 1, c - 1, h, w) for r, c in cs[0]], "%s_%s" % (name, view))
        for hole in cs[1:]:                                   # see-through gaps (a handset arch)
            if area(hole) > 0.002 * h * w:
                boolean(outer, prism(view, [to2d(view, r - 1, c - 1, h, w) for r, c in hole], "hole"), "DIFFERENCE")
        if result is None:
            result = outer
        else:
            boolean(result, outer, "INTERSECT")
    result.name = name
    core_link = __import__("propkit.core", fromlist=["link"]) if False else None
    from .core import PARTS
    PARTS.append(result)
    bv = result.modifiers.new("bevel", "BEVEL")
    bv.width = bevel_frac * min(W, D, H)
    bv.segments = 2
    bv.limit_method = "ANGLE"
    apply_mods(result)
    result["hull_frame"] = [W, D, H]
    smooth(result, 35)
    return result


def loft_from_views(front, top, W, D, H, name="loft", stations=64, sides=28, exponent=2.6):
    """A long, smooth part (handset, handle bar, rail) lofted along x. At every station the
    front view gives its top and bottom, the top view its front and back; the cross-section is a
    superellipse fitted into that box (exponent 2 = ellipse, higher = squarer, 2.6 = moulded
    plastic). Masks are in the object's view frames (front: cols = x, rows = z; top: cols = x,
    rows = y with the front at the bottom). Smooth by construction: no voxel or facet steps."""
    hf, wf = front.shape
    ht, wt = top.shape
    cols = np.nonzero(front.any(0))[0]
    if len(cols) < 4:
        return None
    x0, x1 = cols.min(), cols.max() + 1
    rings = []
    for s in range(stations + 1):
        c = x0 + (x1 - x0) * (0.02 + 0.96 * s / stations)
        cf = min(wf - 1, int(c))
        rows = np.nonzero(front[:, cf])[0]
        ct = min(wt - 1, int(c / wf * wt))
        trow = np.nonzero(top[:, ct])[0]
        if not len(rows) or not len(trow):
            continue
        x = (c / wf - 0.5) * W
        z_top, z_bot = (1 - rows.min() / hf) * H, (1 - (rows.max() + 1) / hf) * H
        y_back, y_front = (0.5 - trow.min() / ht) * D, (0.5 - (trow.max() + 1) / ht) * D
        yc, zc, ry, rz = (y_back + y_front) / 2, (z_top + z_bot) / 2, (y_back - y_front) / 2, (z_top - z_bot) / 2
        ring = []
        for k in range(sides):
            t = 2 * math.pi * k / sides
            ct_, st_ = math.cos(t), math.sin(t)
            ring.append((x, yc + ry * math.copysign(abs(ct_) ** (2 / exponent), ct_),
                         zc + rz * math.copysign(abs(st_) ** (2 / exponent), st_)))
        rings.append(ring)
    if len(rings) < 3:
        return None
    bm = bmesh.new()
    vr = [[bm.verts.new(p) for p in ring] for ring in rings]
    for a, b in zip(vr, vr[1:]):
        for k in range(sides):
            bm.faces.new((a[k], a[(k + 1) % sides], b[(k + 1) % sides], b[k]))
    for ring, rev in ((vr[0], True), (vr[-1], False)):          # rounded end caps
        c = bm.verts.new(tuple(sum(v.co[i] for v in ring) / sides for i in range(3)))
        for k in range(sides):
            f = (ring[k], ring[(k + 1) % sides], c)
            bm.faces.new(tuple(reversed(f)) if rev else f)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    obj = link(bpy.data.objects.new(name, me))
    obj["hull_frame"] = [W, D, H]
    smooth(obj, 60)
    return obj
