"""Round parts for the hull line: a part whose top view is round is a lathe shape.

Intersecting the front and side outlines makes every horizontal slice a rectangle, so a carafe,
vase, bottle, lamp base or stool comes out boxy. The top view says what the slices really are.
If its main body (the outline with thin appendages such as a handle or spout opened away) is an
ellipse, the body is a surface of revolution: the slice at each height is an ellipse whose width
is the front outline's width there and whose depth is the side outline's width there. Appendages
keep the ordinary hull shape (a handle is the intersection of its views).
"""
import numpy as np
from scipy import ndimage

ROUND_IOU = 0.96          # main body vs its fitted ellipse (a square ~0.83, a squircle ~0.9)
APPENDAGE_RATIO = 0.6     # sticks out at least this much of its joint's width: a handle, not a corner
MAX_TILT = 12             # degrees: the ellipse must line up with the front/side views


def _disk(r):
    r = max(1, int(r))
    yy, xx = np.mgrid[-r:r + 1, -r:r + 1]
    return xx * xx + yy * yy <= r * r


def round_body(top_mask):
    """The top view's main round body as {cx, cy, ax, ay (pixels), iou, core}, or None."""
    P = 2                                       # silhouettes are cropped tight: pad so the edge is background
    m = np.pad(top_mask.astype(bool), P)
    if m.sum() < 50:
        return None
    r = ndimage.distance_transform_edt(m).max()
    core = ndimage.binary_opening(m, structure=_disk(0.6 * r))     # thin parts (handle, spout) go
    lab, n = ndimage.label(core)
    if not n:
        return None
    core = lab == (1 + int(np.argmax(ndimage.sum(core, lab, range(1, n + 1)))))
    # The opening also shaves a box's corners. A shaved piece is an appendage only if it sticks out
    # (deep compared with where it joins the body: a handle, a spout); shallow wide slivers
    # (corners, chamfers) go back to the body so a box never passes as round.
    rest, nr = ndimage.label(m & ~core)
    depth_from_core = ndimage.distance_transform_edt(~core)
    rim = ndimage.binary_dilation(core) & ~core
    for i in range(1, nr + 1):
        piece = rest == i
        joint = (piece & rim).sum()
        if joint == 0:
            continue                                              # not attached: not part of the body
        if depth_from_core[piece].max() < APPENDAGE_RATIO * joint:
            core |= piece
    ys, xs = np.nonzero(core)
    cx, cy = xs.mean(), ys.mean()
    cov = np.cov(np.vstack([xs - cx, ys - cy]))
    ev, evec = np.linalg.eigh(cov)
    tilt = abs(np.degrees(np.arctan2(evec[1, 1], evec[0, 1])))
    tilt = min(tilt % 90, 90 - tilt % 90) if ev[1] / max(ev[0], 1e-9) > 1.05 else 0.0
    ax, ay = 2 * np.sqrt(cov[0, 0]), 2 * np.sqrt(cov[1, 1])          # uniform ellipse: var = a^2 / 4
    h, w = m.shape
    Y, X = np.mgrid[0:h, 0:w]
    ell = ((X - cx) / ax) ** 2 + ((Y - cy) / ay) ** 2 <= 1
    iou = float((ell & core).sum() / max(1, (ell | core).sum()))
    core = core[P:-P, P:-P]
    m = m[P:-P, P:-P]
    cx, cy = cx - P, cy - P
    out = {"cx": float(cx), "cy": float(cy), "ax": float(ax), "ay": float(ay), "iou": round(iou, 3),
           "tilt": round(float(tilt), 1), "core": core, "share": round(float(core.sum() / m.sum()), 3)}
    out["round"] = iou >= ROUND_IOU and tilt <= MAX_TILT
    return out


def _run_at(row, c):
    """(start, end) of the filled run of a boolean row containing column c, or of the nearest run."""
    xs = np.nonzero(row)[0]
    if not len(xs):
        return None
    c = int(np.clip(c, 0, len(row) - 1))
    if not row[c]:
        c = int(xs[np.argmin(np.abs(xs - c))])
    a = c
    while a > 0 and row[a - 1]:
        a -= 1
    b = c
    while b < len(row) - 1 and row[b + 1]:
        b += 1
    return a, b + 1


def voxel_hook(report=None):
    """hull_prop voxel_hook: a part whose top view is round is a lathe about the vertical axis (a carafe);
    one whose front view is round is a lathe about the front-to-back axis (a dial, a cap). Boxy slices
    become ellipses; appendages (a handle, a finger stop) keep their hull."""
    def hook(keep, sil, W, D, H):
        out = _lathe(keep, sil, report, "vertical")
        if out is not keep:
            return out
        if "front" not in sil:
            return keep
        # front-to-back axis: relabel so the front view plays the top view's part, lathe, relabel back
        # (x, y, z) -> (x, z, y): new top = front; new front = top; new right = the side view turned
        ns = {"top": sil["front"]}
        if "top" in sil:
            ns["front"] = sil["top"]
        if "right" in sil:
            side = sil["right"]
        elif "left" in sil:
            side = (sil["left"][0][:, ::-1], sil["left"][1])          # as a right view
        else:
            side = None
        if side is not None:
            R = side[0]
            ns["right"] = (np.ascontiguousarray(R[::-1, :].T[::-1, :]), side[1])
        t = np.ascontiguousarray(keep.transpose(0, 2, 1))
        rep2 = {} if report is not None else None
        o = _lathe(t, ns, rep2, "front-to-back")
        if report is not None and rep2.get("revolve"):
            report["revolve"] = rep2["revolve"]
        return keep if o is t else np.ascontiguousarray(o.transpose(0, 2, 1))
    return hook


def _lathe(keep, sil, report, axis):
    """The lathe about the axis the "top" view looks along; front and side views (either may be
    missing) give the slice radii; returns keep itself when the top view is not round."""
    if "top" not in sil or not ({"front", "right", "left"} & set(sil)):
        return keep
    tm = sil["top"][0]
    rb = round_body(tm)
    if report is not None:
        if rb is not None and (rb["round"] or not report.get("revolve")):
            report["revolve"] = {k: rb[k] for k in ("iou", "tilt", "share", "round")}
            report["revolve"]["axis"] = axis
    if rb is None or not rb["round"]:
        return keep
    nx, ny, nz = keep.shape
    th, tw = tm.shape
    fm = sil["front"][0] if "front" in sil else None
    side = "right" if "right" in sil else "left" if "left" in sil else None
    # axis of the body, as fractions of width (x) and depth (y from the front)
    ux, uy = rb["cx"] / tw, 1 - rb["cy"] / th
    xs = (np.arange(nx) + 0.5) / nx
    ys = (np.arange(ny) + 0.5) / ny
    # appendage columns: in the top outline outside the round body (their hull stays)
    ci = np.clip((xs * tw).astype(int), 0, tw - 1)
    rj = np.clip(((1 - ys) * th).astype(int), 0, th - 1)
    app_px = tm & ~rb["core"]
    app = app_px[rj[None, :], ci[:, None]]                              # [nx, ny]
    # the directions the appendages leave the body in (a handle meets the body where the body
    # is narrower than its widest slice: the wedge between them in that direction joins them)
    X_, Y_ = np.meshgrid(ci, rj, indexing="ij")
    ang_cols = np.arctan2(Y_ - rb["cy"], X_ - rb["cx"])
    sector = np.zeros((nx, ny), bool)
    lab_a, na = ndimage.label(app_px)
    for i in range(1, na + 1):
        yy_, xx_ = np.nonzero(lab_a == i)
        if len(xx_) < 0.002 * tm.sum():
            continue                                                    # outline noise
        ang = np.arctan2(yy_ - rb["cy"], xx_ - rb["cx"])
        mid = np.arctan2(np.sin(ang).mean(), np.cos(ang).mean())
        dev = np.angle(np.exp(1j * (ang - mid)))
        lo, hi = dev.min(), dev.max()
        dc = np.angle(np.exp(1j * (ang_cols - mid)))
        sector |= (dc >= lo) & (dc <= hi)
    core_cols = rb["core"][rj[None, :], ci[:, None]]
    if fm is not None:
        fh, fw = fm.shape
    if side:
        sm = sil[side][0]
        sh, sw = sm.shape
    lathe = np.zeros_like(keep)
    rows = 0
    for k in range(nz):
        zf = 1 - (k + 0.5) / nz
        rx = ry = None
        if fm is not None:
            run = _run_at(fm[min(fh - 1, int(zf * fh))], ux * fw)
            if run is None:
                continue
            # a lathe is symmetric about its axis: the radius is the axis to the nearer edge (a
            # handle drawn joined to the body widens a row on its own side only)
            rx = min(ux - run[0] / fw, run[1] / fw - ux)
            ry = (rb["ay"] / th) * rx / max(rb["ax"] / tw, 1e-6)      # default: the top view's ratio
        if side:
            sr = sm[min(sh - 1, int(zf * sh))]
            c_side = uy if side == "right" else 1 - uy
            srun = _run_at(sr, c_side * sw)
            if srun is not None:
                y0, y1 = srun[0] / sw, srun[1] / sw
                if side == "left":
                    y0, y1 = 1 - y1, 1 - y0
                ry = min(uy - y0, y1 - uy)
                if rx is None:                                          # no front view: the top's ratio
                    rx = ry * (rb["ax"] / tw) / max(rb["ay"] / th, 1e-6)
            elif rx is None:
                continue
        if rx is None or ry is None or rx <= 0 or ry <= 0:
            continue
        cxk, cyk = ux, uy
        e = ((xs[:, None] - cxk) / max(rx, 1e-6)) ** 2 + ((ys[None, :] - cyk) / max(ry, 1e-6)) ** 2 <= 1
        lathe[:, :, k] = e
        rows += 1
    # never outside any outline: everything kept is still inside the plain hull
    out = (keep & app[:, :, None]) | (keep & lathe)
    handle_z = (keep & app[:, :, None]).any((0, 1))                    # heights an appendage exists
    out |= keep & (sector & core_cols)[:, :, None] & handle_z[None, None, :]
    if report is not None:
        report["revolve"]["slices"] = rows
        report["revolve"]["voxels_before_after"] = [int(keep.sum()), int(out.sum())]
    return out

