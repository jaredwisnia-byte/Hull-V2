"""Companion drawings must be identified without an object-type vocabulary."""
import unittest

from sheet_blobs import assign_companion_captions


def label(text, box):
    return {'text': text, 'box': box, 'view': None}


def region(index, box):
    return {'id': index, 'box': box, 'part': 'assembly', 'view': None,
            'status': 'unresolved'}


class CompanionCaptionTest(unittest.TestCase):
    def test_inline_and_stacked_direction_captions(self):
        regions = [region(0, [100, 100, 250, 350]),
                   region(1, [400, 100, 550, 350])]
        labels = [label('LEVER (FRONT)', [110, 360, 240, 380]),
                  label('CONTROL KNOB', [410, 350, 540, 370]),
                  label('(SIDE)', [435, 371, 515, 390])]
        assign_companion_captions(regions, labels, 1000)
        self.assertEqual([r['part'] for r in regions], ['lever', 'control_knob'])

    def test_detail_headings_name_nearby_drawings(self):
        regions = [region(0, [240, 760, 600, 950]),
                   region(1, [940, 760, 1120, 950]),
                   region(2, [1180, 860, 1450, 970])]
        labels = [label('DETAIL:', [30, 800, 110, 830]),
                  label('CASSETTE DOOR', [30, 830, 190, 855]),
                  label('DETAIL:', [750, 800, 840, 830]),
                  label('FOLDING HANDLE', [750, 830, 920, 855])]
        assign_companion_captions(regions, labels, 1024)
        self.assertEqual([r['part'] for r in regions],
                         ['cassette_door', 'folding_handle', 'folding_handle'])


if __name__ == '__main__':
    unittest.main()
