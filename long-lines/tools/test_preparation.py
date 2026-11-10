"""Run in Blender Python with Hull dependencies on PYTHONPATH."""
import json
import tempfile
import unittest
from pathlib import Path
from PIL import Image, ImageDraw
from propkit.components.dimensions import from_height
from propkit.components.masks import masked_crop
from propkit.components.preparation import prepare


class PreparationTests(unittest.TestCase):
    def test_independent_drawing_scales(self):
        self.assertEqual(from_height([100, 200], [75, 100], .4), [.2, .3, .4])
        for value in (0, -1, float('nan'), True):
            with self.assertRaises(ValueError):
                from_height([100, 200], [75, 100], value)

    def test_hole_survives_and_mask_alignment_is_checked(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'mask.png'
            mask = Image.new('L', (40,40))
            draw = ImageDraw.Draw(mask)
            draw.rectangle((5,5,34,34), fill=255)
            draw.rectangle((12,12,27,27), fill=0)
            mask.save(path)
            m, _, bounds = masked_crop(Image.new('RGB',(40,40)), path, [0,0,40,40])
            self.assertFalse(m[15,15])
            self.assertEqual(bounds,(5,5,35,35))
            with self.assertRaises(ValueError):
                masked_crop(Image.new('RGB',(50,40)),path,[0,0,40,40])

    def test_prepare_emits_reviewable_manifest(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            image=Image.new('RGB',(120,100),'white')
            draw=ImageDraw.Draw(image)
            draw.rectangle((10,10,45,85),fill='black')
            draw.rectangle((70,10,100,85),fill='black')
            image.save(root/'sheet.png')
            recipe={'name':'test','reference':'sheet.png','triangle_limit':100,'parts':[
                {'name':'body','method':'polygon','budget':100,'height_anchor':{'metres':.4,'source':'assumed test'},
                 'views':{'front':[0,0,60,100],'right':[60,0,120,100]}}]}
            (root/'recipe.json').write_text(json.dumps(recipe))
            path=prepare(root/'recipe.json',root/'prepared')
            cfg=json.loads(Path(path).read_text())
            self.assertTrue(cfg['dimensions_assumed'])
            self.assertEqual(cfg['parts'][0]['dimensions'][2],.4)
            self.assertTrue((root/'prepared/body_regions.png').exists())
            self.assertTrue(Path(cfg['parts'][0]['reference']).is_file())


if __name__=='__main__':
    unittest.main()
