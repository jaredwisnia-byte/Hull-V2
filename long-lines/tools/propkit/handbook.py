"""The reference handbook (factory/reference_handbook.json): what an object type is made of, what its
parts are finished in, and how it meets the human body. It holds no product sizes: the drawing gives
proportions and the body gives scale (propkit/human_scale.py).

    entry = handbook.entry("wall_telephone_rotary")          # or by an alias / category
    handbook.contacts(entry)                                 # how it meets the body
    handbook.material(entry, "hooks")                        # -> (roughness, metallic, class)
"""
import json
import os

PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                    "factory", "reference_handbook.json")
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


def contacts(entry_):
    return (entry_ or {}).get("contacts", [])


def material(entry_, name, kind=None, default=0.5):
    cls = part(entry_, name, kind).get("material")
    m = data()["materials"].get(cls) if cls else None
    return (m["roughness"], m["metallic"], cls) if m else (default, 0.0, None)
