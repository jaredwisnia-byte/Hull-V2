"""Blade carving for the hull line: find hollows that no outline shows (a sofa's seat).

Silhouettes alone fill a sofa's seat to arm height: in the side view the arm hides it, in the
front view the back cushions fill that outline, from the top it's a rectangle. An engineer
reading the same views does this instead:

- the top view splits into regions (each seat cushion, each arm, the back cushions);
- for a region at the front, the front view shows its top edge as a horizontal line across
  the region's width. A blade pushed in along that line, and one pushed down along the
  region's outline in the top view, meet along the region's real top;
- so the region is cut down to that line, but only if no view's outline changes: every view
  still shows exactly what was painted.

Works on the hull's voxels before smoothing, so the shapes stay soft and painted.
"""
import numpy as np
from PIL import Image
from scipy import ndimage

MIN_REGION = 0.01        # of the top outline's area
LINE_COVER = 0.6         # a top edge must run across this share of the region's width
WOBBLE = 3               # px: painted edges wander a little
MAX_OUTLINE_CHANGE = 0.005


def edges(img, mask):
    from skimage.feature import canny
    a = np.asarray(img.convert("L")).astype(float) / 255
    e = canny(a, sigma=2.5, low_threshold=0.04, high_threshold=0.10)
    return e & ndimage.binary_erosion(mask, iterations=3)


def regions(img, mask):
    """Areas of the top view enclosed by painted edges (cushions, arms...)."""
    # close small gaps in painted outlines (about 0.5% of the view) so cushions don't merge
    e = ndimage.binary_dilation(edges(img, mask), iterations=max(2, int(round(0.005 * max(mask.shape)))))
    outline = mask & ~ndimage.binary_erosion(mask, iterations=3)
    lab, n = ndimage.label(mask & ~e & ~outline)
    sizes = ndimage.sum(np.ones_like(lab), lab, range(1, n + 1))
    keep = [i + 1 for i, s in enumerate(sizes) if s >= MIN_REGION * mask.sum()]
    # Every pixel of the view belongs to its nearest region: the painted lines between cushions,
    # blotches inside them and the outline band are part of the surface, not walls.
    seeds = np.isin(lab, keep)
    idx = ndimage.distance_transform_edt(~seeds, return_distances=False, return_indices=True)
    full = np.where(mask, lab[idx[0], idx[1]], 0)
    return full, keep


def projections(keep):
    return {"front": keep.any(1), "side": keep.any(0), "top": keep.any(2)}


def carve(keep, sil, report=None):
    """keep: voxels [x (left->right), y (front->back), z (bottom->top)]; sil: {view: (mask, image)}.
    Lowers front-facing top-view regions to the top edge the front view shows for them."""
    if "top" not in sil or "front" not in sil:
        return keep
    nx, ny, nz = keep.shape
    tm, timg = sil["top"]
    fm, fimg = sil["front"]
    lab, ids = regions(timg, tm)
    th, tw = tm.shape
    fh, fw = fm.shape
    ink = edges(fimg, fm)
    thick = ink.copy()
    for d in range(1, WOBBLE + 1):
        thick[d:] |= ink[:-d]
        thick[:-d] |= ink[d:]
    xs = (np.arange(nx) + 0.5) / nx
    ys = (np.arange(ny) + 0.5) / ny
    zs = (np.arange(nz) + 0.5) / nz
    # top-view region label of every voxel column
    ci = np.clip((xs * tw).astype(int), 0, tw - 1)
    rj = np.clip(((1 - ys) * th).astype(int), 0, th - 1)
    col_lab = lab[rj[None, :], ci[:, None]]                          # [nx, ny]
    before = projections(keep)
    top_z = np.where(keep.any(2), (nz - 1 - np.argmax(keep[:, :, ::-1], 2)), -1)
    done, skipped = [], []
    order = sorted(ids, key=lambda i: np.nonzero(col_lab == i)[1].min() if (col_lab == i).any() else ny)
    for i in order:
        cols = col_lab == i
        if cols.sum() < 4:
            continue
        cx, cy = np.nonzero(cols)
        # the region must face the front: nothing taller stands in front of it
        if cy.min() > 0.25 * ny:
            skipped.append((int(i), "not at the front"))
            continue
        # A region on the outer left/right edge is what a side view sees first: its top is the
        # side view's outline there, so it can't be cut below that.
        occupied_x = np.nonzero(keep.any((1, 2)))[0]
        edge_margin = max(1, int(0.03 * nx))
        if cx.min() <= occupied_x.min() + edge_margin or cx.max() >= occupied_x.max() - edge_margin:
            skipped.append((int(i), "on the side edge: the side view shows its top"))
            continue
        x0, x1 = np.percentile(xs[cx], 10), np.percentile(xs[cx], 90)
        fx0, fx1 = int(x0 * fw), int(np.ceil(x1 * fw))
        if fx1 - fx0 < 4:
            continue
        cur = np.median(top_z[cx, cy])
        cover = thick[:, fx0:fx1].mean(1)                            # per front-view row
        best = None
        for r in range(fh):
            z = 1 - (r + 0.5) / fh
            zi = int(z * nz)
            if zi >= cur - 2 or zi < 0.1 * nz:
                continue
            if cover[r] >= LINE_COVER:
                best = zi
                break                                                # the highest such line
        if best is None:
            skipped.append((int(i), "no top edge in the front view (best cover %.2f)" % cover[:max(1, int((1 - cur / nz) * fh) - 2)].max()))
            continue
        trial = keep.copy()
        trial[cx, cy, best + 1:] = False
        after = projections(trial)
        changed = max((before[k] ^ after[k]).sum() / max(1, before[k].sum()) for k in before)
        if changed > MAX_OUTLINE_CHANGE:
            skipped.append((int(i), "would change an outline (%.3f)" % changed))
            continue
        keep = trial
        top_z = np.where(keep.any(2), (nz - 1 - np.argmax(keep[:, :, ::-1], 2)), -1)
        done.append({"region": int(i), "columns": int(cols.sum()), "from_z": round(float(cur) / nz, 3),
                     "to_z": round(float(best + 1) / nz, 3)})
    if report is not None:
        report["blade_carves"] = done
        report["blade_skipped"] = skipped
        report["top_regions"] = {int(i): [round(float(v), 2) for v in (xs[np.nonzero(col_lab == i)[0]].min(), xs[np.nonzero(col_lab == i)[0]].max(), ys[np.nonzero(col_lab == i)[1]].min(), ys[np.nonzero(col_lab == i)[1]].max())] for i in ids if (col_lab == i).any()}
    return keep
