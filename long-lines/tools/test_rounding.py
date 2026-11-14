"""Measured roundness and local features (propkit/rounding.py, propkit/features.py)."""
import math
import unittest

import numpy as np
from PIL import Image, ImageDraw

from propkit import features, rounding


def _box_views(nx=40, ny=30, nz=60):
    """A plain upright bar: front 40 wide, side 30 deep, 60 tall (no top view constraint)."""
    front = np.ones((nz, nx), bool)
    side = np.ones((nz, ny), bool)
    return front, side, None, (nx, ny, nz)


class Rounding(unittest.TestCase):
    def test_round_exponent_makes_elliptic_sections(self):
        front, side, top, shape = _box_views()
        Fm, Sm, Tm = rounding.view_masks(front, side, top, shape)
        keep = Fm[:, None, :] & Sm[None, :, :] & Tm[:, :, None]
        out = rounding.rounded_hull(keep, Fm, Sm, Tm, {'z': 2.0}, (True, True, False))
        frac = out.sum() / keep.sum()
        # an ellipse fills pi/4 of its box; the half-voxel slack adds about 6% on this 40 x 30 grid
        self.assertAlmostEqual(frac, math.pi / 4, delta=0.065)

    def test_rounding_never_changes_an_outline(self):
        front, side, top, shape = _box_views()
        Fm, Sm, Tm = rounding.view_masks(front, side, top, shape)
        keep = Fm[:, None, :] & Sm[None, :, :] & Tm[:, :, None]
        for ex in ({'z': 2.0}, {'x': 2.0}, {'y': 2.6}, {'x': 2.0, 'y': 2.0, 'z': 2.0}):
            out = rounding.rounded_hull(keep, Fm, Sm, Tm, ex, (True, True, False))
            self.assertTrue((out.any(1) == keep.any(1)).all(), ex)     # front outline
            self.assertTrue((out.any(0) == keep.any(0)).all(), ex)     # side outline

    def test_infinite_exponent_is_the_visual_hull(self):
        front, side, top, shape = _box_views()
        Fm, Sm, Tm = rounding.view_masks(front, side, top, shape)
        keep = Fm[:, None, :] & Sm[None, :, :] & Tm[:, :, None]
        out = rounding.rounded_hull(keep, Fm, Sm, Tm, {'z': math.inf})
        self.assertTrue((out == keep).all())

    def test_parts_split_where_the_section_jumps(self):
        # a narrow handle under a wide body, seen from the front and the side
        front = np.zeros((60, 40), bool)
        front[:25, :] = True             # body (top rows)
        front[25:, 15:25] = True         # handle
        side = np.zeros((60, 30), bool)
        side[:25, :] = True
        side[25:, 10:20] = True
        Fm, Sm, Tm = rounding.view_masks(front, side, None, (40, 30, 60))
        parts = rounding.tracks('z', Fm, Sm, Tm)
        self.assertGreaterEqual(len(parts), 2)
        handle = min(parts, key=lambda p: p['box'][3] - p['box'][2])
        self.assertLess(handle['box'][1], 0.65)        # the handle part ends below the body


class LocalFeatures(unittest.TestCase):
    def test_bump_is_as_wide_as_the_painting_shows(self):
        # an upright handle 40 wide x 30 deep x 100 tall with a switch sticking out of the front
        # (toward -y) between heights 40 and 55; the front painting shows the switch 10 wide
        H, W, D = 100, 40, 36
        front_m = np.ones((H, W), bool)
        side_m = np.zeros((H, D), bool)
        side_m[:, 6:] = True
        side_m[100 - 55:100 - 40, :6] = True     # the switch, at the front of the side view
        paint = Image.new('RGB', (W, H), (200, 120, 60))
        ImageDraw.Draw(paint).rectangle([15, 100 - 55, 24, 100 - 41], fill=(30, 30, 30))
        top_m = np.ones((D, W), bool)
        masks = {'front': front_m, 'right': side_m, 'top': top_m}
        paintings = {'front': paint, 'right': Image.new('RGB', (D, H), (200, 120, 60)),
                     'top': Image.new('RGB', (W, D), (200, 120, 60))}
        feats = features.find(masks, paintings, {'width': W / 1000, 'depth': D / 1000, 'height': H / 1000}, res=100)
        sw = [f for f in feats if f['axis'] == 'z' and f.get('keep')]
        self.assertTrue(sw, feats)
        lo, hi = sw[0]['keep']
        self.assertAlmostEqual((lo + hi) / 2, 0.5, delta=0.08)
        self.assertAlmostEqual(hi - lo, 10 / 40, delta=0.1)


if __name__ == '__main__':
    unittest.main()


class OppositeViews(unittest.TestCase):
    def test_part_missing_from_one_view_is_kept_when_others_support_it(self):
        from propkit.drafting import reconcile_opposites
        # body 100 wide x 60 deep x 80 tall; a lever sticks out on the left at the top.
        front = np.zeros((80, 120), bool); front[:, 20:] = True; front[5:12, :20] = True   # lever drawn
        back = np.zeros((80, 120), bool); back[:, :100] = True                             # lever left out
        right = np.ones((80, 60), bool)
        left = np.ones((80, 60), bool)
        top = np.zeros((60, 120), bool); top[:, 20:] = True; top[40:55, :20] = True        # lever from above
        bottom = top[::-1].copy()
        out, rep = reconcile_opposites({'front': front, 'back': back, 'right': right, 'left': left,
                                        'top': top, 'bottom': bottom}, 0.12, 0.06, 0.08)
        self.assertTrue(out['front'][5:12, :20].mean() > 0.9)          # lever kept in the front
        self.assertTrue(out['back'][5:12, 100:].mean() > 0.9)          # and added to the back (mirrored)
        self.assertGreater(rep['front/back']['kept_from_one_view_px'], 0)

    def test_unsupported_extra_is_dropped(self):
        from propkit.drafting import reconcile_opposites
        front = np.ones((80, 120), bool); front[:, :20] = False; front[5:12, :20] = True   # stray bump
        back = np.ones((80, 120), bool); back[:, 100:] = False
        side = np.ones((80, 60), bool)
        top = np.zeros((60, 120), bool); top[:, 20:] = True                                # nothing there from above
        out, rep = reconcile_opposites({'front': front, 'back': back, 'right': side, 'left': side,
                                        'top': top, 'bottom': top[::-1].copy()}, 0.12, 0.06, 0.08)
        self.assertTrue(out['front'][5:12, :18].mean() < 0.1)
        self.assertGreater(rep['front/back']['dropped_px'], 0)
