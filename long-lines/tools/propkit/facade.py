"""Facade line: a building from one painted front elevation.

    split_sheet(sheet) -> crops of every whole elevation on a facade atlas sheet
    analyse(png)       -> trimmed elevation, window rectangles, storeys, wall colour
    facade_prop(png)   -> the building in the current scene, ready for bake.finish

The elevation is the front. Windows are found where the painting is dark and
rectangular, and are recessed into the wall so they read as openings, not stickers.
A cornice is extruded along the top. Sides and back take the exterior wall surface
(assets/surfaces/ext_*) whose colour is nearest the painted wall, the roof is tar.
Everything is measured from the picture; the only assumption is a storey height.
"""
import json
import os

import numpy as np
from PIL import Image

STOREY_M = 3.4        # typical lower-Manhattan loft / tenement storey, floor to floor
BG_MAX = 52           # sheet background is near-black; anything brighter is drawing
SURF = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "surfaces.json"))


def _bg(a):
    return (a[..., :3].max(-1) < BG_MAX)


def _runs(mask):
    out, s = [], None
    for i, x in enumerate(mask):
        if x and s is None:
            s = i
        if not x and s is not None:
            out.append((s, i))
            s = None
    if s is not None:
        out.append((s, len(mask)))
    return out


def _xy_cut(bg, x0, y0, x1, y1, out, depth=0):
    """Recursive gutter cut: split a region wherever a full-height column band or
    full-width row band is background, until nothing splits. Atlas sheets are laid
    out on such gutters; dark shopfronts inside a building never span it fully."""
    reg = bg[y0:y1, x0:x1]
    if reg.size == 0:
        return
    for axis in (0, 1):  # 0: columns (vertical gutters), 1: rows
        full = reg.mean(axis) > 0.985
        pieces = [(a, b) for a, b in _runs(~full) if b - a > 3]
        if len(pieces) > 1 or (pieces and (pieces[0][0] > 0 or pieces[0][1] < len(full))):
            for a, b in pieces:
                if axis == 0:
                    _xy_cut(bg, x0 + a, y0, x0 + b, y1, out, depth + 1)
                else:
                    _xy_cut(bg, x0, y0 + a, x1, y0 + b, out, depth + 1)
            return
    out.append((x0, y0, x1, y1))


def split_sheet(sheet, min_h=0.35, min_area=0.04):
    """Whole elevations on an atlas sheet: leaves of the gutter cut that are tall
    and big enough to be a building (windows, doors and swatches are smaller).
    Returns [(x0, y0, x1, y1)] in reading order."""
    a = np.asarray(Image.open(sheet).convert("RGB"))
    H, W = a.shape[:2]
    leaves = []
    _xy_cut(_bg(a), 0, 0, W, H, leaves)
    boxes = [b for b in leaves if (b[3] - b[1]) >= min_h * H and (b[3] - b[1]) * (b[2] - b[0]) >= min_area * H * W]
    return sorted(boxes, key=lambda b: (round(b[1] / (0.2 * H)), b[0]))


def trim(im):
    """Strips background margins from each edge until a row/column is mostly
    drawing, so narrow things above the roofline (water towers, chimneys) go too."""
    a = np.asarray(im.convert("RGB"))
    fg = ~_bg(a)
    r, c = fg.mean(1), fg.mean(0)
    t, b, l, rr = 0, len(r), 0, len(c)
    while t < b - 1 and r[t] < 0.6:
        t += 1
    while b > t + 1 and r[b - 1] < 0.6:
        b -= 1
    while l < rr - 1 and c[l] < 0.6:
        l += 1
    while rr > l + 1 and c[rr - 1] < 0.6:
        rr -= 1
    return im.crop((l, t, rr, b))


def _period(profile, lo, hi):
    x = profile - profile.mean()
    n = len(x)
    ac = np.correlate(x, x, "full")[n - 1:]
    lo, hi = max(2, int(lo)), min(n - 1, int(hi))
    if hi <= lo:
        return None
    return lo + int(np.argmax(ac[lo:hi]))


def _lattice(profile, lo, hi, start, stop, min_w=0.3):
    """Window positions along one axis from the repeat: period by autocorrelation,
    opening width and phase from the profile folded over one period."""
    P = _period(profile[start:stop], lo, hi)
    if not P:
        return []
    seg = profile[start:stop]
    fold = np.array([seg[k::P].mean() for k in range(P)])
    k = max(1, P // 8)  # circular smoothing: the opening, not its frame line
    fold = np.convolve(np.concatenate([fold[-k:], fold, fold[:k]]), np.ones(2 * k + 1) / (2 * k + 1), "valid")
    k0 = int(np.argmax(fold))
    above = fold > fold.mean()
    a = b = k0
    while b - a + 1 < P and above[(a - 1) % P]:
        a -= 1
    while b - a + 1 < P and above[(b + 1) % P]:
        b += 1
    w = int(np.clip(b - a + 1, min_w * P, 0.7 * P))
    a = int((a + b) / 2 - w / 2)
    out = []
    pos = start + a % P - P
    while pos < stop:
        if pos >= start and pos + w <= stop:
            out.append((pos, pos + w))
        pos += P
    return out


def windows(im):
    """Windows from the facade's regularity. Openings are darker than the wall
    around them and repeat at a fixed spacing across and up the building, so the
    spacing comes from autocorrelation and the opening from the profile folded over
    one period. Cells that are not actually dark (signs, blind bays) are dropped,
    and the shopfront storey is left as painted. Returns (u0, v0, u1, v1) fractions,
    v up. Robust to fire escapes, curtains and paint loss, which defeat blob finding."""
    from scipy import ndimage
    g = np.asarray(im.convert("L")).astype(np.float32) / 255.0
    H, W = g.shape
    D = np.clip(ndimage.gaussian_filter(g, sigma=max(4, W / 14)) - g, 0, None)
    top = int(0.05 * H)
    rows_p = D[:, int(0.05 * W):int(0.95 * W)].mean(1)
    Py = _period(rows_p[top:int(0.8 * H)], 0.07 * H, 0.34 * H)
    if not Py:
        return [], 3
    n_storeys = int(np.clip(round((H - 1.15 * Py) / Py) + 1, 2, 14))
    ground = H - int(1.15 * Py)                      # the shopfront storey
    cols = _lattice(D[top:ground].mean(0), 0.07 * W, 0.5 * W, 0, W)
    if not cols:
        return [], n_storeys
    cm = np.zeros(W, bool)
    for c0, c1 in cols:
        cm[c0:c1] = True
    rows = _lattice(D[:, cm].mean(1), 0.07 * H, 0.34 * H, top, ground, min_w=0.5)
    inside = np.zeros((H, W), bool)
    for r0, r1 in rows:
        for c0, c1 in cols:
            inside[r0:r1, c0:c1] = True
    band = np.zeros((H, W), bool)
    band[top:ground] = True
    wall = D[band & ~inside].mean() if (band & ~inside).any() else 1.0
    if not rows or D[inside].mean() < 1.8 * wall:
        return [], n_storeys  # not confident: leave the facade painted rather than cut holes in brick
    out = []
    for r0, r1 in rows:
        for c0, c1 in cols:
            cell = D[r0:r1, c0:c1]
            if cell.size and cell.mean() > 1.3 * wall and 0.5 < (r1 - r0) / max(1, c1 - c0) < 4.5:
                out.append((c0 / W, 1 - r1 / H, c1 / W, 1 - r0 / H))
    return out, n_storeys


def wall_colour(im, wins):
    a = np.asarray(im.convert("RGB")).astype(np.float32)
    H, W = a.shape[:2]
    keep = np.ones((H, W), bool)
    for u0, v0, u1, v1 in wins:
        keep[int((1 - v1) * H):int((1 - v0) * H) + 1, int(u0 * W):int(u1 * W) + 1] = False
    px = a[keep]
    lum = px.mean(1)
    return np.median(px[lum >= np.percentile(lum, 40)], 0)  # windows, shadows, fire escapes are the dark 40%


def nearest_surface(col, prefix="ext_"):
    cat = json.load(open(SURF))
    root = os.path.dirname(os.path.dirname(SURF))
    best, bd = None, 1e9
    for k, v in cat.items():
        if not k.startswith(prefix) or "corrugated" in k:
            continue
        p = os.path.join(root, v["file"].replace("res://", ""))
        m = np.asarray(Image.open(p).convert("RGB").resize((32, 32))).reshape(-1, 3).mean(0)
        d = float(((m - col) ** 2).sum())
        if d < bd:
            best, bd = k, d
    return best


def analyse(png, storeys_override=None):
    im = trim(Image.open(png))
    wins, n = windows(im)
    n = storeys_override or n
    col = wall_colour(im, wins)
    return {"image": im, "windows": wins, "storeys": n, "wall_rgb": [round(float(c)) for c in col],
            "side": nearest_surface(col)}


def facade_prop(png, name="facade", storeys=None, depth_m=12.0, recess_m=0.22, side=None,
                roof="ext_concrete_dark"):
    """Builds the building (front at y = 0 facing -y, standing on z = 0)."""
    import bpy
    from . import core, mats
    info = analyse(png, storeys)
    im = info["image"]
    trimmed = os.path.join(os.path.dirname(png), "facade_trim.png")
    im.save(trimmed)
    H = info["storeys"] * STOREY_M + 0.9           # plus parapet / cornice band
    W = H * im.size[0] / im.size[1]
    front = mats.image(trimmed, rough=0.8, grime=0.3, name="facade_" + name)
    side_mat = mats.painted(side or info["side"], rough=0.85)
    roof_mat = mats.painted(roof, rough=0.95)

    body = core.box((W, depth_m, H), (0, depth_m / 2, H / 2), side_mat, bevel=0, name="body")
    body.data.transform(body.matrix_world)   # work in building coordinates: front y = 0, ground z = 0
    body.matrix_world.identity()
    body.data.materials.append(front)
    body.data.materials.append(roof_mat)
    cut = []
    for u0, v0, u1, v1 in info["windows"]:
        w, h = (u1 - u0) * W, (v1 - v0) * H
        cx, cz = (u0 + u1) / 2 * W - W / 2, (v0 + v1) / 2 * H
        c = core.box((w, 2 * recess_m, h), (cx, 0, cz), front, bevel=0, name="cut")
        core.PARTS.remove(c)
        cut.append(c)
    if cut:
        bpy.ops.object.select_all(action="DESELECT")
        for c in cut:
            c.select_set(True)
        bpy.context.view_layer.objects.active = cut[0]
        bpy.ops.object.join()
        cutter = bpy.context.view_layer.objects.active
        mod = body.modifiers.new("windows", "BOOLEAN")
        mod.operation = "DIFFERENCE"
        mod.solver = "EXACT"
        mod.object = cutter
        mod.material_mode = "TRANSFER"
        core.apply_mods(body)
        bpy.data.objects.remove(cutter)
    me = body.data
    idx = {m.name: i for i, m in enumerate(me.materials)}
    bottom = []
    for p in me.polygons:
        n, c = p.normal, p.center
        if -1e-3 < c.y < recess_m + 1e-3 and (n.y < -0.5 or c.y > 1e-3):  # wall face, reveals, recesses
            p.material_index = idx[front.name]
        if n.z > 0.5 and c.z > H - 1e-3:
            p.material_index = idx[roof_mat.name]
        if n.z < -0.5 and c.z < 1e-3:
            bottom.append(p.index)
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.faces.ensure_lookup_table()
    bmesh.ops.delete(bm, geom=[bm.faces[i] for i in bottom], context="FACES")
    bm.to_mesh(me)
    bm.free()
    core.planar_uv(body, 0, 2, W, H)
    attr = me.color_attributes["label_uv"]
    for li in range(len(me.loops)):  # planar_uv centres v on 0; the wall stands on z = 0
        u, v, a, b = attr.data[li].color
        attr.data[li].color = (u, v - 0.5, a, b)

    ch = max(0.45, 0.035 * H)
    cor = core.box((W + 0.3, 0.6, ch), (0, 0.1, H - ch / 2), front, bevel=0.02, name="cornice")
    core.planar_uv(cor, 0, 2, W, H)
    ca = cor.data.color_attributes["label_uv"]
    for li in range(len(cor.data.loops)):
        u, v, a, b = ca.data[li].color
        z = cor.data.vertices[cor.data.loops[li].vertex_index].co.z + (H - ch / 2)
        ca.data[li].color = (min(max(u, 0.0), 1.0), min(z / H, 0.995), a, b)
    return {"width_m": round(W, 2), "height_m": round(H, 2), "depth_m": depth_m, "storeys": info["storeys"],
            "windows": len(info["windows"]), "side": side or info["side"], "wall_rgb": info["wall_rgb"]}
