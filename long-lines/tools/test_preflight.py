"""Blender: conflicting views are reported without editing source evidence."""
import hashlib
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from PIL import Image  # noqa: E402
from propkit.preflight import inspect_order  # noqa: E402

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
