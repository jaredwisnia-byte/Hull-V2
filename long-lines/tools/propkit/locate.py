"""Find a part's own painted view inside a whole-object view (the 'photo' of the assembly).

A parts sheet draws each part at its own scale. The part's position AND size in the assembled object
come from where its painting best matches the whole-object view: masked normalised cross-correlation
(only the part's own pixels count, so the surroundings in the photo don't matter) over a range of
scales. Reliable for a large, distinctive part lying on the body (a dial face); thin or repetitive parts
are better found as residuals, protrusions or attachments (propkit/parts_layout.py)."""
import numpy as np
from PIL import Image
from scipy import ndimage
from scipy.signal import fftconvolve

from .hull import silhouette


def _grey(img):
    return np.asarray(img.convert("L")).astype(float) / 255


def masked_ncc(I, T, M):
    """Normalised cross-correlation of template T (weights M) at every valid offset in image I."""
    M = M.astype(float)
    n = M.sum()
    if n < 10:
        return None
    Tm = (T * M).sum() / n
    Tz = (T - Tm) * M
    Tn = np.sqrt((Tz ** 2).sum())
    Mf = M[::-1, ::-1]
    s1 = fftconvolve(I, Mf, mode="valid")
    s2 = fftconvolve(I * I, Mf, mode="valid")
    num = fftconvolve(I, Tz[::-1, ::-1], mode="valid")
    var = np.maximum(s2 - s1 * s1 / n, 1e-9)
    return num / (np.sqrt(var) * max(Tn, 1e-9))


def find_part(view_path, part_path, scales=None):
    """Best placement of the part's view in the whole view: dict(score, scale (whole px per part px),
    box (x0, y0, x1, y1) in the whole view's object crop, frac (u0, u1, v0, v1)).

    Masked NCC of grey levels blurred in proportion to the scale (broad shading survives a change of
    drawing size; fine brushwork does not), counting only the part's own pixels and not its drawn holes
    (what shows through a hole depends on the assembly), and never off the object."""
    import os
    wm, wimg = silhouette(view_path)
    pm, pimg, box = silhouette(part_path, with_box=True)
    hp = os.path.join(os.path.dirname(part_path), "h_%s.png" % os.path.basename(part_path)[2:-4])
    pm_use = pm
    if os.path.exists(hp):
        holes = np.asarray(Image.open(hp).convert("L").crop(box)) > 127
        if holes.shape == pm.shape:
            pm_use = pm & ~ndimage.binary_dilation(holes, iterations=2)
    wg = _grey(wimg)
    H_, W_ = wm.shape
    h, w = pm.shape
    best = None
    for s in (scales if scales is not None else np.geomspace(0.15, 1.3, 30)):
        th, tw = int(round(h * s)), int(round(w * s))
        if th < 10 or tw < 10 or th > H_ or tw > W_:
            continue
        sig = max(1.0, 2.0 * s)
        M = np.asarray(Image.fromarray(pm_use.astype(np.uint8) * 255).resize((tw, th))) > 127
        Mo = np.asarray(Image.fromarray(pm.astype(np.uint8) * 255).resize((tw, th))) > 127
        a = masked_ncc(ndimage.gaussian_filter(wg, sig), ndimage.gaussian_filter(_grey(pimg.resize((tw, th))), sig), M)
        if a is None:
            continue
        on = fftconvolve(wm.astype(float), Mo[::-1, ::-1].astype(float), mode="valid") / Mo.sum()
        score = a - 2.0 * (1 - on)
        j = np.unravel_index(int(np.argmax(score)), score.shape)
        if best is None or score[j] > best["score"]:
            y0, x0 = int(j[0]), int(j[1])
            best = {"score": float(score[j]), "scale": float(s), "box": (x0, y0, x0 + tw, y0 + th),
                    "frac": (x0 / W_, (x0 + tw) / W_, y0 / H_, (y0 + th) / H_)}
    return best
