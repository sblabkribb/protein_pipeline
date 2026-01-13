import unittest

from pipeline_mcp.bio.a3m import compute_conservation
from pipeline_mcp.bio.a3m import filter_a3m
from pipeline_mcp.bio.a3m import msa_quality


class TestA3MConservation(unittest.TestCase):
    def test_quantile_fixed_positions(self) -> None:
        a3m = """>query
ACDE
>hit1
ACDE
>hit2
AC-E
>hit3
ACKE
"""
        cons = compute_conservation(a3m, tiers=[0.5, 0.75], mode="quantile")
        self.assertEqual(cons.query_length, 4)
        self.assertEqual([round(x, 3) for x in cons.scores], [1.0, 1.0, 0.5, 1.0])
        self.assertEqual(cons.fixed_positions_by_tier[0.5], [1, 2])
        self.assertEqual(cons.fixed_positions_by_tier[0.75], [1, 2, 4])

    def test_threshold_fixed_positions(self) -> None:
        a3m = """>query
ACDE
>hit1
ACDE
>hit2
AC-E
>hit3
ACKE
"""
        cons = compute_conservation(a3m, tiers=[0.9], mode="threshold")
        self.assertEqual(cons.fixed_positions_by_tier[0.9], [1, 2, 4])

    def test_msa_quality_and_filtering(self) -> None:
        a3m = """>query
ACDE
>hit1
ACDE
>hit2
AC--
>hit3
----
"""
        q = msa_quality(a3m)
        self.assertEqual(q["query_length"], 4)
        self.assertEqual(q["total_hits"], 3)
        self.assertEqual(q["usable_hits"], 3)

        filtered, report = filter_a3m(a3m, min_coverage=0.6, min_identity=0.6)
        self.assertEqual(report["kept_hits"], 1)
        self.assertEqual(report["dropped_hits"], 2)
        self.assertIn(">hit1", filtered)
        self.assertNotIn(">hit2", filtered)
        self.assertNotIn(">hit3", filtered)


if __name__ == "__main__":
    unittest.main()
