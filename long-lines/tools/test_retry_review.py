"""The second exported build cannot replace a safer first build by accident."""

import unittest

import factory


class RetryReviewTests(unittest.TestCase):
    def setUp(self):
        self.targets = [{'id': 'groove', 'view': 'front',
                         'center_uv': [.5, .5], 'status': 'supported_unmet'}]
        metrics = {'extreme_folds': {'count': 60, 'per_1k': 3.}, 'geometric_components': 1,
                   'tris': 20000, 'silhouette_iou': {'front': .96, 'right': .95}}
        self.before = {'pass': False, 'fails': ['missing shading depth: groove'],
                       'metrics': metrics}
        self.after = {'pass': True, 'fails': [], 'metrics': metrics.copy()}
        self.measured = {'relief': {'local_retry': {'applied': True}}}

    def test_better_export_is_accepted(self):
        review = factory._local_retry_review(
            self.before, self.after, self.targets, self.measured)
        self.assertTrue(review['accepted'], review)

    def test_new_fold_or_failure_rejects_export(self):
        self.after['metrics'] = dict(self.after['metrics'],
                                     extreme_folds={'count': 80, 'per_1k': 4.})
        self.assertFalse(factory._local_retry_review(
            self.before, self.after, self.targets, self.measured)['accepted'])
        self.after['metrics']['extreme_folds'] = {'count': 60, 'per_1k': 3.}
        self.after['fails'] = ['new silhouette mismatch']
        self.assertFalse(factory._local_retry_review(
            self.before, self.after, self.targets, self.measured)['accepted'])

    def test_only_supported_missing_detail_can_trigger_retry(self):
        order = {'line': 'hull', 'automatic_depth': True,
                 'measured': {'relief': {'probe_diagnostics': {'probes': [
                     *self.targets,
                     {'id': 'paint', 'view': 'front', 'center_uv': [.6, .5],
                      'status': 'unsupported_source'}]}}}}
        self.before['fails'].append('missing shading depth: paint')
        self.assertTrue(factory.correct(order, self.before))
        self.assertEqual([item['id'] for item in order['relief_retry']], ['groove'])


if __name__ == '__main__':
    unittest.main()
