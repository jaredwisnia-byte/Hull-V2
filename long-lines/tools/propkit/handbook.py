"""The reference handbook (factory/reference_handbook.json): what an object type is made of and how big
its parts really are, with sources and confidence, read at build time instead of searching.

    entry = handbook.entry("wall_telephone_rotary")          # or by an alias / category
    handbook.size_m(entry, "dial_wheel", "width")          # -> (0.076, "low", source) or None
    handbook.material(entry, "hooks")                       # -> (roughness, metallic, class)
"""
import json
import os

PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                    "factory", "reference_handbook.json")
CONFIDENCE = {"high": 3, "medium": 2, "low": 1, "estimate": 0}
_DATA = None


def data():
    global _DATA
    if _DATA is None:
        _DATA = json.load(open(PATH))
    return _DATA


def entry(name):
    objs = data()["objects"]
    if name in objs:
        return dict(objs[name], name=name)
    for k, v in objs.items():
        if name in v.get("aka", []):
            return dict(v, name=k)
    return None


def part(entry_, name, kind=None):
    if not entry_:
        return {}
    parts = entry_.get("parts", {})
    return parts.get(name) or (parts.get(kind) if kind else None) or {}


def value(entry_, name, key, kind=None):
    """(value, confidence, source) of a part's field, or None."""
    v = part(entry_, name, kind).get(key)
    if v is None:
        return None
    if isinstance(v, dict):
        return v["value"], v.get("confidence", "estimate"), v.get("source", "")
    return v, "estimate", ""


def size_m(entry_, name, axis, kind=None):
    """A part's real size along width / height / depth in metres, with confidence and source."""
    v = value(entry_, name, axis + "_mm", kind)
    return None if v is None else (v[0] / 1000.0, v[1], v[2])


def material(entry_, name, kind=None, default=0.5):
    cls = part(entry_, name, kind).get("material")
    m = data()["materials"].get(cls) if cls else None
    return (m["roughness"], m["metallic"], cls) if m else (default, 0.0, None)


def trusted(conf, minimum="medium"):
    return CONFIDENCE.get(conf, 0) >= CONFIDENCE[minimum]
