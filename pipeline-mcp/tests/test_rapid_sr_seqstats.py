from __future__ import annotations

from pathlib import Path
import sys
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "transcoder"))

from rapid_sr.seqstats import (
    composition, mean_pairwise_distance, n_unique, positional_entropy,
)


class EntropyTests(unittest.TestCase):
    def test_identical_sequences_have_zero_entropy(self):
        self.assertEqual(positional_entropy(["AAAA", "AAAA", "AAAA"]), 0.0)

    def test_more_variation_gives_more_entropy(self):
        low = positional_entropy(["AAAA", "AAAC"])
        high = positional_entropy(["AAAA", "CCCC", "DDDD", "EEEE"])
        self.assertGreater(high, low)

    def test_single_sequence_is_not_scored(self):
        self.assertEqual(positional_entropy(["ACDE"]), 0.0)
        self.assertEqual(positional_entropy([]), 0.0)


class DistanceTests(unittest.TestCase):
    def test_identical_set_has_zero_distance(self):
        self.assertEqual(mean_pairwise_distance(["ACDE", "ACDE"]), 0.0)

    def test_fully_different_set_has_distance_one(self):
        self.assertAlmostEqual(mean_pairwise_distance(["AAAA", "CCCC"]), 1.0)

    def test_half_different_is_half(self):
        self.assertAlmostEqual(mean_pairwise_distance(["AACC", "AAAA"]), 0.5)

    def test_uses_shortest_length_without_crashing(self):
        self.assertAlmostEqual(mean_pairwise_distance(["AAAA", "AA"]), 0.0)


class CompositionTests(unittest.TestCase):
    def test_frequencies_sum_to_one_over_known_alphabet(self):
        comp = composition(["ACDEFGHIKLMNPQRSTVWY"])
        self.assertAlmostEqual(sum(v for k, v in comp.items() if k.startswith("aa_")), 1.0)

    def test_hydrophobic_fraction(self):
        self.assertAlmostEqual(composition(["AAAA"])["hydrophobic"], 1.0)
        self.assertAlmostEqual(composition(["DDDD"])["charged"], 1.0)

    def test_n_unique_counts_distinct(self):
        self.assertEqual(n_unique(["AA", "AA", "AC"]), 2)


if __name__ == "__main__":
    unittest.main()
