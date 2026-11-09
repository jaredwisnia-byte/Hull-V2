"""Relief: the surface inside an outline, read from the painting (2.5D carving: flutes, beads, leaves).

A silhouette says nothing about what the surface does inside it. A painting does, but ambiguously:
darkness means either occlusion (a crease, a groove: light cannot get in) or a surface turned away from
the light (one side of a raised bead). This module separates the two:

1. Outlines from occlusion. "Cavity" = how much darker a point is than its neighbourhood. It traces
   every crease between carved parts, so the creases split the view into regions (a bead, a leaf, a
   flute channel, the strip between two flutes).
2. A shape per region from its outline: a dome (or dish) whose height grows with the distance from the
   region's edge, up to a share of the region's own half width (a bead comes out near a hemisphere; a
   long strip a rounded rib). The creases themselves become shallow V-grooves.
3. Raised or sunk from the shading. A raised dome and a sunk dish have the same outline but opposite
   shading: the dome is lit on the side facing the light, the dish on the side away from it. Each region's
   painted shading is regressed on its dome's slopes; the regions agree on one light direction (taken as
   coming from above, as painters light), and each region is raised if its shading matches the dome, sunk
   if it matches the dish, and left flat (paint only) if the shading says neither clearly.
4. The check: the finished relief, lit by that light, is compared with the painting's shading (correlation
   over the carved area). A relief that contradicts the painting scores near zero or below.

Heights are in the view's pixels until scaled by the view's metres per pixel; every relief is capped at a
share of the object's thinner side. hook(...) displaces a dense hull mesh along its smoothed normals, each
point blending the elevation views by how squarely it faces them (as texturing.project blends paint).
"""
import numpy as np
from PIL import Image
from scipy import ndimage

from .hull import silhouette

CAVITY_SIGMA = 6.0      # px: the neighbourhood a crease is darker than
CREASE = 0.35           # share of the 95th-percentile cavity that counts as a crease
DOME = 0.6              # dome height / region half width (1.0 = hemisphere)
BASE_R = 0.09           # a region whose half width exceeds this share of the view's width is base surface
MIN_R = 1.5             # px: narrower regions are left to the crease grooves
BOUND = 0.3             # mean crease strength round a region for it to count as carved
MERGE = 0.22            # neighbours split by a line weaker than this (mean crease strength) are one region
FIT = 0.12              # share of its shading a dome or dish must explain
MAX_R_PX = 8.0          # px: domes stop rising past this half width (no pillows on broad leaves)
CONFIDENT = 0.25        # |cos| between a region's shading vector and the light below which it stays flat
CREASE_DEPTH = 0.5      # crease groove depth, in px at full cavity
MAX_RELIEF = 0.07       # relief never exceeds this share of the object's thinner side
HIGH_TRIS = 800000       # the dense copy baked into the normal map is simplified to this
POWER = 4.0             # view blending sharpness (as texturing.project)
ELEVATIONS = ("front", "back", "right", "left")


def _lum(img, m):
    a = np.asarray(img.convert("RGB")).astype(float) / 255
    L = a @ [0.299, 0.587, 0.114]
    return np.where(m, L, 0)


def _local_mean(x, m, sigma):
    return ndimage.gaussian_filter(np.where(m, x, 0), sigma) / np.maximum(ndimage.gaussian_filter(m.astype(float), sigma), 1e-3)


def _regions(m, cn):
    """Split the view into carved regions along crease ridges: watershed of the cavity map from markers at
    the middles of the uncreased areas, so an outline need not be closed to separate two leaves."""
    from skimage.segmentation import watershed
    from skimage.feature import peak_local_max
    inner = ndimage.binary_erosion(m, iterations=2)
    open_ = inner & (cn <= CREASE)
    d = ndimage.distance_transform_edt(open_)
    pk = peak_local_max(d, min_distance=4, threshold_abs=MIN_R, labels=ndimage.label(open_)[0])
    mk = np.zeros(m.shape, int)
    mk[tuple(pk.T)] = np.arange(1, len(pk) + 1)
    lab = watershed(cn, mk, mask=inner, watershed_line=True)
    # merge neighbours split by a weak line (one flute cut into pieces along its length; a leaf's painted
    # streaks): keep a dividing line only where it is a real crease on average
    line = (lab == 0) & inner
    ys, xs = np.nonzero(line)
    pairs = {}
    hh, ww = lab.shape
    for y, x in zip(ys, xs):
        nb = lab[max(0, y - 1):y + 2, max(0, x - 1):x + 2]
        u = np.unique(nb[nb > 0])
        for i in range(len(u)):
            for j in range(i + 1, len(u)):
                key = (u[i], u[j])
                a, c = pairs.get(key, (0.0, 0))
                pairs[key] = (a + cn[y, x], c + 1)
    parent = np.arange(lab.max() + 1)

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    for (a, b), (tot, cnt) in pairs.items():
        if tot / cnt < MERGE:
            parent[find(a)] = find(b)
    roots = np.array([find(i) for i in range(len(parent))])
    lab = roots[lab]
    lab[lab == roots[0]] = 0
    # dissolve weak line pixels into their region
    weak = (lab == 0) & inner & (cn < MERGE)
    if weak.any():
        idx = ndimage.distance_transform_edt(lab == 0, return_distances=False, return_indices=True)
        lab[weak] = lab[tuple(i[weak] for i in idx)]
    return lab


def _region_votes(L, m, cn, lab):
    """Per region: dome shape, its shading vector (regression on the dome's slopes) and boundary bands."""
    hp = L - _local_mean(L, m, 8.0)                       # shading detail, without the paint's broad tone
    W = m.shape[1]
    out = []
    for i, sl in enumerate(ndimage.find_objects(lab), 1):
        if sl is None:
            continue
        sl = tuple(slice(max(0, q.start - 3), q.stop + 3) for q in sl)
        r = lab[sl] == i
        d = ndimage.distance_transform_edt(np.pad(r, 1))[1:-1, 1:-1]
        R = float(d.max())
        if R < MIN_R or R > BASE_R * W:
            continue
        t = np.clip(d / R, 0, 1)
        dome = DOME * min(R, MAX_R_PX) * np.sqrt(1 - (1 - t) ** 2)
        gy, gx = np.gradient(dome)
        inside = r & (d > 1)
        if inside.sum() < 6:
            continue
        A = np.c_[-gx[inside], -gy[inside]]               # shading of z = dome: -hx lx - hy ly (+ lz)
        b = hp[sl][inside]
        coef, *_ = np.linalg.lstsq(A, b - b.mean(), rcond=None)
        res = b - b.mean() - A @ coef
        r2 = 1 - float(res.var()) / max(float(b.var()), 1e-12)
        ring = ndimage.binary_dilation(r, iterations=2) & ~r
        bound = float(cn[sl][ring].mean()) if ring.any() else 0.0
        # carved, not just painted: creases all round it, and shading a dome (or dish) explains
        if bound < BOUND or r2 < FIT:
            continue
        out.append({"sl": sl, "r": r, "dome": dome, "coef": coef, "w": float(inside.sum()), "R": R, "r2": r2})
    return out, hp


def light_of(votes):
    """One light direction (image x right, y down) from many regions' shading vectors: their principal
    axis, signed so the light comes from above (as painters light)."""
    M = sum(v["w"] * np.outer(v["coef"], v["coef"]) for v in votes)
    l = np.linalg.eigh(M)[1][:, -1]
    if l[1] > 0 or (abs(l[1]) < 0.2 and l[0] > 0):
        l = -l
    return l


def view_relief(path, view=None, light=None):
    """Height map (px, + out of the surface) for one painted view, over its silhouette crop; and a report.
    light: a shared light direction (image coords) from all the sheet's views, else this view's own."""
    m, img = silhouette(path)
    L = _lum(img, m)
    cav = np.clip(_local_mean(L, m, CAVITY_SIGMA) - L, 0, None)
    cav[~m] = 0
    scale = np.percentile(cav[m], 95) + 1e-6
    cn = np.clip(cav / scale, 0, 1)
    lab = _regions(m, cn)
    votes, hp = _region_votes(L, m, cn, lab)
    if not votes:
        return np.zeros_like(L), {"view": view, "regions": 0}
    l = np.asarray(light) if light is not None else light_of(votes)
    h = np.zeros_like(L)
    h_up = np.zeros_like(L)
    raised = sunk = flat = 0
    off = np.array([l[1], l[0]])                          # (row, col) step towards the light
    for v in votes:
        sl, r, dome = v["sl"], v["r"], v["dome"]
        n = np.linalg.norm(v["coef"])
        cos = float(v["coef"] @ l / n) if n > 0 else 0.0
        # cast shadow: a raised region throws its shadow outside its edge away from the light; a sunk one
        # has the shadow inside, under its edge nearest the light
        ring_out = ndimage.binary_dilation(r, iterations=2) & ~r
        ring_in = r & ~ndimage.binary_erosion(r, iterations=2)
        yy, xx = np.nonzero(r)
        cy, cx = yy.mean(), xx.mean()
        def side(mask, towards):
            ys, xs = np.nonzero(mask)
            proj = (ys - cy) * off[0] + (xs - cx) * off[1]
            sel = proj > 0 if towards else proj < 0
            return float(cn[sl][ys[sel], xs[sel]].mean()) if sel.any() else 0.0
        cast = side(ring_out, False) - side(ring_in, True)
        vote = 0.5 * cos + 0.5 * np.clip(cast * 2, -1, 1)
        h_up[sl][r] = dome[r]
        if abs(vote) < CONFIDENT:
            flat += 1
            continue
        s = 1.0 if vote > 0 else -1.0
        raised += s > 0
        sunk += s < 0
        h[sl][r] = s * dome[r]
    h -= CREASE_DEPTH * cn * 2
    h = ndimage.gaussian_filter(h, 0.7)
    h[~m] = 0
    carved = m & (np.abs(h) > 0.2)

    def match(hh):
        gy, gx = np.gradient(hh)
        pred = -gx * l[0] - gy * l[1]
        return float(np.corrcoef(pred[carved], hp[carved])[0, 1]) if carved.sum() > 20 else 0.0
    return h, {"view": view, "regions": len(votes), "raised": int(raised), "sunk": int(sunk), "flat": int(flat),
               "light_dir": [round(float(l[0]), 2), round(float(-l[1]), 2)],
               "shading_match": round(match(h), 3),
               "all_raised_match": round(match(ndimage.gaussian_filter(h_up - CREASE_DEPTH * cn * 2, 0.7)), 3),
               "grooves_only_match": round(match(ndimage.gaussian_filter(-CREASE_DEPTH * cn * 2, 0.7)), 3),
               "carved_share": round(float(carved.sum() / max(m.sum(), 1)), 3)}


def shared_light(views):
    """The painter's light, from all elevation views' regions together."""
    votes = []
    for k, p in views.items():
        if k not in ELEVATIONS:
            continue
        m, img = silhouette(p)
        L = _lum(img, m)
        cav = np.clip(_local_mean(L, m, CAVITY_SIGMA) - L, 0, None)
        cn = np.clip(cav / (np.percentile(cav[m], 95) + 1e-6), 0, 1)
        votes += _region_votes(L, m, cn, _regions(m, cn))[0]
    return light_of(votes)


def _smoothed_normals(verts, faces, iters=4):
    """Vertex normals from face areas, then averaged over neighbours (vectorised with bincount: a dense hull
    has ~1M vertices)."""
    nv = len(verts)
    v = verts[faces]
    fn = np.cross(v[:, 1] - v[:, 0], v[:, 2] - v[:, 0])
    n = np.stack([sum(np.bincount(faces[:, j], fn[:, c], nv) for j in range(3)) for c in range(3)], 1)
    a = np.r_[faces[:, 0], faces[:, 1], faces[:, 2]]
    b = np.r_[faces[:, 1], faces[:, 2], faces[:, 0]]
    for _ in range(iters):
        n = n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
        n = n + np.stack([np.bincount(a, n[b, c], nv) + np.bincount(b, n[a, c], nv) for c in range(3)], 1)
    return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)


def _sample(img, u, v):
    """Bilinear sample of a crop-sized map at (u, v) in [0,1], v measured up from the bottom."""
    hh, ww = img.shape
    x = np.clip(u * ww - 0.5, 0, ww - 1)
    y = np.clip((1 - v) * hh - 0.5, 0, hh - 1)
    return ndimage.map_coordinates(img, [y, x], order=1, mode="nearest")


def hook(views, W, D, H, report):
    """A hull mesh_hook: displace the dense mesh by the views' relief. Fills report (per view and totals)."""
    from .texturing import _uv
    maps, mpp = {}, {}
    light = shared_light(views)
    report["light_dir"] = [round(float(light[0]), 2), round(float(-light[1]), 2)]
    for k in ELEVATIONS:
        if k in views:
            h, rep = view_relief(views[k], k, light)
            maps[k] = h
            mpp[k] = (W if k in ("front", "back") else D) / h.shape[1]
            report.setdefault("views", {})[k] = rep
    cap = MAX_RELIEF * min(W, D)
    dirs = {"front": (0, -1, 0), "back": (0, 1, 0), "right": (1, 0, 0), "left": (-1, 0, 0)}

    def apply(obj):
        me = obj.data
        nv = len(me.vertices)
        co = np.empty(nv * 3)
        me.vertices.foreach_get("co", co)
        co = co.reshape(-1, 3)
        me.calc_loop_triangles()
        faces = np.empty(len(me.loop_triangles) * 3, dtype=np.int64)
        me.loop_triangles.foreach_get("vertices", faces)
        faces = faces.reshape(-1, 3)
        n = _smoothed_normals(co, faces)
        wsum = np.zeros(nv)
        hsum = np.zeros(nv)
        for k, hm in maps.items():
            f = np.clip(n @ np.array(dirs[k]), 0, None) ** POWER
            sel = f > 1e-3
            u, v = _uv(k, co[sel].T, W, D, H)
            hsum[sel] += f[sel] * _sample(hm, u, v) * mpp[k]
            wsum[sel] += f[sel]
        disp = np.clip(np.where(wsum > 0, hsum / np.maximum(wsum, 1e-9), 0), -cap, cap)
        co += n * disp[:, None]
        me.vertices.foreach_set("co", co.ravel())
        me.update()
        # the dense relief, kept for baking its detail into the normal map (bake.finish bakes
        # "<name>__high" onto the simplified mesh): geometry keeps what the triangle budget can hold
        import bpy
        hi = bpy.data.objects.new(obj.name.split(".")[0] + "__high", me.copy())
        bpy.context.scene.collection.objects.link(hi)
        tris = len(me.polygons)
        if tris > HIGH_TRIS:
            d = hi.modifiers.new("dec", "DECIMATE")
            d.ratio = HIGH_TRIS / tris
            bpy.ops.object.select_all(action="DESELECT")
            hi.select_set(True)
            bpy.context.view_layer.objects.active = hi
            bpy.ops.object.modifier_apply(modifier="dec")
        report["high_tris"] = len(hi.data.polygons)
        report["displaced_mm"] = {"max_out": round(float(disp.max()) * 1000, 2), "max_in": round(float(-disp.min()) * 1000, 2),
                                  "cap": round(cap * 1000, 2), "vertices": int(nv)}
    return apply


def maps_preview(views, out_png):
    """The relief maps side by side (grey = flat, light = raised, dark = sunk), for checking by eye."""
    tiles = []
    light = shared_light(views)
    for k in ELEVATIONS:
        if k in views:
            h, _ = view_relief(views[k], k, light)
            s = max(np.abs(h).max(), 1e-6)
            tiles.append(((0.5 + 0.5 * h / s) * 255).astype(np.uint8))
    hh = max(t.shape[0] for t in tiles)
    out = np.full((hh, sum(t.shape[1] + 8 for t in tiles)), 40, np.uint8)
    x = 0
    for t in tiles:
        out[:t.shape[0], x:x + t.shape[1]] = t
        x += t.shape[1] + 8
    Image.fromarray(out).save(out_png)
