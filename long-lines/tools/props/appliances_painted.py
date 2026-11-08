"""Appliances textured from painted sheets, assembled from propkit.parts."""
import math
import os

from propkit import prop
from propkit import mats as M
from propkit.core import box, cyl, planar_uv
from propkit.parts import sheet_box

SRC = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "assets", "source_textures"))
R90 = (math.radians(90), 0, 0)


def T(sheet, part, rough=0.45):
    return M.image(os.path.join(SRC, sheet, part + ".png"), rough, 0.25, 0.02, name="%s_%s" % (sheet, part))


@prop("range_electric", tex=2048, tags=["kitchen", "appliance"], kind="fixture")
def range_electric():
    """A 1960s electric range with a clock backsplash, coil burners and a broiler drawer."""
    S = "range_electric"
    W, D, H = 0.76, 0.64, 0.9
    body = M.plain((0.78, 0.75, 0.68), 0.4, edge=0.3, name="range_enamel")
    sheet_box((W, D, H * 0.27), (0, 0, 0.04), {"front": T(S, "drawer"), "left": T(S, "side_l"), "right": T(S, "side_r")}, body)
    sheet_box((W, D, H * 0.63), (0, 0, 0.04 + H * 0.27), {"front": T(S, "oven_door"), "left": T(S, "side_l"), "right": T(S, "side_r"),
                                                          "top": T(S, "cooktop")}, body)
    box((W, D - 0.04, 0.04), (0, 0.02, 0.02), T(S, "toe_kick"), bevel=0.004)
    sheet_box((W, 0.06, 0.2), (0, D / 2 - 0.03, H), {"front": T(S, "backsplash"), "top": body, "back": T(S, "panel_plain")}, body)
    # Real handles over the painted ones, so they catch light.
    chrome = M.chrome()
    box((0.5, 0.03, 0.022), (0, -D / 2 - 0.02, 0.04 + H * 0.27 + H * 0.63 * 0.86), chrome, bevel=0.009)
    box((0.26, 0.03, 0.02), (0, -D / 2 - 0.02, 0.04 + H * 0.27 * 0.82), chrome, bevel=0.008)
    for i, x in enumerate((-0.27, -0.16, 0.16, 0.27)):
        k = cyl(0.022, 0.024, (x, D / 2 - 0.075, H + 0.06), T(S, "knob", 0.35), 24, R90, bevel=0.003)
        planar_uv(k, 0, 2, 0.044, 0.044)
