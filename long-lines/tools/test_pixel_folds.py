"""Holdout groups cover space without fixed pixel-row phase bias."""
import unittest
import numpy as np
from propkit.pixel_folds import balanced


class FoldContracts(unittest.TestCase):
    def test_each_complete_block_contains_every_fold(self):
        folds = balanced((96, 120))
        for y in range(0, 96, 3):
            for x in range(0, 120, 3):
                np.testing.assert_array_equal(
                    np.sort(folds[y:y + 3, x:x + 3].ravel()), np.arange(9))

    def test_fold_one_is_not_tied_to_one_row_phase(self):
        folds = balanced((96, 120))
        counts = [np.count_nonzero(folds[row::3] == 1) for row in range(3)]
        self.assertGreater(min(counts), 300)
        self.assertLess(max(counts) / min(counts), 1.3)

    def test_odd_shapes_are_deterministic_and_in_range(self):
        folds = balanced((79, 101))
        np.testing.assert_array_equal(folds, balanced((79, 101)))
        self.assertTrue(((folds >= 0) & (folds < 9)).all())


if __name__ == '__main__':
    unittest.main()
