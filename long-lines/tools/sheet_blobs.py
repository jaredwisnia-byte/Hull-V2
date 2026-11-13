"""Find every drawn object on a parts sheet, then crop the ones a spec names into part views.

    blender -b --factory-startup -P tools/sheet_blobs.py -- list SHEET.png OUT_overlay.png
    blender -b --factory-startup -P tools/sheet_blobs.py -- crop SHEET.png SPEC.json NAME
    python tools/sheet_blobs.py auto SHEET.png OUT_DIR

list: objects are the sheet's coloured drawings; section labels (grey tags with text), titles and divider
lines are left out (low colour saturation, or thin). Prints "id x0 y0 x1 y1" per object, numbered left to
right, top to bottom, and writes an overlay with the numbers, so a person (or Claude) only has to say
which number is which part's view.

crop: SPEC is {"part": {"view": id, ...}, ...} with ids from list (or [x0, y0, x1, y1] boxes). Writes
assets/source_textures/NAME/<part>/v_<view>.png on black, plus h_<view>.png for background-coloured holes
(carved solid, never painted; cut through in a part of the "parts" layout), as split_parts_sheet does.
"""
import json
import os
import sys
import re
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

VIEW_LABELS = {v.upper(): v for v in ('front', 'back', 'left', 'right', 'top', 'bottom')}
VIEW_LABELS.update({'THREE-QUARTER':'perspective', 'ISOMETRIC':'perspective', 'REAR DIAGONAL':'perspective'})


def recognized_labels(sheet):
    """Local OCR, loaded only for automatic intake. No LLM or coordinate prompts."""
    from rapidocr import RapidOCR
    result = RapidOCR()(str(sheet))
    labels = []
    if result.txts is None:
        return labels
    for text, score, points in zip(result.txts, result.scores, result.boxes):
        text = text.strip().upper()
        box = [int(points[:,0].min()), int(points[:,1].min()), int(points[:,0].max()), int(points[:,1].max())]
        if score >= .8 and len(re.sub('[^A-Z]', '', text)) >= 3:
            labels.append({'text':text, 'confidence':float(score), 'box':box,
                           'view':VIEW_LABELS.get(text)})
    return labels


def visual_regions(a, labels):
    """Recover dark/transparent drawings without the legacy saturation filter."""
    height, width = a.shape[:2]
    left = np.median(a[:,:6], axis=1)
    right = np.median(a[:,-6:], axis=1)
    fraction = np.linspace(0,1,width)[None,:,None]
    background = left[:,None,:]*(1-fraction)+right[:,None,:]*fraction
    mask = np.abs(a-background).sum(2) > 32
    for label in labels:
        x0,y0,x1,y1=label['box']
        if y1-y0 < height*.06:
            mask[max(0,y0-3):min(height,y1+4),max(0,x0-3):min(width,x1+4)] = False
    # Separator lines define sections, not object silhouettes.
    horizontal = ndimage.binary_opening(mask, structure=np.ones((1,max(20,width//3)),bool))
    # A divider must be nearly achromatic; preserve coloured straight object edges.
    neutral = a.max(2)-a.min(2) < 15
    dividers = horizontal & neutral
    mask &= ~ndimage.binary_dilation(dividers, iterations=2)
    mask = ndimage.binary_closing(mask, iterations=3)
    components,n = ndimage.label(mask)
    boxes=[]
    for index,sl in enumerate(ndimage.find_objects(components),1):
        y,x=sl
        h,w=y.stop-y.start,x.stop-x.start
        if h < height*.04 or w < width*.015 or (components[sl]==index).sum() < 250:
            continue
        boxes.append([x.start,y.start,x.stop,y.stop])
    # Join overlapping outlines and nearby detached pieces of a drawing.
    merged=True
    while merged:
        merged=False
        for i,A in enumerate(boxes):
            for j in range(i+1,len(boxes)):
                B=boxes[j]
                dx=max(0,max(A[0],B[0])-min(A[2],B[2]))
                dy=max(0,max(A[1],B[1])-min(A[3],B[3]))
                ox=min(A[2],B[2])-max(A[0],B[0])
                oy=min(A[3],B[3])-max(A[1],B[1])
                if (ox>0 and oy>0) or (dx<=4 and oy>.5*min(A[3]-A[1],B[3]-B[1])) or (dy<=10 and ox>.5*min(A[2]-A[0],B[2]-B[0])):
                    boxes[i]=[min(A[0],B[0]),min(A[1],B[1]),max(A[2],B[2]),max(A[3],B[3])]
                    boxes.pop(j); merged=True; break
            if merged:
                break
    boxes.sort(key=lambda b:(b[1],b[0]))
    return boxes, dividers


def visual_match(template, scene):
    """SIFT + affine RANSAC correspondence; returns evidence, never a forced pose."""
    import cv2
    detector=cv2.SIFT_create(nfeatures=1600)
    t=cv2.cvtColor(np.asarray(template),cv2.COLOR_RGB2GRAY)
    s=cv2.cvtColor(np.asarray(scene),cv2.COLOR_RGB2GRAY)
    kt,dt=detector.detectAndCompute(t,None)
    ks,ds=detector.detectAndCompute(s,None)
    if dt is None or ds is None or len(dt)<4 or len(ds)<4:
        return None
    pairs=cv2.BFMatcher().knnMatch(dt,ds,k=2)
    good=[p[0] for p in pairs if len(p)==2 and p[0].distance < .7*p[1].distance]
    if len(good)<4:
        return None
    src=np.float32([kt[m.queryIdx].pt for m in good])
    dst=np.float32([ks[m.trainIdx].pt for m in good])
    cv2.setRNGSeed(0)
    transform,inliers=cv2.estimateAffinePartial2D(src,dst,method=cv2.RANSAC,ransacReprojThreshold=3)
    if transform is None or inliers is None:
        return None
    count=int(inliers.sum())
    coverage=float(np.ptp(src[inliers.ravel().astype(bool)],axis=0).prod()/max(1,t.shape[0]*t.shape[1])) if count else 0
    return {'inliers':count,'matches':len(good),'inlier_fraction':count/len(good),
            'source_coverage':coverage,'affine_2d':transform.tolist(),
            'score':float(count*min(1,coverage*4))}


def caption_regions(boxes, labels, image_height):
    """Separate adjacent drawings when independent captions share one mask blob."""
    result = [list(box) for box in boxes]
    captions = [label for label in labels if label['view'] is not None]
    changed = True
    while changed:
        changed = False
        for index, box in enumerate(result):
            nearby = [label for label in captions
                      if box[0] < (label['box'][0]+label['box'][2])/2 < box[2]
                      and -image_height*.02 <= label['box'][1]-box[3] <= image_height*.12]
            nearby.sort(key=lambda label: (label['box'][0]+label['box'][2])/2)
            if len(nearby) < 2:
                continue
            centers = [(label['box'][0]+label['box'][2])/2 for label in nearby]
            split = int(round((centers[0]+centers[1])/2))
            if min(split-box[0], box[2]-split) < (box[2]-box[0])*.18:
                continue
            result[index:index+1] = [[box[0],box[1],split,box[3]],
                                     [split,box[1],box[2],box[3]]]
            changed = True
            break
    return result


def assign_companion_captions(regions, labels, image_height):
    """Name uncaptioned detail drawings from nearby headings or view captions.

    This records a candidate physical part. Matching and the part graph still
    decide whether it belongs in an assembly; a caption alone never builds it.
    """
    def part_name(text):
        text = re.sub(r'\s*\((?:FRONT|BACK|LEFT|RIGHT|SIDE)(?:\s+DETAIL)?\)\s*$',
                      '', text.upper()).strip(' :')
        if not text or text in VIEW_LABELS or text in ('DETAIL', 'PART'):
            return None
        return re.sub('[^a-z0-9]+', '_', text.lower()).strip('_')

    def caption_part(label):
        text = label['text']
        if re.search(r'\((?:FRONT|BACK|LEFT|RIGHT|SIDE)(?:\s+DETAIL)?\)\s*$', text):
            name = part_name(text)
            if name:
                return name
        elif not re.match(r'^(?:FRONT|BACK|LEFT|RIGHT|SIDE)\s*\(DETAIL\)$', text):
            return None
        # The direction can be on its own OCR line below the part name.
        above = [item for item in labels if item is not label
                 and abs((item['box'][0] + item['box'][2]) / 2 -
                         (label['box'][0] + label['box'][2]) / 2) < image_height * .09
                 and -image_height * .005 <= label['box'][1] - item['box'][3] < image_height * .04
                 and part_name(item['text'])]
        if above:
            return part_name(min(above, key=lambda item: label['box'][1] - item['box'][3])['text'])
        return 'unnamed_detail' if 'DETAIL' in text else None

    detail_heads = sorted((label for label in labels if label['text'].strip() == 'DETAIL:'),
                          key=lambda label: label['box'][0])
    panels = []
    for head in detail_heads:
        following = [label for label in labels if label is not head
                     and abs(label['box'][0] - head['box'][0]) < image_height * .04
                     and -image_height * .02 <= label['box'][1] - head['box'][3] < image_height * .045
                     and part_name(label['text'])]
        if following:
            title = min(following, key=lambda label: label['box'][1])
            panels.append((head['box'][0], head['box'][1], part_name(title['text'])))

    for region in regions:
        if region['view'] is not None:
            continue
        x0, y0, x1, y1 = region['box']
        center = (x0 + x1) / 2
        matching = [panel for index, panel in enumerate(panels)
                    if panel[0] <= center < (panels[index + 1][0] if index + 1 < len(panels) else float('inf'))
                    and y0 >= panel[1] - image_height * .1]
        if matching:
            region.update(part=matching[-1][2], status='companion_heading_candidate')
            continue
        if region['part'] != 'assembly':
            continue
        candidates = [label for label in labels
                      if x0 <= (label['box'][0] + label['box'][2]) / 2 <= x1
                      and -image_height * .02 <= label['box'][1] - y1 <= image_height * .12
                      and caption_part(label)]
        if candidates:
            label = min(candidates, key=lambda item: abs(item['box'][1] - y1))
            region.update(part=caption_part(label), status='companion_caption_candidate')
    return regions


def automatic(sheet, output):
    """Image-only inspection stage. Ambiguous views stay unresolved, not guessed."""
    sheet=Path(sheet).resolve()
    output=Path(output).resolve()
    output.mkdir(parents=True,exist_ok=True)
    image=Image.open(sheet).convert('RGB')
    a=np.asarray(image).astype(int)
    labels=recognized_labels(sheet)
    boxes,dividers=visual_regions(a,labels)
    boxes=caption_regions(boxes,labels,image.height)
    # Detect horizontal section boundaries from long divider support.
    lines=np.nonzero(dividers.sum(1)>image.width*.4)[0]
    cuts=[]
    for y in lines:
        if not cuts or y-cuts[-1]>8:
            cuts.append(int(y))
    def band(y):
        return sum(y>cut for cut in cuts)
    # Branding printed within a drawing is not a section heading.
    headings=[label for label in labels if label['view'] is None
              and band(label['box'][1]) > 0 and not any(
        box[0] <= (label['box'][0]+label['box'][2])/2 <= box[2]
        and box[1] <= (label['box'][1]+label['box'][3])/2 <= box[3]
        for box in boxes)]
    regions=[]
    for i,box in enumerate(boxes):
        x0,y0,x1,y1=box
        b=band((y0+y1)/2)
        candidates=[h for h in headings if band(h['box'][1])==b and h['box'][1]<y0]
        # Heading panels are separated by vertical rules; choose the closest
        # preceding heading along the row, never a fixed object-specific layout.
        preceding=[h for h in candidates if h['box'][0] <= (x0+x1)/2]
        heading=max(preceding,key=lambda h:h['box'][0]) if preceding else None
        part=re.sub('[^a-z0-9]+','_',heading['text'].lower()).strip('_') if heading else 'assembly'
        regions.append({'id':i,'box':box,'part':part,'view':None,'status':'unresolved', 'section':b})
    # Captioned assembly views: match each caption to the nearest drawing above it.
    for label in (l for l in labels if l['view'] is not None):
        x0,y0,x1,y1=label['box']; cx=(x0+x1)/2
        candidates=[r for r in regions if r['part']=='assembly' and r['view'] is None
                    and r['box'][0]<=cx<=r['box'][2]
                    and -image.height*.02 <= y0-r['box'][3] <= image.height*.12]
        if not candidates:
            continue
        region=min(candidates,key=lambda r:y0-r['box'][3])
        region.update(view=label['view'],status='caption_assigned',confidence=label['confidence'])
    assign_companion_captions(regions, labels, image.height)
    assembly=[r for r in regions if r['part']=='assembly' and r['view'] not in (None,'perspective')]
    cv=__import__('cv2'); cv.setNumThreads(1)
    from propkit.vision import DenseVision, compact_parts
    from propkit.vision_order import generate
    _, background = load(sheet)
    engine = DenseVision(output.parent / 'models', background)
    for region in regions:
        if region['part']=='assembly':
            continue
        matches=[]
        for target in assembly:
            result=engine.match(image.crop(region['box']),image.crop(target['box']))
            if result:
                matches.append(dict(result,view=target['view'],assembly_region=target['id']))
        matches.sort(key=lambda m:m['score'],reverse=True)
        region['dense_matches']=matches
    compact=compact_parts(image,regions,assembly,engine)
    report={'image':str(sheet),'input_mode':'image_only','runtime_llm':False,'labels':labels,
            'regions':regions,'compact_parts':compact,'status':'needs_review',
            'limitations':['Caption vocabulary supplies semantic part names.',
                           'Absolute size is inferred from physical priors and is not a measurement.',
                           'Hidden-face orientation uses recorded geometric hypotheses.']}
    from propkit.part_graph import (assembly_envelopes, from_report,
                                    infer_surface_contacts, export_ownership)
    report['physical_part_graph']=infer_surface_contacts(
        from_report(report), assembly_envelopes(image, regions, background))
    report['source_pixel_ownership']=export_ownership(report,image,background,output/'ownership')
    try:
        order=generate(report,image,background,output/'manufacture')
        order['physical_part_graph']=report['physical_part_graph']
        order['source_pixel_ownership']=report['source_pixel_ownership']
        evidence=json.loads((output/'manufacture'/'vision-report.json').read_text())
        from propkit.drawing_traces import infer_sheet_regions
        report['source_drawings'] = infer_sheet_regions(
            sheet, evidence['records'], regions, output/'source-drawings')
        order['source_drawings'] = report['source_drawings']
        (output/'manufacture'/'work-order.json').write_text(json.dumps(order,indent=2))
        report['work_order']=str(output/'manufacture'/'work-order.json')
        report['status']='ready_to_build'
        for name,record in evidence['records'].items():
            for view,identifier in record.get('views',{}).items():
                region=next(r for r in regions if r['id']==identifier)
                region.setdefault('assigned_views',[]).append(view)
                region.update(view=region.get('view') or view,status='joint_visual_and_geometry_assignment')
        for region in regions:
            if region['part']!='assembly' and region['view'] is None:
                region['status']='alternate_hidden_surface_evidence'
    except ValueError as exc:
        report['failure']=str(exc)
    spec={}
    overlay=image.copy(); draw=ImageDraw.Draw(overlay)
    for region in regions:
        accepted=region['view'] is not None and region['view']!='perspective'
        color='lime' if accepted else 'orange'
        draw.rectangle(region['box'],outline=color,width=3)
        text=f"{region['id']}: {region['part']} / {region['view'] or '?'}"
        draw.text((region['box'][0],region['box'][1]),text,fill=color,stroke_width=1,stroke_fill='black')
        image.crop(region['box']).save(output/f"region_{region['id']:02d}.png")
        if accepted:
            spec.setdefault(region['part'],{})[region['view']]=region['box']
    unresolved=[r['id'] for r in regions if r['view'] is None and r['status']!='alternate_hidden_surface_evidence']
    report['unresolved']=unresolved
    overlay.save(output/'detected-regions.png')
    (output/'sheet-spec.partial.json').write_text(json.dumps(spec,indent=2),encoding='utf-8')
    (output/'intake-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({'status':report['status'],'regions':len(regions),'unresolved':len(unresolved),'output':str(output)}))
    return report


def load(sheet):
    a = np.asarray(Image.open(sheet).convert("RGB")).astype(int)
    border = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])
    vals, counts = np.unique((border // 8) * 8, axis=0, return_counts=True)
    bg = np.median(a.reshape(-1, 3)[np.abs(a.reshape(-1, 3) - vals[np.argmax(counts)]).sum(1) < 24], axis=0)
    return a, bg


def objects(a, bg):
    diff = np.abs(a - bg).sum(2)
    mx, mn = a.max(2), a.min(2)
    sat = (mx - mn) / np.maximum(mx, 1)
    drawn = diff > 36
    lab, n = ndimage.label(ndimage.binary_closing(drawn, iterations=2))
    out = []
    for i, sl in enumerate(ndimage.find_objects(lab), 1):
        m = lab[sl] == i
        h, w = m.shape
        if m.sum() < 150 or min(h, w) < 6:
            continue                                         # specks, divider lines
        s_ = float(np.median(sat[sl][m]))
        if s_ < 0.18:
            continue                                         # grey label tags, titles, rules
        out.append([sl[1].start, sl[0].start, sl[1].stop, sl[0].stop])
    # merge pieces of one drawing (a view drawn in a few parts with gaps under 3 px; neighbouring
    # views on a sheet can sit 5 px apart)
    merged = True
    while merged:
        merged = False
        for i in range(len(out)):
            for j in range(i + 1, len(out)):
                A, B = out[i], out[j]
                if A[0] - 3 <= B[2] and B[0] - 3 <= A[2] and A[1] - 3 <= B[3] and B[1] - 3 <= A[3]:
                    out[i] = [min(A[0], B[0]), min(A[1], B[1]), max(A[2], B[2]), max(A[3], B[3])]
                    out.pop(j)
                    merged = True
                    break
            if merged:
                break
    rows = sorted(out, key=lambda b: b[1])
    lines, cur = [], []
    for b in rows:                                           # reading order: rows by overlap, then x
        if cur and b[1] > max(c[3] for c in cur) - 0.3 * (b[3] - b[1]):
            lines.append(cur)
            cur = []
        cur.append(b)
    if cur:
        lines.append(cur)
    return [b for line in lines for b in sorted(line, key=lambda b: b[0])]


def crop(a, bg, box, pad=6):
    x0, y0, x1, y1 = box
    c = a[y0:y1, x0:x1].copy()
    drawn = np.abs(c - bg).sum(2) > 36
    lab, n = ndimage.label(ndimage.binary_closing(drawn, iterations=2))
    sizes = ndimage.sum(drawn, lab, range(1, n + 1))
    keep = np.isin(lab, [i + 1 for i, s_ in enumerate(sizes) if s_ >= 0.05 * sizes.max()]) & drawn
    filled = ndimage.binary_fill_holes(ndimage.binary_closing(keep, iterations=2))
    holes = ndimage.binary_opening(filled & ~ndimage.binary_dilation(keep, iterations=1)
                                   & (np.abs(c - bg).sum(2) <= 36), iterations=1)
    c[~filled] = 0
    out = np.zeros((c.shape[0] + 2 * pad, c.shape[1] + 2 * pad, 3), np.uint8)
    out[pad:-pad, pad:-pad] = c
    hm = np.zeros(out.shape[:2], bool)
    hm[pad:-pad, pad:-pad] = holes
    return out, hm


def main(argv):
    cmd, sheet = argv[0], argv[1]
    if cmd == 'auto':
        report = automatic(sheet, argv[2])
        return 2 if report['status'] == 'needs_review' else 0
    a, bg = load(sheet)
    if cmd == "list":
        obs = objects(a, bg)
        im = Image.open(sheet).convert("RGB")
        d = ImageDraw.Draw(im)
        for i, b in enumerate(obs):
            d.rectangle(b, outline=(255, 0, 255), width=2)
            d.text((b[0] + 3, b[1] + 2), str(i), fill=(0, 255, 255))
            print("%d %d %d %d %d" % (i, *b))
        im.save(argv[2])
        return
    spec, name = json.load(open(argv[2])), argv[3]
    obs = objects(a, bg)
    for part, views in spec.items():
        if part.startswith("_"):
            continue
        d_ = os.path.join(ROOT, "assets", "source_textures", name, part)
        os.makedirs(d_, exist_ok=True)
        for v, ref in views.items():
            box = obs[ref] if isinstance(ref, int) else ref
            img, holes = crop(a, bg, box)
            Image.fromarray(img).save(os.path.join(d_, "v_%s.png" % v))
            hp = os.path.join(d_, "h_%s.png" % v)
            if holes.sum() > 20:
                Image.fromarray(holes.astype(np.uint8) * 255).save(hp)
            elif os.path.exists(hp):
                os.remove(hp)
            print("CROP", part, v, img.shape[:2], "holes", int(holes.sum()))


if __name__ == "__main__":
    sys.exit(main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]))
