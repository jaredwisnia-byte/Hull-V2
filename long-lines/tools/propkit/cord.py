"""Cords and cables: build them straight, then curl them along their path.

A coiled phone cord, a lamp flex, a hose or a spring is one construction with different numbers:
  1. straight: the cord laid along a straight line of its path's length - a plain tube, or for a
     coiled cord a helix (coil diameter and pitch from the reference handbook), as it would lie on a
     bench;
  2. curl: that straight piece bent along the path it takes in the object (traced from the photo:
     where it hangs from the handset and how it curls), every point carried by the path's local frame;
  3. the wire swept along the result as a tube of the wire's thickness, both ends capped.
Sizes come from the reference handbook (wire, coil, pitch); the path from the photo.
"""
import numpy as np


def resample(path, step):
    """Points every `step` metres along a polyline, and the total length."""
    p = np.asarray(path, float)
    seg = np.linalg.norm(np.diff(p, axis=0), axis=1)
    t = np.r_[0, np.cumsum(seg)]
    L = float(t[-1])
    n = max(2, int(np.ceil(L / step)) + 1)
    ts = np.linspace(0, L, n)
    return np.c_[[np.interp(ts, t, p[:, i]) for i in range(3)]].T, ts, L


def frames(p):
    """Tangent, normal, binormal along a polyline by parallel transport (no twisting flips)."""
    T = np.gradient(p, axis=0)
    T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-12)
    a = np.array([0, 1, 0]) if abs(T[0][1]) < 0.9 else np.array([1, 0, 0])
    N = np.zeros_like(p)
    N[0] = np.cross(T[0], a)
    N[0] /= np.linalg.norm(N[0])
    for i in range(1, len(p)):
        n = N[i - 1] - np.dot(N[i - 1], T[i]) * T[i]
        N[i] = n / max(np.linalg.norm(n), 1e-12)
    B = np.cross(T, N)
    return T, N, B


def straight(length, coil_r, pitch, samples_per_turn=6):
    """Step 1: the cord laid straight along z. A coil is a helix of radius coil_r (the radius of the
    wire's centre) and the given pitch; coil_r = 0 is a plain straight cord."""
    if coil_r <= 0:
        z = np.linspace(0, length, 2)
        return np.c_[np.zeros(2), np.zeros(2), z]
    turns = length / pitch
    n = max(8, int(turns * samples_per_turn))
    t = np.linspace(0, length, n)
    th = 2 * np.pi * t / pitch
    return np.c_[coil_r * np.cos(th), coil_r * np.sin(th), t]


def curl(local, path):
    """Step 2: bend a straight piece (x, y around the z axis, z = distance along) onto a path."""
    p, ts, L = resample(path, max(1e-4, min(0.002, 0.01 * np.linalg.norm(np.ptp(np.asarray(path), axis=0)))))
    T, N, B = frames(p)
    z = np.clip(local[:, 2] / max(local[:, 2].max(), 1e-9) * L, 0, L)
    idx = np.clip(np.searchsorted(ts, z), 0, len(ts) - 1)
    return p[idx] + local[:, :1] * N[idx] + local[:, 1:2] * B[idx]


def tube(points, radius, name, segments=6):
    """Step 3: sweep a circle of the wire's radius along the points; capped ends."""
    import bmesh
    import bpy
    from .core import link
    T, N, B = frames(points)
    bm = bmesh.new()
    rings = []
    for i, c in enumerate(points):
        rings.append([bm.verts.new(tuple(c + radius * (np.cos(a) * N[i] + np.sin(a) * B[i])))
                      for a in np.linspace(0, 2 * np.pi, segments, endpoint=False)])
    for ra, rb in zip(rings[:-1], rings[1:]):
        for k in range(segments):
            bm.faces.new((ra[k], ra[(k + 1) % segments], rb[(k + 1) % segments], rb[k]))
    bm.faces.new(rings[0][::-1])
    bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return link(bpy.data.objects.new(name, me))


def make_cord(path, wire_d, coil_d, pitch, name, samples_per_turn=6, segments=6):
    """A cord along `path` (N x 3, metres): straight first, then curled onto the path, then swept.
    coil_d <= wire_d gives a plain (uncoiled) cord. Returns (object, report)."""
    p, ts, L = resample(path, 0.002)
    coil_r = max(0.0, (coil_d - wire_d) / 2)
    line = straight(L, coil_r, pitch, samples_per_turn)
    pts = curl(line, p)
    obj = tube(pts, wire_d / 2, name, segments)
    rep = {"path_length_mm": round(L * 1000, 1), "turns": round(L / pitch, 1) if coil_r > 0 else 0,
           "wire_mm": round(wire_d * 1000, 1), "coil_mm": round(coil_d * 1000, 1), "pitch_mm": round(pitch * 1000, 1),
           "triangles": sum(len(f.vertices) - 2 for f in obj.data.polygons)}
    return obj, rep
