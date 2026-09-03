from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "transcoder"))

from rapid_sr.records import DesignRecord
from rapid_sr.splits import (
    attach_superfamily,
    cath_group,
    group_split,
    leave_one_source_out,
    parse_cath_domain_list,
)

CATH_SAMPLE = """\
#
# comment
#---------------------------------------------------------------------
1oaiA00     1    10     8    10     1     1     1     1     1    59 1.000
2wejA00     3    10    20    40     2     1     1     1   200 15.000
"""


def _rec(bid, target, design_id, source="rfd3"):
    return DesignRecord(
        design_id=design_id, target_id=target, tier="30",
        backbone_id=bid, backbone_source=source, sequence="MKT",
        soluprot=0.6, plddt_af2=90.0, rmsd_af2=1.0,
        label_regime="af2_all_candidates",
    )


class SplitTests(unittest.TestCase):
    def test_parse_builds_four_level_superfamily_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cath-domain-list.txt"
            path.write_text(CATH_SAMPLE)
            mapping = parse_cath_domain_list(path)
            self.assertEqual(mapping["1oaiA00"], "1.10.8.10")
            self.assertEqual(mapping["2wejA00"], "3.10.20.40")
            self.assertEqual(len(mapping), 2)

    def test_attach_superfamily_fills_records(self):
        out = attach_superfamily([_rec("bb1", "1oaiA00", "d1")], {"1oaiA00": "1.10.8.10"})
        self.assertEqual(out[0].superfamily, "1.10.8.10")

    def test_attach_leaves_none_when_unmapped(self):
        out = attach_superfamily([_rec("bb1", "unknown", "d1")], {})
        self.assertIsNone(out[0].superfamily)

    def test_backbone_never_spans_train_and_test(self):
        recs = [_rec(f"bb{i}", f"t{i % 3}", f"d{i}") for i in range(30)]
        folds = list(group_split(recs, n_splits=3, seed=0))
        self.assertGreater(len(folds), 0)
        for fold in folds:
            train_bb = {recs[i].backbone_id for i in fold["train_idx"]}
            test_bb = {recs[i].backbone_id for i in fold["test_idx"]}
            self.assertEqual(train_bb & test_bb, set())

    def test_superfamily_takes_priority_over_target(self):
        recs = [_rec("bbA", "t1", "d1"), _rec("bbB", "t2", "d2"),
                _rec("bbC", "t3", "d3"), _rec("bbD", "t4", "d4")]
        recs = attach_superfamily(
            recs, {"t1": "1.10", "t2": "1.10", "t3": "2.20", "t4": "2.20"}
        )
        for fold in group_split(recs, n_splits=2, seed=0):
            train_sf = {recs[i].superfamily for i in fold["train_idx"]}
            test_sf = {recs[i].superfamily for i in fold["test_idx"]}
            self.assertEqual(train_sf & test_sf, set())

    def test_falls_back_to_target_when_superfamily_missing(self):
        recs = [_rec("bbA", "t1", "d1"), _rec("bbB", "t2", "d2")]
        folds = list(group_split(recs, n_splits=2, seed=0))
        self.assertEqual(len(folds), 2)
        for fold in folds:
            train_t = {recs[i].target_id for i in fold["train_idx"]}
            test_t = {recs[i].target_id for i in fold["test_idx"]}
            self.assertEqual(train_t & test_t, set())

    def test_degenerate_fold_is_skipped_not_returned_empty(self):
        recs = [_rec("bbA", "t1", "d1")]
        self.assertEqual(list(group_split(recs, n_splits=3, seed=0)), [])

    def test_cath_depth_truncates_grouping_level(self):
        """실측: 이 CATH 세트는 superfamily/topology 가 전부 싱글톤이라
        depth=4 group split 은 타겟 단위와 같다. 의미 있는 상위 그룹은
        architecture(depth=2) 뿐이므로 깊이를 조절할 수 있어야 한다."""
        recs = [_rec("bbA", "t1", "d1"), _rec("bbB", "t2", "d2"),
                _rec("bbC", "t3", "d3"), _rec("bbD", "t4", "d4")]
        recs = attach_superfamily(recs, {
            "t1": "1.10.8.10", "t2": "1.10.20.30",
            "t3": "3.40.50.60", "t4": "3.40.1000.10",
        })
        # depth=4 이면 네 그룹, depth=2 이면 두 그룹(1.10 / 3.40)
        self.assertEqual(len({cath_group(r.superfamily, depth=4) for r in recs}), 4)
        self.assertEqual({cath_group(r.superfamily, depth=2) for r in recs}, {"1.10", "3.40"})

    def test_architecture_split_keeps_whole_architecture_on_one_side(self):
        recs = [_rec("bbA", "t1", "d1"), _rec("bbB", "t2", "d2"),
                _rec("bbC", "t3", "d3"), _rec("bbD", "t4", "d4")]
        recs = attach_superfamily(recs, {
            "t1": "1.10.8.10", "t2": "1.10.20.30",
            "t3": "3.40.50.60", "t4": "3.40.1000.10",
        })
        for fold in group_split(recs, n_splits=2, seed=0, cath_depth=2):
            train_arch = {cath_group(recs[i].superfamily, depth=2) for i in fold["train_idx"]}
            test_arch = {cath_group(recs[i].superfamily, depth=2) for i in fold["test_idx"]}
            self.assertEqual(train_arch & test_arch, set())

    def test_cath_group_passes_through_none(self):
        self.assertIsNone(cath_group(None, depth=2))

    def test_leave_one_source_out_yields_one_fold_per_source(self):
        recs = [_rec("bbA", "t1", "d1", source="rfd3"),
                _rec("bbB", "t2", "d2", source="bioemu")]
        folds = list(leave_one_source_out(recs))
        self.assertEqual({f["held_out_source"] for f in folds}, {"rfd3", "bioemu"})
        for fold in folds:
            self.assertFalse(fold["is_degenerate"])

    def test_loso_flags_degenerate_single_source(self):
        recs = [_rec("bbA", "t1", "d1", source="rfd3")]
        folds = list(leave_one_source_out(recs))
        self.assertEqual(len(folds), 1)
        self.assertTrue(folds[0]["is_degenerate"])


if __name__ == "__main__":
    unittest.main()
