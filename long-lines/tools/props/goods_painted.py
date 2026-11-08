"""Cans textured from supplied painted label sheets (assets/source_textures/cans/)."""
import math
import os

from propkit import prop
from propkit import mats as M
from propkit.core import cyl, planar_uv, wrap_uv
from propkit.parts import rolled_rim

SRC = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "assets", "source_textures", "cans"))


def painted_can(name, r, h, repeat=1.0):
    """A food can: wrapped painted label, rolled rims, and the plain painted lid on
    both ends (opened with a can opener, as in 1975)."""
    label = M.image(os.path.join(SRC, name + "_label.png"), 0.55, 0.25, 0.0, name=name + "_label",
                    extension="REPEAT" if repeat > 1 else "EXTEND")
    lid = M.image(os.path.join(SRC, name + "_lid.png"), 0.4, 0.3, 0.0, name=name + "_lid")
    rim = M.plain((0.42, 0.38, 0.33), 0.6, edge=0.2, grime=0.8, metal_v=0.5, name="can_rim")
    body = cyl(r, h - 0.008, (0, 0, h / 2), label, 40)
    wrap_uv(body, h - 0.008, -(h - 0.008) / 2, repeat)
    for z in (0.003, h - 0.003):
        rolled_rim(r + 0.0005, z, rim, 0.0032)
        cap = cyl(r * 0.99, 0.002, (0, 0, z + (-0.0005 if z > h / 2 else 0.0005)), lid, 40)
        planar_uv(cap, 0, 1, r * 2 * 0.99, r * 2 * 0.99)


@prop("can_soup", tex=512, tags=["goods", "food", "small"], kind="carry")
def can_soup():
    """A can of Northern Harvest tomato soup."""
    painted_can("tomato", 0.033, 0.101)


@prop("can_peaches", tex=512, tags=["goods", "food", "small"], kind="carry")
def can_peaches():
    """A can of Orchard Crest sliced peaches."""
    painted_can("peaches", 0.038, 0.112)


@prop("can_tuna", tex=512, tags=["goods", "food", "small"], kind="carry")
def can_tuna():
    """A flat can of North Shore albacore tuna."""
    painted_can("tuna", 0.043, 0.042, repeat=2.0)


@prop("can_chili", tex=512, tags=["goods", "food", "small"], kind="carry")
def can_chili():
    """A can of Campfire chili with beans."""
    painted_can("chili", 0.038, 0.112)
