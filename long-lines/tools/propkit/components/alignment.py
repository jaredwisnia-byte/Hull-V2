"""Rigid component alignment from three or more corresponding 3D landmarks."""
import numpy as np


def solve(source, target, tolerance):
    a, b = np.asarray(source, dtype=float), np.asarray(target, dtype=float)
    if a.shape != b.shape or a.ndim != 2 or a.shape[1] != 3 or len(a) < 3 or not np.isfinite(a).all() or not np.isfinite(b).all():
        raise ValueError("alignment needs at least three finite matching 3D landmarks")
    if not np.isfinite(tolerance) or tolerance <= 0:
        raise ValueError("alignment tolerance must be positive")
    ac, bc = a-a.mean(0), b-b.mean(0)
    if np.linalg.matrix_rank(ac, tol=1e-8) < 2 or np.linalg.matrix_rank(bc, tol=1e-8) < 2:
        raise ValueError("alignment landmarks must not be collinear")
    u, _, vt = np.linalg.svd(ac.T @ bc)
    correction = np.eye(3)
    correction[2, 2] = np.linalg.det(vt.T @ u.T)
    rotation = vt.T @ correction @ u.T
    translation = b.mean(0)-rotation @ a.mean(0)
    error = float(np.linalg.norm(a @ rotation.T+translation-b, axis=1).max())
    if error > tolerance:
        raise ValueError(f"attachment landmarks disagree: {error:.6f} m > {tolerance:.6f} m")
    matrix = np.eye(4)
    matrix[:3,:3], matrix[:3,3] = rotation, translation
    return matrix, error
