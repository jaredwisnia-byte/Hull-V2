"""Prop kit: shared parts for building, baking and exporting props.

Recipes live in tools/props/*.py and register themselves with @prop.
"""
PROPS = {}


def prop(name, tex=1024, tags=(), desc="", kind="static"):
    """Registers a recipe. tex is the baked texture size; kind is the default
    Godot behaviour (static, fixture, carry, container, readable)."""
    def wrap(fn):
        PROPS[name] = {"fn": fn, "tex": tex, "tags": list(tags), "desc": desc or (fn.__doc__ or "").strip(), "kind": kind}
        return fn
    return wrap
