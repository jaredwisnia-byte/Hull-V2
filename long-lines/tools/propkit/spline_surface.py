"""Error-bounded B-spline height charts and explicit trimmed NURBS documents.

Charts are mathematical surface patches, not separately capped physical parts.
Unit rational weights make these B-splines a subset of NURBS. Fitting a chart
does not establish that the inferred input geometry is physically correct.
"""
import numpy as np
from scipy import sparse
from scipy.interpolate import BSpline
from scipy.sparse.linalg import lsmr


def knots(count, degree=3):
    if count < degree + 1:
        raise ValueError('Too few controls for spline degree')
    return np.r_[np.zeros(degree + 1),
                 np.linspace(0, 1, count - degree + 1)[1:-1], np.ones(degree + 1)]


class Basis:
    """Sparse tensor-product basis at image pixel centres; exact transpose."""

    def __init__(self, shape, controls, degree=3):
        self.shape = tuple(shape)
        self.controls = tuple(controls)
        self.degree = degree
        self.v_knots, self.u_knots = [knots(n, degree) for n in controls]
        self.by = BSpline.design_matrix(
            (np.arange(shape[0]) + .5) / shape[0], self.v_knots, degree)
        self.bx = BSpline.design_matrix(
            (np.arange(shape[1]) + .5) / shape[1], self.u_knots, degree)

    def evaluate(self, coefficients):
        temporary = self.by @ np.asarray(coefficients).reshape(self.controls)
        return np.asarray(self.bx @ temporary.T).T

    def adjoint(self, pixels):
        temporary = self.by.T @ pixels
        return np.asarray(self.bx.T @ temporary.T).T

    def matrix(self):
        return sparse.kron(self.by, self.bx, format='csr')

    def project(self, pixels, mask=None, weights=None):
        valid = np.isfinite(pixels) if mask is None else np.asarray(
            mask, bool) & np.isfinite(pixels)
        if not valid.any():
            raise ValueError('No finite points to fit')
        matrix = self.matrix()[valid.ravel()]
        target = np.asarray(pixels)[valid]
        if weights is not None:
            root = np.sqrt(np.maximum(np.asarray(weights)[valid], 1e-8))
            matrix = matrix.multiply(root[:, None])
            target = target * root
        solution = lsmr(matrix, target, damp=1e-7,
                        atol=1e-8, btol=1e-8, maxiter=500)
        return solution[0].reshape(self.controls), {'stop_code': int(solution[1]), 'iterations': int(solution[2])}


def control_shape(shape, spacing, maximum=96):
    return tuple(min(maximum, max(4, int(np.ceil(n / spacing)) + 3)) for n in shape)


def fit_height(height, mask, tolerance, weights=None, max_controls=96):
    """Refine mathematical charts until measured error passes, or report failure."""
    height = np.asarray(height, float)
    valid = np.asarray(mask, bool) & np.isfinite(height)
    if not valid.any() or tolerance <= 0:
        raise ValueError(
            'Finite surface observations and positive tolerance required')
    history = []
    for spacing in (64, 32, 16, 8, 4):
        basis = Basis(height.shape, control_shape(
            height.shape, spacing, max_controls))
        coefficients, solver = basis.project(height, valid, weights)
        errors = abs(basis.evaluate(coefficients)[valid] - height[valid])
        record = dict(controls=list(basis.controls), rms=float(np.sqrt(np.mean(errors**2))),
                      p99=float(np.percentile(errors, 99)), maximum=float(errors.max()), solver=solver)
        history.append(record)
        accepted = record['p99'] <= tolerance and record['maximum'] <= tolerance * 3
        if accepted or all(n == max_controls for n in basis.controls):
            break
    return {'basis': basis, 'coefficients': coefficients, 'mask': valid,
            'report': {'accepted': bool(accepted), 'tolerance': float(tolerance),
                       'history': history, 'representation': 'trimmed tensor B-spline; NURBS weights=1'}}


def document(fit, origin, u_vector, v_vector, height_vector, units='metres'):
    """An explicit control net, knot vectors and trim loops in a declared frame."""
    from skimage.measure import find_contours
    basis = fit['basis']
    degree = basis.degree
    u = np.array([basis.u_knots[i + 1:i + degree + 1].mean()
                 for i in range(basis.controls[1])])
    v = np.array([basis.v_knots[i + 1:i + degree + 1].mean()
                 for i in range(basis.controls[0])])
    net = (np.asarray(origin) + u[None, :, None] * np.asarray(u_vector)
           + v[:, None, None] * np.asarray(v_vector)
           + fit['coefficients'][..., None] * np.asarray(height_vector))
    hh, ww = fit['mask'].shape
    trims = []
    for contour in find_contours(np.pad(fit['mask'].astype(float), 1), .5):
        uv = np.c_[(contour[:, 1] - .5) / ww, (contour[:, 0] - .5) / hh]
        trims.append(np.clip(uv, 0, 1).tolist())
    return {'format': 'Hull.NURBS.surface.v1', 'units': units, 'surface_kind': 'trimmed_surface_not_solid',
            'degree_u': degree, 'degree_v': degree, 'knots_u': basis.u_knots.tolist(),
            'knots_v': basis.v_knots.tolist(), 'control_points_vu': net.tolist(),
            'weights_vu': np.ones(basis.controls).tolist(), 'trim_loops_uv': trims,
            'fit': fit['report'], 'source_uncertainty': 'inherited; geometric approximation is not depth validation'}


def evaluate_document(surface, u, v):
    """Evaluate the rational surface independently of image resolution."""
    bu = BSpline.design_matrix(np.asarray(
        u), surface['knots_u'], surface['degree_u'])
    bv = BSpline.design_matrix(np.asarray(
        v), surface['knots_v'], surface['degree_v'])
    points = np.asarray(surface['control_points_vu'])
    weights = np.asarray(surface['weights_vu'])
    denominator = np.asarray(bu @ (bv @ weights).T).T
    coordinates = [np.asarray(
        bu @ (bv @ (weights * points[..., axis])).T).T / denominator for axis in range(3)]
    return np.stack(coordinates, axis=2)
