"""Synthetic CV regressions; the real-sheet trial also exercises actual OCR."""
import unittest
import numpy as np
import cv2
from PIL import Image
from sheet_blobs import visual_regions, visual_match


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


if __name__=='__main__':
    unittest.main()
