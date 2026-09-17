import unittest

from pipeline_mcp.bio.a3m import compute_conservation
from pipeline_mcp.bio.a3m import conservation_scores
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

    def test_weighted_conservation_changes_threshold_fixed_positions(self) -> None:
        a3m = """>query
ACDE
>hit1
ACDE
>hit2
ACDE
>hit3
ACKE
"""
        scores_unweighted = conservation_scores(a3m)
        self.assertAlmostEqual(scores_unweighted[2], 2.0 / 3.0, places=6)

        scores_weighted = conservation_scores(a3m, weights=[0.5, 0.5, 1.0])
        self.assertAlmostEqual(scores_weighted[2], 0.5, places=6)

        cons_unweighted = compute_conservation(a3m, tiers=[0.6], mode="threshold")
        cons_weighted = compute_conservation(a3m, tiers=[0.6], mode="threshold", weights=[0.5, 0.5, 1.0])
        self.assertEqual(cons_unweighted.fixed_positions_by_tier[0.6], [1, 2, 3, 4])
        self.assertEqual(cons_weighted.fixed_positions_by_tier[0.6], [1, 2, 4])


if __name__ == "__main__":
    unittest.main()


# --- 보존도 정보량 --------------------------------------------------------------

def test_distinct_score_count_spots_a_flat_profile():
    from pipeline_mcp.bio.a3m import distinct_score_count

    assert distinct_score_count([1.0, 1.0, 1.0]) == 1
    assert distinct_score_count([1.0, 0.5, 1.0]) == 2
    assert distinct_score_count([]) == 0


def test_query_only_msa_gives_a_degenerate_profile():
    """서열 하나뿐인 MSA 는 모든 위치를 100% 보존으로 만든다.

    그러면 tier 분할이 동점 처리로 앞에서부터 잘려 보존도와 무관한 N-말단
    구간이 된다. anjv72_kribb.re.kr_mrna10837 에서 실제로 그렇게 됐다.
    """
    from pipeline_mcp.bio.a3m import conservation_is_degenerate

    assert conservation_is_degenerate([1.0] * 439) is True
    assert conservation_is_degenerate([1.0, 0.4, 0.9]) is False
    # 비어 있으면 판정할 게 없다 - 퇴화로 부르지 않는다.
    assert conservation_is_degenerate([]) is False
