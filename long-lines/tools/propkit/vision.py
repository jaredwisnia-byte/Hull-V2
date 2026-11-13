"""Local learned image correspondence for the existing reference-sheet intake."""
import hashlib
import os
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

MODEL_URL = 'https://huggingface.co/onnx-community/dinov2-small/resolve/ef1fb10/onnx/model.onnx'
MODEL_HASH = 'f22797eabf810a75e41de68d378541ebea372122b25c4ce3ef25ff618250c20a'


def model_file(cache):
    path = Path(os.environ.get('HULL_VISION_MODEL',
                Path(cache)/'dinov2-small.onnx'))
    if not path.exists():
        import requests
        path.parent.mkdir(parents=True, exist_ok=True)
        response = requests.get(MODEL_URL, timeout=120)
        response.raise_for_status()
        payload = response.content
        if hashlib.sha256(payload).hexdigest() != MODEL_HASH:
            raise ValueError('vision-model checksum mismatch')
        path.write_bytes(payload)
    if hashlib.sha256(path.read_bytes()).hexdigest() != MODEL_HASH:
        raise ValueError('vision-model checksum mismatch')
    return path


class DenseVision:
    def __init__(self, cache, background):
        import onnxruntime as ort
        options = ort.SessionOptions()
        options.intra_op_num_threads = 4
        self.session = ort.InferenceSession(
            str(model_file(cache)), options, providers=['CPUExecutionProvider'])
        self.background = np.asarray(background, dtype=float)
        self.cache = {}

    def features(self, image, longest):
        key = (hashlib.sha256(image.tobytes()).hexdigest(), image.size, longest)
        if key in self.cache:
            return self.cache[key]
        scale = longest/max(image.size)
        width = max(28, int(round(image.width*scale/14))*14)
        height = max(28, int(round(image.height*scale/14))*14)
        a = np.asarray(image.resize((width, height),
                       Image.Resampling.LANCZOS)).astype(np.float32)
        mask = np.abs(a-self.background).sum(2) > 32
        valid = cv2.resize(mask.astype(float), (width//14,
                           height//14), interpolation=cv2.INTER_AREA) > .3
        value = ((a/255-[.485, .456, .406])/[.229, .224, .225]
                 ).transpose(2, 0, 1)[None].astype(np.float32)
        descriptors = self.session.run(None, {'pixel_values': value})[0][0, 1:]
        descriptors /= np.maximum(np.linalg.norm(descriptors,
                                  axis=1, keepdims=True), 1e-8)
        y, x = np.mgrid[:height//14, :width//14]
        positions = np.stack(((x.ravel()+.5)*image.width/(width//14),
                             (y.ravel()+.5)*image.height/(height//14)), axis=1)
        result = (descriptors[valid.ravel()], positions[valid.ravel()])
        self.cache[key] = result
        return result

    def match(self, template, scene):
        source, xy = self.features(template, 224)
        target, uv = self.features(scene, 448)
        if min(len(source), len(target)) < 4:
            return None
        similarities = source@target.T
        nearest = similarities.argmax(1)
        reverse = similarities.argmax(0)
        indices = np.arange(len(source))
        keep = (reverse[nearest] == indices) & (
            similarities[indices, nearest] > .45)
        src = xy[keep].astype(np.float32)
        dst = uv[nearest[keep]].astype(np.float32)
        if len(src) < 4:
            return None
        cv2.setRNGSeed(0)
        transform, inliers = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC,
                                                         ransacReprojThreshold=max(scene.size)*.025, maxIters=5000, confidence=.995)
        if transform is None or inliers is None:
            return None
        accepted = inliers.ravel().astype(bool)
        count = int(accepted.sum())
        coverage = float(np.ptp(src[accepted], axis=0).prod(
        )/max(1, template.width*template.height)) if count else 0
        corners = np.array([[0, 0, 1], [template.width, 0, 1], [
                           template.width, template.height, 1], [0, template.height, 1]])@transform.T
        box = [float(corners[:, 0].min()), float(corners[:, 1].min()), float(
            corners[:, 0].max()), float(corners[:, 1].max())]
        inside = max(0, min(scene.width, box[2])-max(0, box[0])) * \
            max(0, min(scene.height, box[3])-max(0, box[1]))
        area = max(1, (box[2]-box[0])*(box[3]-box[1]))
        mean = float(similarities[indices[keep][accepted],
                     nearest[keep][accepted]].mean()) if count else 0
        result = {'inliers': count, 'matches': len(src), 'inlier_fraction': count/len(src),
                  'source_coverage': coverage, 'affine_2d': transform.tolist(), 'box': box,
                  'mean_similarity': mean, 'score': float(count*min(1, coverage*4)*mean*inside/area),
                  'method': 'dinov2_dense_correspondence'}
        if count >= 6 and coverage > .12:
            refined = self.refine(template, scene, box, transform)
            if refined:
                result.update(refined)
        return result

    def refine(self, template, scene, box, transform):
        """Refine learned coarse location, without searching tiny unrelated patches."""
        angle = abs(np.degrees(np.arctan2(transform[1, 0], transform[0, 0])))
        if angle > 20:
            return None
        source = np.asarray(template)
        target = np.asarray(scene)
        source_gray = cv2.cvtColor(source, cv2.COLOR_RGB2GRAY)
        target_gray = cv2.cvtColor(target, cv2.COLOR_RGB2GRAY)
        foreground = np.abs(source.astype(float)-self.background).sum(2) > 32
        scale = np.sqrt(abs(np.linalg.det(transform[:, :2])))
        center = np.array([(box[0]+box[2])/2, (box[1]+box[3])/2])
        best = None
        for value in np.linspace(scale*.65, scale*1.25, 24):
            width, height = int(round(template.width*value)
                                ), int(round(template.height*value))
            if min(width, height) < 6 or width > scene.width or height > scene.height:
                continue
            t = cv2.resize(source_gray, (width, height))
            mask = np.uint8(cv2.resize(foreground.astype(
                float), (width, height)) > .4)*255
            scores = cv2.matchTemplate(
                target_gray, t, cv2.TM_CCOEFF_NORMED, mask=mask)
            scores = np.nan_to_num(scores, nan=-1, posinf=-1, neginf=-1)
            y, x = np.mgrid[:scores.shape[0], :scores.shape[1]]
            distance = ((x+width/2-center[0])/max(1, box[2]-box[0]))**2 + \
                ((y+height/2-center[1])/max(1, box[3]-box[1]))**2
            scores = scores-.12*distance
            j = np.unravel_index(int(scores.argmax()), scores.shape)
            score = float(scores[j])
            if best is None or score > best[0]:
                best = (score, int(j[1]), int(j[0]), width, height)
        if best is None:
            return None
        score, x, y, width, height = best
        return {'box': [x, y, x+width, y+height], 'photometric_match': score,
                'affine_2d': [[width/template.width, 0, x], [0, height/template.height, y]]}


def role(name):
    """Part roles from caption vocabulary, not an object-specific part inventory."""
    name = name.lower()
    for words, value in [(('button', 'key'), 'button'), (('knob', 'dial', 'wheel'), 'knob'),
                         (('toggle', 'lever', 'switch'), 'lever'), ((
                             'lid', 'cover', 'cap'), 'lid'),
                         (('housing', 'collar', 'base', 'socket'), 'support'),
                         (('jar', 'cup', 'bottle', 'container', 'vessel'), 'container')]:
        if any(word in name for word in words):
            return value
    return 'part'


def face_color(image, background):
    a = np.asarray(image)
    lab = cv2.cvtColor(a, cv2.COLOR_RGB2LAB).astype(float)
    keep = np.abs(a.astype(float)-background).sum(2) > 32
    values = lab[keep]
    if not len(values):
        return np.median(lab.reshape(-1, 3), axis=0)
    return np.median(values[values[:, 0] >= np.percentile(values[:, 0], 60)], axis=0)


def appearance_components(image, templates, background, compact=True):
    a = np.asarray(image)
    lab = cv2.cvtColor(a, cv2.COLOR_RGB2LAB).astype(float)
    colors = [face_color(t, background) for t in templates]
    distance = np.min([np.linalg.norm((lab-color)*[.25, 1, 1], axis=2)
                      for color in colors], axis=0)
    minimum = min(c[0] for c in colors)*.65
    mask = np.uint8((distance < 22) & (lab[:, :, 0] > minimum))*255
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((2, 2), np.uint8))
    n, labels, stats, centers = cv2.connectedComponentsWithStats(mask)
    result = []
    for x, y, w, h, area in stats[1:]:
        if min(w, h) < 3 or area < 10:
            continue
        if compact and (w > image.width*.22 or h > image.height*.14):
            continue
        result.append(
            {'box': [int(x), int(y), int(x+w), int(y+h)], 'area': int(area)})
    return result


def repeated_row(candidates):
    """Discover repeated controls and count them from the image."""
    best = []
    for candidate in candidates:
        b = candidate['box']
        width = b[2]-b[0]
        height = b[3]-b[1]
        cy = (b[1]+b[3])/2
        row = []
        for other in candidates:
            box = other['box']
            w = box[2]-box[0]
            h = box[3]-box[1]
            if .5 <= w/width <= 2 and .5 <= h/height <= 2 and abs((box[1]+box[3])/2-cy) < max(height, h)*.5:
                row.append(other)
        row.sort(key=lambda r: r['box'][0])
        if len(row) < 3:
            continue
        centers = np.array([(r['box'][0]+r['box'][2])/2 for r in row])
        steps = np.diff(centers)
        if steps.min() < width*.5 or steps.std()/max(1, steps.mean()) > .4:
            continue
        if len(row) > len(best):
            best = row
    return best


def overlap(a, b):
    area = max(0, min(a[2], b[2])-max(a[0], b[0])) * \
        max(0, min(a[3], b[3])-max(a[1], b[1]))
    return area/max(1, min((a[2]-a[0])*(a[3]-a[1]), (b[2]-b[0])*(b[3]-b[1])))


def rectangular_components(image):
    gray = cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2GRAY)
    edges = cv2.morphologyEx(cv2.Canny(gray, 40, 100),
                             cv2.MORPH_CLOSE, np.ones((2, 2), np.uint8))
    contours, _ = cv2.findContours(
        edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    result = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if min(w, h) < 4 or w > image.width*.22 or h > image.height*.14:
            continue
        polygon = cv2.approxPolyDP(
            contour, .04*cv2.arcLength(contour, True), True)
        if len(polygon) == 4 and cv2.isContourConvex(polygon) and cv2.contourArea(polygon) > w*h*.5:
            box = [x, y, x+w, y+h]
            if not any(overlap(box, r['box']) > .8 for r in result):
                result.append({'box': box, 'area': w*h})
    return result


def compact_parts(image, regions, assembly, engine):
    """Find repeated buttons, round dials and levers at their observed image scale."""
    groups = {}
    for region in regions:
        if region['part'] != 'assembly':
            groups.setdefault(region['part'], []).append(region)
    located = {}
    for name, parts in groups.items():
        if role(name) != 'button':
            continue
        templates = [image.crop(p['box']) for p in parts]
        trials = []
        for view in assembly:
            scene = image.crop(view['box'])
            row = repeated_row(appearance_components(
                scene, templates, engine.background))
            if row:
                trials.append((len(row), view, row))
        if trials:
            _, view, row = max(trials, key=lambda t: t[0])
            located[name] = {'view': view['view'], 'assembly_region': view['id'], 'instances': [r['box'] for r in row],
                             'method': 'repeated_appearance_components', 'count': len(row)}
    for name, parts in groups.items():
        if role(name) != 'knob':
            continue
        face = min(parts, key=lambda p: abs(
            np.log((p['box'][2]-p['box'][0])/(p['box'][3]-p['box'][1]))))
        template = image.crop(face['box'])
        color = face_color(template, engine.background)
        descriptor = engine.features(template, 224)[0].mean(0)
        descriptor /= np.linalg.norm(descriptor)
        trials = []
        for view in assembly:
            scene = image.crop(view['box'])
            a = np.asarray(scene)
            gray = cv2.cvtColor(a, cv2.COLOR_RGB2GRAY)
            circles = cv2.HoughCircles(cv2.GaussianBlur(gray, (3, 3), 0), cv2.HOUGH_GRADIENT, 1, 8, param1=70, param2=14,
                                       minRadius=4, maxRadius=max(5, int(scene.width*.18)))
            if circles is None:
                continue
            proposals = []
            for x, y, radius in circles[0]:
                box = [max(0, int(x-radius)), max(0, int(y-radius)), min(scene.width,
                                                                         int(x+radius+1)), min(scene.height, int(y+radius+1))]
                patch = scene.crop(box)
                candidate_color = face_color(patch, engine.background)
                delta = np.linalg.norm((candidate_color-color)*[.3, 1, 1])
                if delta > 30:
                    continue
                proposals.append((delta, box))
            for delta, box in sorted(proposals, key=lambda p: p[0])[:6]:
                patch = scene.crop(box)
                candidate = engine.features(patch, 224)[0].mean(0)
                candidate /= np.linalg.norm(candidate)
                score = float(candidate@descriptor)-delta/150
                if not any(overlap(box, b) > .2 for match in located.values() if match['view'] == view['view'] for b in match['instances']):
                    trials.append((score, view, box))
        if trials:
            score, view, box = max(trials, key=lambda t: t[0])
            located[name] = {'view': view['view'], 'assembly_region': view['id'], 'instances': [box],
                             'method': 'round_shape_and_learned_appearance', 'score': score, 'front_source': face['id']}
    for name, parts in groups.items():
        if role(name) != 'lever':
            continue
        templates = [image.crop(p['box']) for p in parts]
        face = max(parts, key=lambda p: cv2.cvtColor(np.asarray(
            image.crop(p['box'])), cv2.COLOR_RGB2LAB)[:, :, 0].mean())
        templates = [image.crop(face['box'])]
        descriptor = engine.features(image.crop(face['box']), 224)[0].mean(0)
        descriptor /= np.linalg.norm(descriptor)
        trials = []
        for view in assembly:
            peers = [b for match in located.values() if match['view'] == view['view']
                     for b in match['instances']]
            if not peers:
                continue
            peer_center = np.mean([[(b[0]+b[2])/2, (b[1]+b[3])/2]
                                  for b in peers], axis=0)
            scene = image.crop(view['box'])
            candidates = appearance_components(
                scene, templates, engine.background)+rectangular_components(scene)
            candidates = sorted(candidates, key=lambda c: -c['area'])[:24]
            for candidate in candidates:
                box = candidate['box']
                center = np.array([(box[0]+box[2])/2, (box[1]+box[3])/2])
                if any(overlap(box, b) > .15 for b in peers) or np.linalg.norm((center-peer_center)/[scene.width, scene.height]) > .3:
                    continue
                patch = scene.crop(box)
                features = engine.features(patch, 224)[0]
                if not len(features):
                    continue
                vector = features.mean(0)
                vector /= np.linalg.norm(vector)
                score = float(vector@descriptor)
                trials.append((score, view, box))
        if trials:
            score, view, box = max(trials, key=lambda t: t[0])
            located[name] = {'view': view['view'], 'assembly_region': view['id'], 'instances': [box],
                             'method': 'component_appearance_and_control_cluster', 'score': score, 'front_source': face['id']}
    return located
