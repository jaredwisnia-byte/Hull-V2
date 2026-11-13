"""Image-only silhouette extraction shared by planning and Blender construction."""

import numpy as np
from PIL import Image
from scipy import ndimage


def silhouette(path, thresh=30, convex=False, with_box=False):
    """Mask the main object plus nearby small shapes, then crop to its bounds.

    Background is estimated from the border. Dark enclosed areas count as solid;
    outer notches remain open. With ``with_box``, return crop coordinates too.
    """
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
        from skimage.morphology import convex_hull_image
        m = convex_hull_image(m)
    ys, xs = np.nonzero(m)
    box = (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1)
    if with_box:
        return m[box[1]:box[3], box[0]:box[2]], im.crop(box), box
    return m[box[1]:box[3], box[0]:box[2]], im.crop(box)
