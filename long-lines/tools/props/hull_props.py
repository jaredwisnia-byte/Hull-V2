"""Props built by visual hull from orthographic painted views (propkit.hull).
A sheet with front/side/top views of an object becomes a prop with one entry here."""
import os

from propkit import prop
from propkit.hull import hull_prop

SRC = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "assets", "source_textures"))


def views(folder, prefix="v_"):
    d = os.path.join(SRC, folder)
    return {k: os.path.join(d, prefix + k + ".png") for k in ("front", "back", "right", "left", "top")
            if os.path.exists(os.path.join(d, prefix + k + ".png"))}


# name -> (source folder, real height in metres, description, hull options)
HULLS = {
    "tv_hull": ("tv_painted", 0.48, "The painted 'Westbury' TV rebuilt by visual hull from its five sheet views.",
                {"convex": True, "paint_only": ("back",)}),
}


def _register(name, folder, height, desc, opts):
    prop(name, tex=2048, tags=["electronics", "hull"], desc=desc, kind="fixture")(lambda: hull_prop(views(folder), height, name=name, **opts))


for _n, (_f, _h, _d, _o) in HULLS.items():
    _register(_n, _f, _h, _d, _o)
