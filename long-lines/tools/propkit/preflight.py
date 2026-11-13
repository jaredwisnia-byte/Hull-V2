"""Reuse legacy view reconciliation as a non-destructive evidence inspector.

Proposed transformations are reported, never silently applied to authoritative
source views. This station is not a camera-pose or inverse-CAD solver.
"""
from pathlib import Path


def inspect_order(order, source_root, output):
    from . import reconcile
    if not order.get("views_folder"):
        return {"status": "not_applicable", "decisions": []}
    folder = Path(source_root) / order["views_folder"]
    if order.get("layout") == "parts":
        folder = folder / order.get("assembly", "assembly")
    views = {name: str(folder / ("v_" + name + ".png"))
             for name in ("front", "back", "left", "right", "top", "bottom")
             if (folder / ("v_" + name + ".png")).is_file()}
    if not {"front", "right"} <= set(views) and not {"front", "left"} <= set(views):
        return {"status": "needs_review", "decisions": ["Missing front/side constraints"]}
    _, _, _, report = reconcile.run(views, tmp=str(output))
    report["proposals"] = report.pop("decisions")
    report["status"] = "needs_review" if report["proposals"] else "consistent"
    report["mode"] = "diagnostic_only; proposed source transformations not applied"
    return report
