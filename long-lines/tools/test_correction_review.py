"""A successful local fix must not authorize unrelated destructive changes."""
import unittest
from propkit.correction_review import assess


class CorrectionContracts(unittest.TestCase):
    def review(self, **changes):
        after = dict(component_errors=0, detail_retention=1.,
                     discarded_fraction=.000001)
        after.update(changes)
        return assess('extra components', 'local fragment removal',
                      {'component_errors': 25}, after, improve=['component_errors'],
                      limits={'detail_retention': (.8, 1.), 'discarded_fraction': (0., .001)})

    def test_local_repair_with_full_detail_is_accepted(self):
        self.assertTrue(self.review()['accepted'])

    def test_fixing_components_does_not_authorize_halving_every_groove(self):
        report = self.review(detail_retention=.5)
        self.assertFalse(report['accepted'])
        self.assertEqual(report['decision'], 'reject_and_rollback')
        self.assertIn('detail_retention', ' '.join(report['reasons']))

    def test_large_deletion_is_not_disguised_as_cleaning(self):
        self.assertFalse(self.review(discarded_fraction=.1)['accepted'])

    def test_triggering_problem_must_actually_improve(self):
        self.assertFalse(self.review(component_errors=25)['accepted'])

    def test_missing_or_nonfinite_measurements_fail_closed(self):
        for value in (None, float('nan'), float('inf')):
            self.assertFalse(self.review(detail_retention=value)['accepted'])

    def test_an_optimization_requires_preservation_checks(self):
        result = assess('too many triangles', 'decimate', {'triangles': 1000},
                        {'triangles': 10}, improve=['triangles'], limits={})
        self.assertFalse(result['accepted'])


if __name__ == '__main__':
    unittest.main()
