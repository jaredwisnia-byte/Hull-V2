"""Plane/mesh intersections and hole-aware section drawings, without Blender.

Open contour networks remain diagnostic lines; they are never silently filled.
"""
from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class CuttingPlane:
    origin: tuple
    normal: tuple
    label: str = "A-A"

    def frame(self):
        origin = np.asarray(self.origin, dtype=float)
        normal = np.asarray(self.normal, dtype=float)
        if origin.shape != (3,) or normal.shape != (3,) or not np.isfinite([origin, normal]).all():
            raise ValueError("Plane requires finite 3D origin and normal")
        length = np.linalg.norm(normal)
        if length < 1e-12:
            raise ValueError("Plane normal cannot be zero")
        normal = normal / length
        axis = np.eye(3)[np.argmin(np.abs(normal))]
        horizontal = np.cross(axis, normal)
        horizontal /= np.linalg.norm(horizontal)
        vertical = np.cross(normal, horizontal)
        return origin, normal, horizontal, vertical


def intersect_mesh(vertices, triangles, plane):
    """Half-open crossing convention avoids duplicate intersections at vertices."""
    origin, normal, horizontal, vertical = plane.frame()
    vertices = np.asarray(vertices, dtype=float)
    segments = []
    for triangle in vertices[np.asarray(triangles, dtype=int)]:
        distances = (triangle - origin) @ normal
        points = []
        for first, second in ((0, 1), (1, 2), (2, 0)):
            a, b = distances[first], distances[second]
            if (a <= 0 < b) or (b <= 0 < a):
                point = triangle[first] + a / \
                    (a - b) * (triangle[second] - triangle[first])
                delta = point - origin
                points.append([delta @ horizontal, delta @ vertical])
        if len(points) == 2 and np.linalg.norm(np.subtract(*points)) > 1e-12:
            segments.append(points)
    return np.asarray(segments).reshape(-1, 2, 2)


def closed_contours(segments, tolerance=1e-7):
    """Join degree-two contour components. Reject ambiguous/nonmanifold branches."""
    adjacency = {}
    coordinates = {}
    for segment in segments:
        keys = [tuple(np.rint(point / tolerance).astype(int))
                for point in segment]
        a, b = keys
        if a == b:
            continue
        for key, point in zip(keys, segment):
            coordinates[key] = point
        adjacency.setdefault(a, set()).add(b)
        adjacency.setdefault(b, set()).add(a)
    remaining = set(adjacency)
    loops = []
    rejected = 0
    while remaining:
        start = min(remaining)
        component = set()
        pending = [start]
        while pending:
            key = pending.pop()
            if key in component:
                continue
            component.add(key)
            pending.extend(adjacency[key] - component)
        remaining -= component
        if any(len(adjacency[key]) != 2 for key in component):
            rejected += 1
            continue
        path = [start]
        previous, current = None, start
        while True:
            following = min(adjacency[current] - {previous})
            if following == start:
                break
            path.append(following)
            previous, current = current, following
        loops.append(np.asarray([coordinates[key] for key in path]))
    return loops, rejected


def section_image(segments, size=360, pixels_per_metre=None):
    """Even/odd fill preserves nested voids. Hatching marks cut material only."""
    from PIL import Image, ImageDraw
    segments = np.asarray(segments).reshape(-1, 2, 2)
    image = Image.new("RGB", (size, size), "white")
    if not len(segments):
        return image, {"closed_loops": 0, "open_components": 0}
    extent = np.ptp(segments.reshape(-1, 2), axis=0)
    scale = pixels_per_metre or (size - 30) / max(extent.max(), 1e-9)
    center = (segments.min(axis=(0, 1)) + segments.max(axis=(0, 1))) / 2

    def pixels(points):
        return (points - center) * [scale, -scale] + size / 2

    loops, rejected = closed_contours(segments)
    material = np.zeros((size, size), dtype=bool)
    for loop in loops:
        mask = Image.new("1", (size, size))
        ImageDraw.Draw(mask).polygon([tuple(point)
                                      for point in pixels(loop)], fill=1)
        material ^= np.asarray(mask, dtype=bool)
    array = np.asarray(image).copy()
    y, x = np.mgrid[:size, :size]
    array[material] = (235, 235, 235)
    array[material & ((x + y) % 12 < 2)] = (115, 115, 115)
    image = Image.fromarray(array)
    draw = ImageDraw.Draw(image)
    for segment in segments:
        draw.line([tuple(point)
                  for point in pixels(segment)], fill="black", width=2)
    return image, {"closed_loops": len(loops), "open_components": rejected,
                   "cut_area_m2_raster_estimate": float(material.sum() / scale**2)}
