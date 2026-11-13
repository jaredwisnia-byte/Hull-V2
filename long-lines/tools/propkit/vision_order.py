"""Generate the original parts-layout work order from measured visual evidence."""
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from scipy import ndimage
from scipy.optimize import linear_sum_assignment

from .vision import role, face_color


def match_for(region, view):
    return next((m for m in region.get('dense_matches', []) if m['view'] == view), None)


def assign(parts, views):
    scores = np.array([[(match_for(p, v) or {}).get('score', 0)
                      for v in views] for p in parts])
    rows, cols = linear_sum_assignment(-scores)
    return {views[c]: parts[r] for r, c in zip(rows, cols)}


def companion_views(parts, kind, image, background, compact=None):
    """Resolve view families jointly rather than assigning every view independently."""
    if kind == 'container':
        upright = [p for p in parts if (
            p['box'][3]-p['box'][1])/(p['box'][2]-p['box'][0]) > 1.12]
        ends = [p for p in parts if p not in upright]
        return dict(assign(upright, ['front', 'left', 'right', 'back']), **assign(ends, ['top', 'bottom']))
    if kind == 'lid':
        profile = max(parts, key=lambda p: abs(
            np.log((p['box'][2]-p['box'][0])/(p['box'][3]-p['box'][1]))))
        ends = [p for p in parts if p is not profile]
        return dict(assign(ends, ['top', 'bottom']), front=profile, right=profile)
    if kind == 'support':
        profile = max(parts, key=lambda p: (
            p['box'][2]-p['box'][0])/(p['box'][3]-p['box'][1]))
        ends = [p for p in parts if p is not profile]
        # The most structured end face supplies the working interior; other end
        # drawings remain evidence for the underside/alternative hidden surfaces.
        top = max(ends, key=lambda p: cv2.Laplacian(cv2.cvtColor(
            np.asarray(image.crop(p['box'])), cv2.COLOR_RGB2GRAY), cv2.CV_64F).var())
        bottom = max([p for p in ends if p is not top], key=lambda p: (
            match_for(p, 'bottom') or {}).get('score', 0), default=top)
        return {'front': profile, 'right': profile, 'top': top, 'bottom': bottom}
    if compact and compact.get('front_source') is not None:
        front = next(p for p in parts if p['id'] == compact['front_source'])
    elif kind == 'knob':
        front = min(parts, key=lambda p: abs(
            np.log((p['box'][2]-p['box'][0])/(p['box'][3]-p['box'][1]))))
    else:
        front = max(parts, key=lambda p: cv2.cvtColor(np.asarray(
            image.crop(p['box'])), cv2.COLOR_RGB2LAB)[:, :, 0].mean())
    side = next((p for p in parts if p is not front), front)
    return {'front': front, 'right': side}


def support_band(scene, profile, background, container_box):
    a = np.asarray(scene)
    lab = cv2.cvtColor(a, cv2.COLOR_RGB2LAB).astype(float)
    color = face_color(profile, background)
    mask = (np.linalg.norm((lab-color) *
            [.25, 1, 1], axis=2) < 22) & (lab[:, :, 0] > color[0]*.8)
    rows = mask.sum(1) > scene.width*.35
    rows = ndimage.binary_closing(rows, iterations=2)
    labels, n = ndimage.label(rows)
    candidates = []
    for sl in ndimage.find_objects(labels):
        y0, y1 = sl[0].start, sl[0].stop
        if y0 < (container_box[1]+container_box[3])/2 or y1-y0 < 5:
            continue
        y, x = np.nonzero(mask[y0:y1])
        if len(x):
            candidates.append(
                (abs(y1-container_box[3]), [int(x.min()), y0, int(x.max()+1), y1]))
    if not candidates:
        raise ValueError(
            'could not locate support colour band beneath the container')
    return min(candidates, key=lambda c: c[0])[1]


def bounds(a, background, y0=0, y1=None):
    mask = np.abs(a.astype(float)-background).sum(2) > 32
    y1 = a.shape[0] if y1 is None else y1
    y, x = np.nonzero(mask[y0:y1])
    if not len(x):
        raise ValueError('empty inferred body or lid region')
    return [int(x.min()), int(y.min()+y0), int(x.max()+1), int(y.max()+y0+1)]


def generic_order(report, image, background, output, assembly, groups):
    """Build the observed outer body when no supported part grammar exists.

    Component drawings remain evidence, never silently become duplicated geometry.
    """
    from sheet_blobs import crop
    from . import sizing

    source = output/'source'/'assembly'
    source.mkdir(parents=True, exist_ok=True)
    for view, region in assembly.items():
        tile = image.crop(region['box'])
        painting, holes = crop(np.asarray(tile).astype(int), background,
                               [0, 0, tile.width, tile.height])
        Image.fromarray(painting).save(source/f'v_{view}.png')
        if holes.any():
            Image.fromarray(np.uint8(holes)*255).save(source/f'h_{view}.png')

    front = image.crop(assembly['front']['box'])
    # A hand-width for the entire consumer device produced miniature assets and
    # excessive texel density. Three hand-widths is an explicit generic prior,
    # still not a physical measurement or object classification.
    scale = 3*sizing.facts()['hand_width']/1000/front.width
    unresolved = [region['id'] for region in report['regions']
                  if region['id'] not in {item['id'] for item in assembly.values()}
                  and region['view'] != 'perspective']
    asset = 'vision_' + __import__('re').sub('[^a-z0-9]+', '_',
                                            Path(report['image']).stem.lower()).strip('_')
    order = {'name': asset, 'category': 'appliance', 'line': 'hull',
             'status': 'pending', 'class': 'small', 'tex': 2048,
             'views_folder': str(source), 'views': list(assembly),
             'height_m': front.height*scale, 'budget': 'screen', 'rough': .65,
             'hull': {'paint': 'project', 'relief': True},
             'automatic_depth': True, 'vision_generated': True,
             'build_scope': 'outer_body_only',
             'unresolved_component_regions': unresolved,
             'source': report['image'],
             'assumptions': ['Width estimated as three hand-widths; not measured.',
                             'Single observed body only; companion parts are unresolved.']}
    (output/'work-order.json').write_text(json.dumps(order, indent=2))
    (output/'vision-report.json').write_text(json.dumps({
        'mode': 'generic_outer_body', 'image_only': True, 'runtime_llm': False,
        'scale_m_per_pixel': scale, 'unresolved_component_groups': sorted(groups),
        'unresolved_component_regions': unresolved,
        'records': {'assembly': {'views': {view: region['id']
                                           for view, region in assembly.items()}}}
    }, indent=2))
    return order


def generate(report, image, background, output):
    """No user coordinates, dimensions, inventory or placement values are accepted."""
    from sheet_blobs import crop
    from . import sizing, part_rules
    output = Path(output).resolve()
    source = output/'source'
    source.mkdir(parents=True, exist_ok=True)
    regions = report['regions']
    assembly = {r['view']: r for r in regions if r['part'] ==
                'assembly' and r['view'] not in (None, 'perspective')}
    if not {'front', 'left', 'right', 'back', 'top'} <= set(assembly):
        raise ValueError(
            'assembly needs five labelled orthographic directions')
    groups = {}
    for region in regions:
        if region['part'] != 'assembly':
            groups.setdefault(region['part'], []).append(region)
    roles = {name: role(name) for name in groups}
    unknown = [name for name, value in roles.items() if value == 'part']
    if unknown:
        return generic_order(report, image, background, output, assembly, groups)
    containers = [name for name in groups if roles[name] == 'container']
    supports = [name for name in groups if roles[name] == 'support']
    lids = [name for name in groups if roles[name] == 'lid']
    if len(containers) != 1 or len(supports) > 1 or len(lids) > 1:
        return generic_order(report, image, background, output, assembly, groups)
    compact = report['compact_parts']
    for name in groups:
        if roles[name] in ('button', 'knob', 'lever') and name not in compact:
            raise ValueError('no visual location found for '+name)
    mappings = {name: companion_views(parts, roles[name], image, background, compact.get(
        name)) for name, parts in groups.items()}
    front = image.crop(assembly['front']['box'])
    fw, fh = front.size
    vessel = containers[0]
    candidates = [(p, match_for(p, 'front'))
                  for p in groups[vessel] if match_for(p, 'front')]
    selected, match = max(candidates, key=lambda t: t[1]['score'])
    if match['inliers'] < 6:
        raise ValueError('insufficient learned container correspondence')
    vessel_box = list(match['box'])
    boxes = {}
    if supports:
        name = supports[0]
        profile = mappings[name]['front']
        boxes[name] = support_band(front, image.crop(
            profile['box']), background, vessel_box)
        vessel_box[3] = min(vessel_box[3], boxes[name][1])
        body_top = boxes[name][3]
    else:
        body_top = vessel_box[3]
    if lids:
        boxes[lids[0]] = bounds(np.asarray(
            front), background, 0, max(1, int(vessel_box[1])))
        vessel_box[1] = boxes[lids[0]][3]
    boxes[vessel] = vessel_box
    body_front = bounds(np.asarray(front), background, int(body_top))
    # Absolute scale is not observable from one sheet. Use an existing physical
    # control prior and mark it explicitly as an estimate, never a measurement.
    button = next((v for name, v in compact.items()
                  if roles[name] == 'button'), None)
    if button and button['view'] == 'front':
        diameter = sum(part_rules.RULES['button']['diameter'])/2
        scale = diameter/np.median([b[2]-b[0] for b in button['instances']])
        scale_source = 'estimated from sizing-rule button diameter; not measured scale'
    else:
        scale = sizing.facts()['hand_width']/1000/fw
        scale_source = 'estimated from hand-width prior; not measured scale'
    W, H = fw*scale, fh*scale
    side = image.crop(assembly['right']['box'])
    D = H*side.width/side.height
    body_width = (body_front[2]-body_front[0])*scale
    records = {}

    def save_views(name, views, kind):
        folder = source/name
        folder.mkdir(exist_ok=True)
        for view, region in views.items():
            tile = image.crop(region['box'])
            if kind == 'lid' and view in ('front', 'right') and tile.height > tile.width:
                tile = tile.transpose(Image.Transpose.ROTATE_90)
            pixels = np.asarray(tile).astype(int)
            painting, holes = crop(pixels, background, [
                                   0, 0, tile.width, tile.height])
            if kind == 'container' and view in ('front', 'back', 'left', 'right'):
                filled = painting.max(2) > 0
                filled = ndimage.binary_fill_holes(filled)
                counts = filled.sum(0)
                core = np.nonzero(counts >= counts.max()*.85)[0]
                if len(core):
                    holes[:, core.min():core.max()+1] = False
            Image.fromarray(painting).save(folder/f'v_{view}.png')
            hole_path = folder/f'h_{view}.png'
            if holes.any():
                Image.fromarray(np.uint8(holes)*255).save(hole_path)
            elif hole_path.exists():
                hole_path.unlink()
        records[name] = {'role': kind, 'reference_regions': [p['id'] for p in groups.get(name, [])],
                         'views': {v: p['id'] for v, p in views.items()}}
    save_views('assembly', assembly, 'assembly')
    for name, views in mappings.items():
        save_views(name, views, roles[name])
    body = source/'body'
    body.mkdir(exist_ok=True)
    for view, region in assembly.items():
        if view in ('top', 'bottom'):
            continue
        tile = image.crop(region['box'])
        pixels = np.asarray(tile).copy()
        cut = int(round(body_top/fh*tile.height))
        part = pixels[cut:]
        if view in ('left', 'right'):
            mask = np.abs(part.astype(float)-background).sum(2) > 32
            left = np.array(
                [np.nonzero(row)[0].min() if row.any() else 0 for row in mask])
            right = np.array(
                [np.nonzero(row)[0].max()+1 if row.any() else mask.shape[1] for row in mask])
            width = max(3, (len(left)//4) | 1)
            left = ndimage.median_filter(left, size=width, mode='nearest')
            right = ndimage.median_filter(right, size=width, mode='nearest')
            for y, (x0, x1) in enumerate(zip(left, right)):
                part[y, :x0] = background
                part[y, x1:] = background
        painting, holes = crop(part.astype(int), background, [
                               0, 0, part.shape[1], part.shape[0]])
        Image.fromarray(painting).save(body/f'v_{view}.png')

    def world_box(box, depth, center_y=0):
        x0, y0, x1, y1 = box
        return [x0/fw*W-W/2, x1/fw*W-W/2, center_y-depth/2, center_y+depth/2, (1-y1/fh)*H, (1-y0/fh)*H]
    plan = [{'name': 'body', 'views': 'body', 'root': True}]
    parent = 'body'
    for name in supports+containers+lids:
        box = boxes[name]
        width = (box[2]-box[0])*scale
        top = mappings[name].get('top')
        depth = width*((top['box'][3]-top['box'][1]) /
                       (top['box'][2]-top['box'][0])) if top else width
        if roles[name] == 'lid' and vessel in boxes:
            # Lid width/depth use the observed cap and its own plan view.
            depth = max(depth, width*.7)
        vb = world_box(box, depth)
        plan.append({'name': name, 'views': name, 'locate': 'vision', 'vision_box': vb,
                     'attach': {'to': parent, 'face': 'top'}})
        records[name]['observed_front_box'] = box
        parent = name
    catalog = sizing.catalogue()['out']
    body_front_y = -D/2
    for name, location in compact.items():
        if location['view'] != 'front':
            raise ValueError(
                'non-front control orientation needs additional pose support: '+name)
        side = mappings[name].get('right')
        face = mappings[name]['front']
        from .depth_inference import profile_depth
        profiles = {}
        for view in ('left', 'right'):
            profile = source/name/f'v_{view}.png'
            if profile.exists():
                profiles[view] = np.asarray(Image.open(
                    profile).convert('RGB')).max(2) > 0
        for i, box in enumerate(location['instances']):
            h = (box[3]-box[1])*scale
            kind = roles[name]
            rule = catalog.get('knob' if kind == 'knob' else 'button')
            minimum, maximum = (v/1000 for v in rule['depth_mm'])
            inference = profile_depth(h, profiles, (minimum, maximum))
            depth = inference['depth_m']
            vb = world_box(box, depth, body_front_y-depth/2)
            identifier = name if len(
                location['instances']) == 1 else f'{name}_{i+1}'
            plan.append({'name': identifier, 'views': name, 'locate': 'vision', 'vision_box': vb,
                         'depth_inference': inference,
                         'attach': {'to': 'body', 'face': 'front'}})
        records[name]['visual_location'] = location
    asset = 'vision_' + \
        __import__('re').sub('[^a-z0-9]+', '_',
                             Path(report['image']).stem.lower()).strip('_')
    maximum = max(W, D, H)
    standards = json.loads(
        (Path(__file__).resolve().parents[2]/'factory/standards.json').read_text())
    size_class = next((k for k, v in standards['size_classes'].items(
    ) if maximum <= v['max_dim_m']), 'building')
    order = {'name': asset, 'category': 'appliance', 'line': 'hull_parts', 'layout': 'parts', 'status': 'pending',
             'class': size_class, 'tex': 2048, 'views_folder': str(source), 'assembly': 'assembly',
             'body_width_m': body_width, 'sheet_dims_mm': [W*1000, H*1000, D*1000],
             'parts': plan, 'budget': 'screen', 'rough': .65,
             'assumptions': [scale_source, 'Hidden faces use the companion-view geometry hypotheses recorded in vision-report.json.'],
             'vision_generated': True, 'automatic_depth': True, 'source': report['image']}
    (output/'work-order.json').write_text(json.dumps(order, indent=2))
    (output/'vision-report.json').write_text(json.dumps({'scale_m_per_pixel': scale, 'scale_source': scale_source,
                                                         'records': records, 'part_count': len(plan), 'image_only': True, 'runtime_llm': False}, indent=2))
    return order
