"""Evidence-selected construction regions using existing hulls and spline lofts.

Physical region IDs are shared by all views. Unidentified ornament remains hull
geometry; this does not invent semantic labels or hidden manufacturing joints.
"""
import numpy as np
from scipy import interpolate
from . import profile_inference


def infer(views, height_m, guide_band=None):
    from .silhouette import silhouette
    profiles = {}
    for name, path in views.items():
        if name in ('front', 'back', 'left', 'right'):
            mask, image = silhouette(path)
            profiles[name] = profile_inference.elevation(mask, image)
    if 'front' not in profiles or not ('right' in profiles or 'left' in profiles):
        return None
    report, _ = profile_inference.analyse(profiles, guide_band)
    if report['status'] != 'fitted':
        return None
    report['features'] = profile_inference.feature_identities(report)
    report['height_m'] = height_m
    report['scale_status'] = 'inherited sizing estimate'
    band = report['band']
    # Exact continuous cover: inferred shaft boundaries split all other bands.
    cuts = sorted(set([0., 1., *band] + [v for r in report['regions'] for v in r['v']
                                         if v < band[0] or v > band[1]]))
    report['regions'] = [{'id': f'region_{i:03d}', 'v': [a, b],
                          'model': 'spline_shaft' if a == band[0] and b == band[1] else 'visual_hull'}
                         for i, (a, b) in enumerate(zip(cuts, cuts[1:])) if b > a]
    return {'profiles': profiles, 'report': report}


def shaft_vertices(model, stations=12):
    """A spline loft with explicit vertices around channel shoulders and floors."""
    report = model['report']
    H = report['height_m']
    band = report['band']
    profiles = model['profiles']
    side = 'right' if 'right' in profiles else 'left'
    features = report['features']
    angles = list(np.linspace(0, 2 * np.pi, 33)[:-1])
    for feature in features:
        angles.extend((feature['angle'] + feature['width'] * offset) % (2 * np.pi)
                      for offset in (-1, -.6, -.3, 0, .3, .6, 1))
    angles = np.asarray(sorted(set(round(value, 6) for value in angles)))
    v = np.linspace(*band, stations)
    radii = []
    end_centers = []
    for pair in (('front', 'back'), (side, 'left' if side == 'right' else 'right')):
        low = []
        high = []
        for index, view in enumerate(pair):
            if view not in profiles:
                continue
            profile = profiles[view]
            h = len(profile['width'])
            rows = np.arange(h) / h
            radius = np.interp(v, rows, profile['width']) / h * H / 2
            center = np.interp(
                v, rows, profile['center'] - (profile['image_width'] - 1) / 2) / h * H
            roll = np.radians(report['camera_axis_fit']
                              ['roll_degrees'].get(view, 0))
            # Rectify the image-plane roll in the chosen orthographic gauge.
            # Preserve the jointly observed nonlinear bend separately below.
            radius *= np.cos(roll)
            center -= np.tan(roll) * (v - np.mean(band)) * H
            if view in ('back', 'left'):
                center = -center
            low.append(center - radius)
            high.append(center + radius)
        lo = np.max(low, axis=0)
        hi = np.min(high, axis=0)
        spline = interpolate.UnivariateSpline(
            v, (hi - lo) / 2, s=stations * (H / h * .3)**2)
        radii.append(np.maximum(spline(v), H / h))
        c = (lo + hi) / 2
        end_centers.append(np.linspace(c[0], c[-1], stations))
    rx, ry = radii
    r = 1 / np.sqrt((np.cos(angles)[None, :] / rx[:, None])**2 +
                    (np.sin(angles)[None, :] / ry[:, None])**2)
    base = r.copy()
    validation = []
    closure = np.sin(np.linspace(0, np.pi, stations))**.4
    for feature in features:
        difference = np.angle(np.exp(1j * (angles - feature['angle'])))
        shape = np.exp(-(difference / max(feature['width'] * .6, .025))**4)
        depth = 2 * np.minimum(rx, ry) * feature['depth_fraction']
        r -= depth[:, None] * shape[None, :] * closure[:, None]
        center = int(np.argmin(abs(difference)))
        validation.append({'id': feature['id'], 'expected_depth_m': float(np.median(depth * closure)),
                           'represented_depth_m': float(np.median(depth * shape[center] * closure)),
                           'sign': 'recessed', 'cross_view_support': feature['cross_view_support']})
    # Retain nonlinear bend, but anchor the interfaces to the parent's axis.
    t = np.linspace(-1, 1, stations)
    coefficients = np.asarray(report['camera_axis_fit']['bend_coefficients'])
    centers = coefficients @ np.stack([t * t - 1, t**3 - t]) * \
        H + np.asarray(end_centers)
    vertices = np.stack([r * np.cos(angles)[None, :] + centers[0, :, None],
                         r * np.sin(angles)[None, :] + centers[1, :, None],
                         np.broadcast_to(((1 - v) * H)[:, None], r.shape)], axis=-1)
    faces = []
    n = len(angles)
    for row in range(stations - 1):
        for col in range(n):
            a = row * n + col
            b = row * n + (col + 1) % n
            faces.append((a, a + n, b + n, b))
    faces.append(tuple(range(n)))
    faces.append(tuple(range(stations * n - 1, (stations - 1) * n - 1, -1)))
    report['feature_validation'] = validation
    report['spline_profile'] = {'stations': stations, 'angular_vertices': n,
                                'radius_samples_m': [rx.tolist(), ry.tolist()],
                                'center_samples_m': centers.tolist(), 'angle_samples': angles.tolist(),
                                'basis': 'cubic smoothing B-spline'}
    return vertices.reshape(-1, 3), faces


def refine_dense_shaft(obj, model):
    """Give the normal-bake source the same fitted shaft as the low-poly model."""
    if obj is None:
        return
    vertices, _ = shaft_vertices(model)
    stations = model['report']['spline_profile']['stations']
    n = model['report']['spline_profile']['angular_vertices']
    surface = vertices.reshape(stations, n, 3)
    v = np.linspace(*model['report']['band'], stations)
    center = np.asarray(
        model['report']['spline_profile']['center_samples_m']).T
    angles = np.asarray(model['report']['spline_profile']['angle_samples'])
    # Interpolate the sampled closed contour, retaining its winding.
    angles = (angles % (2 * np.pi))
    ordering = np.argsort(angles)
    angles = angles[ordering]
    surface = surface[:, ordering]
    angles = np.r_[angles[-1] - 2 * np.pi, angles, angles[0] + 2 * np.pi]
    surface = np.concatenate(
        [surface[:, -1:], surface, surface[:, :1]], axis=1)
    co = np.array([tuple(vertex.co) for vertex in obj.data.vertices])
    z = 1 - co[:, 2] / model['report']['height_m']
    selected = (z >= v[0]) & (z <= v[-1])
    x0 = np.interp(z[selected], v, center[:, 0])
    y0 = np.interp(z[selected], v, center[:, 1])
    theta = np.arctan2(co[selected, 1] - y0,
                       co[selected, 0] - x0) % (2 * np.pi)
    points = np.c_[z[selected], theta]
    for axis in (0, 1):
        field = interpolate.RegularGridInterpolator(
            (v, angles), surface[:, :, axis], bounds_error=False, fill_value=None)
        co[selected, axis] = field(points)
    obj.data.vertices.foreach_set('co', co.ravel())
    obj.data.update()


def manufacture(obj, model, name):
    """Clip complementary construction bands; replace only the fitted shaft.
    Each region is independently simplified/painted; original core list updated.
    """
    import bpy
    import bmesh
    from . import core
    H = model['report']['height_m']
    built = []
    for region in model['report']['regions']:
        if region['model'] == 'spline_shaft':
            vertices, faces = shaft_vertices(model)
            mesh = bpy.data.meshes.new(region['id'])
            mesh.from_pydata(vertices, [], faces)
            part = core.link(bpy.data.objects.new(
                name + '_' + region['id'], mesh))
            part['preserve_profile_features'] = True
        else:
            part = obj.copy()
            part.data = obj.data.copy()
            part.name = name + '_' + region['id']
            bpy.context.scene.collection.objects.link(part)
            core.PARTS.append(part)
            bm = bmesh.new()
            try:
                bm.from_mesh(part.data)
                for height, normal in (((1 - region['v'][0]) * H, (0, 0, 1)),
                                       ((1 - region['v'][1]) * H, (0, 0, -1))):
                    bmesh.ops.bisect_plane(bm, geom=list(bm.verts) + list(bm.edges) + list(bm.faces),
                                           plane_co=(0, 0, height), plane_no=normal, clear_outer=True, dist=1e-7)
                boundary = [edge for edge in bm.edges if edge.is_boundary]
                if boundary:
                    # This station splits an already solid visual hull. Fill
                    # only simple material cross-sections; never cap nested voids.
                    from .sectioning import closed_contours
                    for height in ((1 - region['v'][0]) * H, (1 - region['v'][1]) * H):
                        edges = [edge for edge in boundary if all(
                            abs(v.co.z - height) < 1e-5 for v in edge.verts)]
                        if edges:
                            lines = np.array(
                                [[tuple(v.co)[:2] for v in edge.verts] for edge in edges])
                            loops, open_components = closed_contours(
                                lines, tolerance=1e-6)
                            if len(loops) != 1 or open_components:
                                raise ValueError(
                                    'Construction cut has ambiguous/non-solid material topology')
                            bmesh.ops.holes_fill(bm, edges=edges, sides=0)
                bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
                bm.to_mesh(part.data)
            finally:
                bm.free()
        part['physical_region_id'] = region['id']
        part['hull_frame'] = obj['hull_frame']
        core.smooth(part, 35)
        built.append(part)
    if obj in core.PARTS:
        core.PARTS.remove(obj)
    bpy.data.objects.remove(obj, do_unlink=True)
    return built
