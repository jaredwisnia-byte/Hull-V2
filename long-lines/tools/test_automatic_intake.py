"""Synthetic CV regressions; the real-sheet trial also exercises actual OCR."""
import unittest
import numpy as np
import cv2
from PIL import Image
from sheet_blobs import visual_regions, visual_match, caption_regions
from propkit.vision import role, repeated_row
from propkit.vision_order import assign, generate


class VisionTests(unittest.TestCase):
    def test_neutral_objects_survive_without_labels(self):
        image=np.full((300,500,3),20,dtype=np.uint8)
        image[30:200,40:160]=100
        image[30:200,250:370]=150
        boxes,_=visual_regions(image.astype(int),[])
        self.assertEqual(len(boxes),2)
        self.assertTrue(any(b[0]<=40 and b[2]>=160 for b in boxes))

    def test_drawings_on_either_side_of_a_rule_stay_separate(self):
        image=np.full((400,500,3),20,dtype=np.uint8)
        image[25:160,50:180]=110
        image[240:370,50:180]=140
        image[195:198,:]=100
        boxes,_=visual_regions(image.astype(int),[])
        self.assertEqual(len(boxes),2)

    def test_adjacent_views_joined_by_mask_are_split_by_captions(self):
        boxes=[[10,10,210,150]]
        labels=[{'view':'left','box':[45,155,75,170]},
                {'view':'right','box':[145,155,185,170]}]
        self.assertEqual(len(caption_regions(boxes,labels,200)),2)

    def test_known_visual_transform(self):
        rng=np.random.default_rng(8)
        template=np.full((180,180,3),35,dtype=np.uint8)
        for _ in range(100):
            x,y=rng.integers(10,170,2)
            cv2.circle(template,(int(x),int(y)),int(rng.integers(2,6)),tuple(int(v) for v in rng.integers(80,250,3)),-1)
        transform=cv2.getRotationMatrix2D((90,90),17,.8)
        transform[:,2]+=[65,55]
        scene=cv2.warpAffine(template,transform,(320,300),borderValue=(35,35,35))
        result=visual_match(Image.fromarray(template),Image.fromarray(scene))
        self.assertIsNotNone(result)
        self.assertGreaterEqual(result['inliers'],8)
        points=np.array([[30,30,1],[150,30,1],[30,150,1]])
        predicted=points@np.asarray(result['affine_2d']).T
        expected=points@transform.T
        self.assertLess(np.linalg.norm(predicted-expected,axis=1).max(),2)

    def test_featureless_regions_are_not_forced_to_match(self):
        image=Image.new('RGB',(100,100),'gray')
        self.assertIsNone(visual_match(image,image))

    def test_repeated_controls_are_counted_not_assumed(self):
        for count in (4,7):
            with self.subTest(count=count):
                boxes=[{'box':[20+i*18,40,30+i*18,52]} for i in range(count)]
                boxes.append({'box':[20,100,30,112]})
                self.assertEqual(len(repeated_row(boxes)),count)

    def test_irregular_controls_are_not_a_repeated_row(self):
        boxes=[{'box':[x,40,x+10,52]} for x in (0,12,100)]
        self.assertEqual(repeated_row(boxes),[])

    def test_support_caption_wins_over_container_word(self):
        self.assertEqual(role('jar_base_blade_housing'),'support')
        self.assertEqual(role('glass_jar'),'container')
        self.assertEqual(role('push_button_switch'),'button')
        self.assertEqual(role('unrecognized_shape'),'part')

    def test_joint_assignment_uses_distinct_drawings(self):
        parts=[{'id':1,'dense_matches':[{'view':'front','score':10},{'view':'back','score':9}]},
               {'id':2,'dense_matches':[{'view':'front','score':8},{'view':'back','score':1}]}]
        result=assign(parts,['front','back'])
        self.assertEqual(result['front']['id'],2)
        self.assertEqual(result['back']['id'],1)

    def test_incomplete_sheet_is_flagged_without_inventing_parts(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(ValueError,'five labelled'):
                generate({'regions':[]},Image.new('RGB',(100,100)),np.zeros(3),folder)

    def test_generic_order_retains_unresolved_components(self):
        import tempfile, json
        image=Image.new('RGB',(400,400),(20,20,20))
        boxes=[[20,20,100,160],[120,20,200,160],[220,20,300,160],
               [20,200,100,340],[120,200,200,340]]
        regions=[{'id':i,'part':'assembly','view':view,'box':box}
                 for i,(view,box) in enumerate(zip(
                     ('front','back','left','right','top'),boxes))]
        regions.append({'id':5,'part':'knob','view':None,'box':[220,200,270,250]})
        with tempfile.TemporaryDirectory() as folder:
            order=generate({'image':'radio.png','regions':regions,'compact_parts':{}},
                           image,np.array([20,20,20]),folder)
            self.assertEqual(order['line'],'hull')
            self.assertEqual(len(order['views']),5)
            self.assertGreater(order['height_m'], .2)
            self.assertEqual(order['class'],'medium')
            evidence=json.loads((__import__('pathlib').Path(folder)/'vision-report.json').read_text())
            self.assertEqual(evidence['unresolved_component_groups'],['knob'])


if __name__=='__main__':
    unittest.main()
