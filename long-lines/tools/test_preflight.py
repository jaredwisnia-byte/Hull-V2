"""Blender: conflicting views are reported without editing source evidence."""
import hashlib
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parent))
from PIL import Image  # noqa: E402
from propkit.preflight import inspect_order  # noqa: E402
from propkit import reconcile  # noqa: E402

with tempfile.TemporaryDirectory() as folder:
    source = Path(folder) / 'source'
    source.mkdir()
    for name, size in {'front':(90,160), 'back':(45,160), 'right':(45,160), 'top':(90,45)}.items():
        image = Image.new('RGB', (size[0]+16,size[1]+16), 'black')
        image.paste(Image.new('RGB',size,(150,100,60)),(8,8))
        image.save(source/('v_'+name+'.png'))
    before = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir()}
    report = inspect_order({'views_folder':str(source)}, Path(folder), Path(folder)/'proposals')
    after = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir()}
    assert report['status'] == 'needs_review', report
    assert report['proposals']
    assert before == after, 'Source evidence was mutated'
print('PREFLIGHT PASS: contradictory dimensions flagged, source bytes preserved')

with tempfile.TemporaryDirectory() as folder:
    root = Path(folder)
    views = {}
    for name, size in {'front': (80, 120), 'right': (40, 120),
                       'top': (80, 40)}.items():
        image = Image.new('RGB', (size[0] + 16, size[1] + 16), 'black')
        image.paste(Image.new('RGB', size, (150, 100, 60)), (8, 8))
        if name == 'right':
            image.putpixel((10, 10), (220, 150, 80))
        path = root / ('v_' + name + '.png')
        image.save(path)
        views[name] = str(path)
    with patch('propkit.reconcile._corr', side_effect=[0.0, 1.0]):
        fixed, _, _, report = reconcile.run(views, tmp=str(root / 'fixed'))
    frame = report['pixel_frames']['right']
    assert frame['operations'] == ['horizontal_flip'], frame
    assert frame['appearance_modifications'] == [], frame
    assert frame['build_to_source_xy'] == {
        'scale_xy': [-1, 1], 'offset_xy': [55, 0]}, frame
    with Image.open(views['right']) as source, Image.open(fixed['right']) as built:
        assert list(built.getdata()) == list(source.transpose(Image.FLIP_LEFT_RIGHT).getdata())
print('PREFLIGHT PASS: lossless flip records an exact build-to-source pixel map')
