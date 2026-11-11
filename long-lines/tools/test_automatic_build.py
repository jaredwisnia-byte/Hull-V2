"""Run under Blender; optional -- RESULT.json verifies a complete real run."""
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parent))
import factory
import sheet_blobs


class BuildGuards(unittest.TestCase):
    def test_assembly_references_are_compared_for_parts_orders(self):
        order={'layout':'parts','views_folder':'example','assembly':'whole'}
        self.assertEqual(factory.reference_views(order),os.path.join(factory.SRC,'example','whole'))
        self.assertEqual(factory.reference_views({'views_folder':'example'}),os.path.join(factory.SRC,'example'))
        self.assertIsNone(factory.reference_views({}))

    def test_failed_build_does_not_package_previous_model(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            image=root/'image.png'; image.write_bytes(b'input')
            order=root/'order.json'; order.write_text(json.dumps({'name':'old','assumptions':[]}))
            old=root/'old'/'old.glb'; old.parent.mkdir(); old.write_bytes(b'old model')
            os.utime(old,(1,1))
            report={'status':'ready_to_build','work_order':str(order)}
            with patch.object(sheet_blobs,'automatic',return_value=report), \
                 patch.object(factory,'LIB',str(root)), \
                 patch.object(factory,'build',return_value={'pass':False,'fails':['manufacturing failed'],'metrics':{}}), \
                 patch.object(factory.bake,'export_textured') as export:
                result=factory.automatic_build(image,root/'output')
            export.assert_not_called()
            self.assertEqual(result['status'],'needs_review')
            self.assertNotIn('model',result)


def artifact_acceptance(path):
    result=json.loads(path.read_text())
    expected_status='needs_review' if result.get('inference_warnings') else 'complete'
    assert result['status']==expected_status and result['qa']['pass'],result
    assert not result['runtime_llm']
    assert hashlib.sha256(Path(result['input_image']).read_bytes()).hexdigest()==result['input_sha256']
    metrics=result['qa']['metrics']
    assert set(metrics['silhouette_iou'])=={'front','back','left','right','top'}
    assert metrics['normal_disagreement']==0
    for key in ('model','blend','render'):
        assert Path(result[key]).is_file(),key
    raw=Path(result['model']).read_bytes()
    assert raw[:4]==b'glTF'
    size=struct.unpack('<I',raw[12:16])[0]
    document=json.loads(raw[20:20+size])
    triangles=sum(document['accessors'][p['indices']]['count']//3
                  for mesh in document['meshes'] for p in mesh['primitives'])
    assert triangles==metrics['tris'],(triangles,metrics['tris'])
    assert len(document.get('images',[]))>=3
    assert all('bufferView' in im for im in document['images'])
    order=json.loads((path.parent/'intake/manufacture/work-order.json').read_text())
    measured=factory.load_order(order['name'])['measured']
    assert len(measured['gaps_mm'])==len(order['parts'])-1
    assert all(g['gap_mm'] is not None and g['gap_mm']<=4 and g['touching']>=.4 for g in measured['gaps_mm'])
    # A complete artifact must be rejected if its reference comparisons disappear.
    with tempfile.TemporaryDirectory() as empty:
        missing=factory.qa.check(order['name'],empty,order['class'],trim_order=order)
    assert not missing['pass']
    assert any('reference comparison missing' in f for f in missing['fails'])
    print('ARTIFACT ACCEPTANCE PASS:',triangles,'triangles, embedded maps, all attachments, five reference comparisons')


if __name__=='__main__':
    args=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(BuildGuards)
    passed=unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful()
    if passed and args:
        artifact_acceptance(Path(args[0]).resolve())
    sys.exit(0 if passed else 1)
