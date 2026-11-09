"""Cross-sections inferred from the painting: how round each height band of an object is, without guide lines.

The silhouettes give, at every height, the half width a (front view) and half depth b (side view). They do
not say whether the section there is an ellipse (a turned shaft), a rounded box (a cushion, a car body) or a
sharp box (a square post). One family covers all of these, the superellipse

        |x/a|^n + |y/b|^n = 1        n = 2 ellipse ... n = 4-6 rounded box ... n large: box

so the only unknown per height band is n. The painting decides it by analysis by synthesis: a curved
section lit from the front shades smoothly across its width (brighter where it faces the light, darker
towards its edges), a flat face shades evenly. For each band and each candidate n the brightness across the
width predicted by that section (a constant, plus the section's sideways and facing normal components, any
light) is fitted to the painted brightness; the n that explains it best, by a clear margin over the box,
wins. Fine detail across the width (flutes, carving) is smoothed out first and measured: where it dominates,
the band is "carved" and left to the hull. All four elevations vote (they see the same section from four
sides). Bands with no clear evidence keep the hull's own section: the simplest shape the views allow.

Outputs: a voxel hook for the hull (each slice in a curved band becomes its superellipse, inscribed in the
slice's own extent), a JSON-ready report (observed widths kept apart from inferred n, with the evidence and
a confidence per band), and an overlay per view (the fitted sections drawn as rings in the view's own pixel
coordinates: a picture of the estimate, not decoration).
"""
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

from .hull import silhouette

CANDIDATES = (2.0, 2.6, 3.5, 5.0, 8.0, 24.0)     # superellipse exponents tried; the last is the box
BOX = CANDIDATES[-1]
SAMPLES = 48            # brightness samples across the width
EDGE_T = 0.9            # sample within this share of the half width (antialiased rims excluded)
BAND = 0.02             # band height, as a share of the object's height
SMOOTH = 4.0            # samples: across-width smoothing that removes flutes and carving
CURVED_MAX_N = 5.0      # a band is curved if its best n is at most this ...
MARGIN = 0.15           # ... and explains this much more of the brightness than the box
DETAIL_MAX = 0.55       # share of brightness variance in fine detail above which a band counts as carved
CONTRAST_MIN = 0.015    # brightness spread (0..1) below which a band says nothing
MIN_W = 12              # px: narrower rows are not judged
CARVED_DENSITY = 0.12   # share of a band's pixels on creases ...
CARVED_DIAG = 0.35      # ... with creases running every way (flutes run along, rings around: low): carved
END_ROUND_IOU = 0.93     # an end view (top / bottom) this close to an ellipse calls its carved bands round
END_WIDE = 0.92         # a band this close to the widest in its half (front and side) is what the end view draws
SMOOTH_Z = 2.5          # slices: smoothing of section size and centre along the height
WITNESS_VARY = 0.08     # second witness: front width and side depth each change this much over the run ...
WITNESS_CORR = 0.6      # ... and together (correlation)
RUN_MIN = 3             # bands: shorter curved runs are dropped


def _lum(path):
    m, img = silhouette(path)
    a = np.asarray(img.convert("RGB")).astype(float) / 255
    return m, a @ [0.299, 0.587, 0.114]


def normals(n, ratio, t):
    """Sideways and facing components of the outward normal of |x|^n + |y/ratio|^n = 1 (front at y < 0),
    at x = t (share of the half width)."""
    at = np.clip(np.abs(t), 0, 0.999)
    y = ratio * (1 - at ** n) ** (1 / n)
    gx = n * at ** (n - 1) * np.sign(t)
    gy = n * (y / ratio) ** (n - 1) / ratio
    g = np.hypot(gx, gy)
    return gx / g, gy / g


def band_profiles(path, other_widths=None):
    """Per band: the mean brightness across the width (SAMPLES points from edge to edge of each row), its
    half width in px, and the band's height range (v from the top, shares of the height)."""
    m, L = _lum(path)
    hh = m.shape[0]
    nb = int(round(1 / BAND))
    t = np.linspace(-EDGE_T, EDGE_T, SAMPLES)
    out = []
    for b in range(nb):
        r0, r1 = int(b * hh / nb), max(int((b + 1) * hh / nb), int(b * hh / nb) + 1)
        profs, widths = [], []
        for r in range(r0, r1):
            xs = np.nonzero(m[r])[0]
            if len(xs) < MIN_W:
                continue
            x0, x1 = xs.min(), xs.max()
            xq = (x0 + x1) / 2 + t * (x1 - x0) / 2
            profs.append(np.interp(xq, np.arange(m.shape[1]), L[r]))
            widths.append((x1 - x0 + 1) / 2)
        out.append({"v": (r0 / hh, r1 / hh), "profile": np.mean(profs, 0) if profs else None,
                    "half_px": float(np.mean(widths)) if widths else 0.0})
    return out


def carving(path):
    """Per band: (crease density, share of crease edges running diagonally). Carving (leaves, scrolls) has
    creases every way; turned work has them along the axis (flutes) or around it (rings, beads)."""
    from . import relief as R
    m, img = silhouette(path)
    L = R._lum(img, m)
    cav = np.clip(R._local_mean(L, m, R.CAVITY_SIGMA) - L, 0, None)
    cn = np.clip(cav / (np.percentile(cav[m], 95) + 1e-6), 0, 1)
    gy, gx = np.gradient(ndimage.gaussian_filter(cn, 1.0))
    mag = np.hypot(gx, gy)
    diag = np.abs(np.sin(2 * np.arctan2(gy, gx)))
    hh, nb = m.shape[0], int(round(1 / BAND))
    out = []
    for b in range(nb):
        sl = slice(int(b * hh / nb), max(int((b + 1) * hh / nb), int(b * hh / nb) + 1))
        mm = m[sl]
        if not mm.any():
            out.append((0.0, 0.0))
            continue
        w = mag[sl][mm]
        out.append((float((cn[sl][mm] > 0.35).mean()), float((diag[sl][mm] * w).sum() / max(w.sum(), 1e-9))))
    return out


def end_round(path):
    """Is an end view (top or bottom) round? (an ellipse fits its main body)."""
    from .revolve import round_body
    if not path:
        return None
    rb = round_body(silhouette(path)[0])
    return None if rb is None else {"iou": round(float(rb["iou"]), 3), "round": bool(rb["iou"] >= END_ROUND_IOU)}


def judge(profile, ratio):
    """R^2 of each candidate n for one smoothed brightness profile; detail share; contrast."""
    t = np.linspace(-EDGE_T, EDGE_T, SAMPLES)
    sm = ndimage.gaussian_filter1d(profile, SMOOTH, mode="nearest")
    detail = float(np.var(profile - sm) / max(np.var(profile), 1e-12))
    sst = float(np.sum((sm - sm.mean()) ** 2))
    r2 = {}
    for n in CANDIDATES:
        nx, nf = normals(n, ratio, t)
        A = np.c_[np.ones_like(t), nx, nf]
        c, *_ = np.linalg.lstsq(A, sm, rcond=None)
        if c[2] < 0:                               # facing the light must not be darker: refit without it
            A = A[:, :2]
            c, *_ = np.linalg.lstsq(A, sm, rcond=None)
        sse = float(np.sum((sm - A @ c) ** 2))
        r2[n] = 1 - sse / sst if sst > 1e-12 else 0.0
    return r2, detail, float(np.std(sm))


def infer(views):
    """Bands with their inferred exponent n. views: {name: path}; elevations vote."""
    pairs = [("front", "right"), ("back", "right"), ("right", "front"), ("left", "front")]
    prof = {k: band_profiles(views[k]) for k in ("front", "back", "right", "left") if k in views}
    if "right" not in prof and "left" in prof:
        prof["right"] = prof["left"]
    nb = int(round(1 / BAND))
    carv = {k: carving(views[k]) for k in prof if k in views}
    ends = {"top": end_round(views.get("top")), "bottom": end_round(views.get("bottom"))}
    # bands an end view draws: in each half, those as wide (front and side) as the widest there
    widest = {"top": set(), "bottom": set()}
    if "front" in prof and "right" in prof:
        fa = np.array([prof["front"][b]["half_px"] for b in range(nb)])
        sa = np.array([prof["right"][b]["half_px"] for b in range(nb)])
        for end, idx in (("top", range(0, nb // 2)), ("bottom", range(nb // 2, nb))):
            idx = list(idx)
            fm, sm = fa[idx].max(), sa[idx].max()
            widest[end] = {b for b in idx if fa[b] >= END_WIDE * fm and sa[b] >= END_WIDE * sm}
    bands = []
    for b in range(nb):
        votes, ev = [], {}
        dens = float(np.mean([c[b][0] for c in carv.values()]))
        diag = float(np.mean([c[b][1] for c in carv.values()]))
        carved = dens > CARVED_DENSITY and diag > CARVED_DIAG
        for k, other in pairs:
            if k not in prof or other not in prof:
                continue
            p, q = prof[k][b], prof[other][b]
            if p["profile"] is None or q["half_px"] <= 0:
                continue
            ratio = q["half_px"] / max(p["half_px"], 1e-6)
            r2, detail, contrast = judge(p["profile"], ratio)
            ev[k] = {"r2": {str(n): round(v, 3) for n, v in r2.items()}, "detail": round(detail, 2),
                     "contrast": round(contrast, 3)}
            if contrast < CONTRAST_MIN or detail > DETAIL_MAX:
                continue
            votes.append(r2)
        band = {"v": [round(x, 3) for x in prof["front"][b]["v"]] if "front" in prof else None, "evidence": ev,
                "carving": {"crease_density": round(dens, 2), "diagonal_share": round(diag, 2), "carved": carved}}
        upper = (band["v"] or [0.5])[0] < 0.5
        end = "top" if upper else "bottom"
        if b in widest[end] and not ends.get(end):
            # the part an end view would draw, with no such view: nothing else can tell its section
            band.update(best_n=None, gain=0.0, views_voting=0, curved=False,
                        decided_by="%s view would draw it: missing, no claim" % end)
            bands.append(band)
            continue
        if b in widest[end] and ends.get(end):
            # the widest part near an end is what that end view draws: its section is that view's shape
            e = ends[end]
            band.update(best_n=2.0 if e["round"] else None, gain=0.0, views_voting=0, curved=e["round"],
                        decided_by="%s view draws it: %s (IoU %.2f)" % (end, "round" if e["round"] else "not round", e["iou"]))
            bands.append(band)
            continue
        if carved:
            # carving shades like curvature (a leaf's edges are dark): only the outline seen from the
            # nearer end can say what the section is; no end view, no claim
            end = "top" if (band["v"] or [0.5])[0] < 0.5 else "bottom"
            e = ends.get(end)
            rnd = bool(e and e["round"])
            band.update(best_n=2.0 if rnd else None, gain=0.0, views_voting=0, curved=rnd,
                        decided_by="%s view %s" % (end, ("round (IoU %.2f)" % e["iou"]) if rnd else
                                                     ("not round (IoU %.2f)" % e["iou"]) if e else "missing"))
            bands.append(band)
            continue
        if votes:
            mean = {n: float(np.mean([v[n] for v in votes])) for n in CANDIDATES}
            best = max(CANDIDATES, key=lambda n: mean[n])
            gain = mean[best] - mean[BOX]
            band.update(best_n=best, gain=round(gain, 3), views_voting=len(votes),
                        curved=bool(best <= CURVED_MAX_N and gain >= MARGIN), decided_by="shading")
        else:
            band.update(best_n=None, gain=0.0, views_voting=0, curved=False, decided_by="no evidence")
        bands.append(band)
    # a second witness for shading: painterly gradients on a box shade like curvature, so a run decided by
    # shading alone must also have the outline of a turned or moulded form: front width and side depth
    # swelling or tapering together. Straight-sided runs keep the hull (a box stays a box)
    if "front" in prof and "right" in prof:
        fa = np.array([prof["front"][b]["half_px"] for b in range(nb)])
        sa = np.array([prof["right"][b]["half_px"] for b in range(nb)])
        cur = [b["curved"] and b.get("decided_by") == "shading" for b in bands]
        lab, k = ndimage.label(np.array(cur))
        for i in range(1, k + 1):
            idx = np.nonzero(lab == i)[0]
            a_, b_ = fa[idx], sa[idx]
            vary = min(np.ptp(a_) / max(a_.mean(), 1e-6), np.ptp(b_) / max(b_.mean(), 1e-6))
            corr = float(np.corrcoef(a_, b_)[0, 1]) if len(idx) > 2 and a_.std() > 0 and b_.std() > 0 else 0.0
            ok = vary >= WITNESS_VARY and corr >= WITNESS_CORR
            for j in idx:
                bands[j]["witness"] = {"outline_varies": round(float(vary), 3), "front_side_corr": round(corr, 2)}
                if not ok:
                    bands[j]["curved"] = False
                    bands[j]["decided_by"] = "shading without a second witness (straight-sided outline)"
    # a run touching the object's top or bottom is what that end view draws: the end view decides it
    cur = np.array([b["curved"] for b in bands])
    lab, k = ndimage.label(cur)
    for i in range(1, k + 1):
        idx = np.nonzero(lab == i)[0]
        for end, at in (("top", 0), ("bottom", nb - 1)):
            if at in idx:
                e = ends.get(end)
                rnd = bool(e and e["round"])
                for j in idx:
                    if "view" in bands[j].get("decided_by", "") and end in bands[j]["decided_by"]:
                        continue
                    bands[j]["curved"] = rnd
                    bands[j]["best_n"] = bands[j]["best_n"] if rnd else None
                    bands[j]["decided_by"] = "touches the %s: %s view %s" % (
                        end, end, ("round (IoU %.2f)" % e["iou"]) if rnd else ("not round (IoU %.2f)" % e["iou"]) if e else "missing, no claim")
    # runs: drop isolated curved bands; fill single-band gaps inside a curved run
    c = np.array([b["curved"] for b in bands])
    c = c | ndimage.binary_closing(c, structure=np.ones(3, bool))
    lab, k = ndimage.label(c)
    for i in range(1, k + 1):
        idx = np.nonzero(lab == i)[0]
        if len(idx) < RUN_MIN:
            c[idx] = False
    ns = [b["best_n"] for b in bands]
    for i, b in enumerate(bands):
        b["curved"] = bool(c[i])
        if b["curved"] and (ns[i] is None or ns[i] > CURVED_MAX_N):
            near = [ns[j] for j in (i - 1, i + 1) if 0 <= j < len(ns) and ns[j] and ns[j] <= CURVED_MAX_N]
            b["best_n"] = float(np.median(near)) if near else 2.0
        b["confidence"] = ("medium" if b["curved"] and (b.get("views_voting", 0) >= 2 or "view" in b.get("decided_by", ""))
                           else "low" if b["curved"] else "hull")
    return bands


def curved_runs(bands):
    runs, cur = [], None
    for b in bands:
        if b["curved"]:
            if cur is None:
                cur = {"v_top": b["v"][0], "v_bottom": b["v"][1], "n": [b["best_n"]]}
            else:
                cur["v_bottom"] = b["v"][1]
                cur["n"].append(b["best_n"])
        elif cur is not None:
            runs.append(cur)
            cur = None
    if cur is not None:
        runs.append(cur)
    for r in runs:
        r["n"] = round(float(np.median(r["n"])), 2)
        r["v_top"], r["v_bottom"] = round(r["v_top"], 3), round(r["v_bottom"], 3)
    return runs


def hook(views, report):
    """A hull voxel_hook: slices in curved bands become superellipses of their band's n."""
    bands = infer(views)
    report["bands"] = [{k: v for k, v in b.items() if k != "evidence"} for b in bands]
    report["evidence"] = {i: b["evidence"] for i, b in enumerate(bands) if b["evidence"]}
    report["curved_runs"] = curved_runs(bands)

    def apply(keep, carve, W, D, H):
        nx, ny, nz = keep.shape
        zs = (np.arange(nz) + 0.5) / nz
        xs = np.arange(nx)[:, None]
        ys = np.arange(ny)[None, :]
        bi = np.minimum(((1 - zs) / BAND).astype(int), len(bands) - 1)
        on = np.array([bands[i]["curved"] for i in bi]) & keep.any(axis=(0, 1))
        # each slice's extent, smoothed along the height within each curved run: slices sized one by one
        # jitter by a voxel and stack into horizontal ridges
        par = np.zeros((nz, 4))
        for iz in np.nonzero(on)[0]:
            ix, iy = np.nonzero(keep[:, :, iz])
            par[iz] = ((ix.min() + ix.max()) / 2, (iy.min() + iy.max()) / 2,
                       (ix.max() - ix.min() + 1) / 2, (iy.max() - iy.min() + 1) / 2)
        lab, k = ndimage.label(on)
        for i in range(1, k + 1):
            idx = np.nonzero(lab == i)[0]
            if len(idx) > 3:
                par[idx] = ndimage.gaussian_filter1d(par[idx], SMOOTH_Z, axis=0, mode="nearest")
        removed = 0
        for iz in np.nonzero(on)[0]:
            cx, cy, ax, ay = par[iz]
            n = bands[bi[iz]]["best_n"]
            s = keep[:, :, iz]
            sec = np.abs((xs - cx) / max(ax, 0.5)) ** n + np.abs((ys - cy) / max(ay, 0.5)) ** n <= 1.0
            removed += int((s & ~sec).sum())
            keep[:, :, iz] = s & sec
        report["voxels_removed"] = removed
        return keep
    return apply


def overlay(view_path, bands, out_png, colour=(0, 220, 255, 255)):
    """The fitted sections drawn on a transparent image the size of the view: for each curved band, the
    near half of its ring (a superellipse seen edge-on and tilted slightly, as a draughtsman draws a
    cross-section ring) at the band's height, spanning the object's width there."""
    im = Image.open(view_path).convert("RGB")
    m, _, (x0, y0, x1, y1) = silhouette(view_path, with_box=True)
    ov = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    hh = m.shape[0]
    for b in bands[::2]:
        if not b["curved"]:
            continue
        r = int((b["v"][0] + b["v"][1]) / 2 * hh)
        xs = np.nonzero(m[min(r, hh - 1)])[0]
        if len(xs) < MIN_W:
            continue
        cx, a = (xs.min() + xs.max()) / 2, (xs.max() - xs.min()) / 2
        n = b["best_n"]
        tt = np.linspace(-1, 1, 41)
        dip = 0.12 * a                                     # the ring's apparent depth when seen slightly from above
        pts = [(x0 + cx + a * t, y0 + r + dip * (1 - np.abs(t) ** n) ** (1 / n)) for t in tt]
        d.line(pts, fill=colour, width=2)
        pts = [(x0 + cx + a * t, y0 + r - dip * (1 - np.abs(t) ** n) ** (1 / n)) for t in tt]
        d.line(pts, fill=colour[:3] + (110,), width=1)
    ov.save(out_png)
    return ov
