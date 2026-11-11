"""Physical identity from projections, without an object-role vocabulary."""
import unittest
import tempfile
from pathlib import Path
import numpy as np
from PIL import Image
from propkit.part_graph import associate, ownership, export_ownership


def observation(identifier, view, box, label='unfamiliar mechanism', source=None):
    return {'id': identifier, 'view': view, 'box_unit': box, 'confidence': .9,
            'label': label, 'source_region': source or identifier}


class PartGraphTests(unittest.TestCase):
    def test_repeated_instances_are_not_duplicated_by_an_ambiguous_side_view(self):
        observations = [observation('f1', 'front', [.1, .5, .2, .6]),
                        observation('f2', 'front', [.7, .5, .8, .6]),
                        observation('t1', 'top', [.1, .7, .2, .8]),
                        observation('t2', 'top', [.7, .7, .8, .8]),
                        observation('side', 'right', [.2, .5, .3, .6])]
        graph = associate(observations)
        self.assertEqual(len(graph['parts']), 2)
        self.assertTrue(all(p['spatially_constrained']
                        for p in graph['parts']))
        self.assertEqual(len(graph['ambiguous_observations']), 1)
        self.assertEqual(
            len(graph['ambiguous_observations'][0]['candidate_physical_ids']), 2)

    def test_overlapping_companion_matches_are_one_physical_observation(self):
        graph = associate([observation('one', 'front', [.2, .3, .5, .7]),
                           observation('duplicate', 'front', [.21, .3, .51, .7])])
        self.assertEqual(len(graph['parts']), 1)
        self.assertEqual(
            len(graph['parts'][0]['observations'][0]['duplicate_observations']), 1)

    def test_unnamed_drawings_can_share_identity_through_two_views(self):
        observations = []
        for source in ('drawing_a', 'drawing_b'):
            observations += [observation(source + 'f', 'front', [.2, .3, .5, .7], label=None, source=source),
                             observation(source + 't', 'top', [.2, .4, .5, .6], label=None, source=source)]
        graph = associate(observations)
        self.assertEqual(len(graph['parts']), 1)
        self.assertTrue(graph['parts'][0]['spatially_constrained'])

    def test_conflicting_pixel_owners_stay_unknown(self):
        foreground = np.ones((12, 12), bool)
        a = np.zeros_like(foreground)
        a[2:8, 2:8] = True
        b = np.zeros_like(foreground)
        b[5:10, 5:10] = True
        pixels, report = ownership([(3, a, .9), (7, b, .88)], foreground)
        self.assertEqual(pixels[3, 3], 3)
        self.assertEqual(pixels[9, 9], 7)
        self.assertEqual(pixels[6, 6], -2)
        self.assertEqual(pixels[0, 0], -1)
        self.assertGreater(report['conflicting_pixels'], 0)

    def test_single_weak_claim_is_not_an_ownership_conflict(self):
        foreground = np.ones((3, 3), bool)
        pixels, report = ownership([(4, foreground, .04)], foreground)
        self.assertTrue((pixels == 4).all())
        self.assertEqual(report['conflicting_pixels'], 0)

    def test_source_mask_warp_keeps_the_declared_assembly_frame(self):
        pixels = np.zeros((20, 40, 3), np.uint8)
        pixels[2:6, 2:6] = 200
        pixels[7:11, 24:28] = 200
        pixels[14:16, 34:36] = 200
        report = {'regions': [{'id': 1, 'box': [0, 0, 10, 10], 'part': 'unknown drawing'},
                              {'id': 2, 'box': [20, 0, 40, 20], 'part': 'assembly', 'view': 'front'}],
                  'physical_part_graph': {'parts': [{'id': 'physical_0000', 'observations': [
                      {'source_region': 1, 'assembly_region': 2, 'affine_2d': [[1, 0, 2], [0, 1, 5]], 'confidence': .9}]}]}}
        with tempfile.TemporaryDirectory() as temporary:
            output = export_ownership(
                report, Image.fromarray(pixels), [0, 0, 0], temporary)
            with np.load(output['sources']['2']['path']) as data:
                self.assertTrue((data['owners'][7:11, 4:8] == 0).all())
                self.assertEqual(data['owners'][14, 14], -1)
                np.testing.assert_array_equal(
                    data['sheet_box'], [20, 0, 40, 20])
            self.assertFalse(output['used_for_texture_projection'])


if __name__ == '__main__':
    unittest.main()
