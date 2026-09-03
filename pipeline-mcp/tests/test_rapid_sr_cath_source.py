from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "transcoder"))

from rapid_sr.cath_source import load_cath_run


def _write_tier(tier_dir, *, plddt, soluprot, seqs, failed_ids=None, errors=None,
                budget=False, rmsd=None):
    tier_dir.mkdir(parents=True, exist_ok=True)
    (tier_dir / "af2_scores.json").write_text(json.dumps({
        "scores": plddt,
        "rmsd_scores": rmsd or {},
        "failed_ids": failed_ids or [],
        "prediction_errors": errors or {},
        "candidate_budget_applied": budget,
    }))
    (tier_dir / "soluprot.json").write_text(json.dumps({"scores": soluprot, "cutoff": 0.5}))
    (tier_dir / "proteinmpnn.json").write_text(json.dumps({
        "samples": [{"id": k, "sequence": v} for k, v in seqs.items()],
    }))


class CathSourceTests(unittest.TestCase):
    def test_all_zero_unit_yields_none_plddt(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "cath_test_1abcA00"
            _write_tier(
                run / "tiers" / "30",
                plddt={"target:fallback_001": 0.0, "target:fallback_002": 0.0},
                soluprot={"target:fallback_001": 0.6, "target:fallback_002": 0.7},
                seqs={"target:fallback_001": "MKT", "target:fallback_002": "MKA"},
                failed_ids=["target:fallback_001"],
                errors={"target:fallback_001": "executionTimeout exceeded"},
            )
            recs = load_cath_run(run)
            self.assertEqual(len(recs), 2)
            self.assertTrue(all(r.plddt_af2 is None for r in recs))
            self.assertEqual(sorted(r.soluprot for r in recs), [0.6, 0.7])

    def test_valid_unit_keeps_plddt_and_masks_individual_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "cath_val_2xyzB01"
            _write_tier(
                run / "tiers" / "50",
                plddt={"target:1": 97.5, "target:2": 0.0},
                soluprot={"target:1": 0.8, "target:2": 0.4},
                seqs={"target:1": "MKT", "target:2": "MKA"},
            )
            recs = {r.design_id: r for r in load_cath_run(run)}
            self.assertEqual(recs["target:1"].plddt_af2, 97.5)
            self.assertIsNone(recs["target:2"].plddt_af2)

    def test_soluprot_zero_is_kept_as_valid_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "cath_val_3zzzA00"
            _write_tier(
                run / "tiers" / "30",
                plddt={"target:1": 90.0},
                soluprot={"target:1": 0.0},
                seqs={"target:1": "MKT"},
            )
            rec = load_cath_run(run)[0]
            self.assertEqual(rec.soluprot, 0.0)

    def test_regime_reflects_candidate_budget_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "cath_train_3defC00"
            _write_tier(run / "tiers" / "70", plddt={"target:1": 90.0},
                        soluprot={"target:1": 0.9}, seqs={"target:1": "MKT"})
            self.assertEqual(load_cath_run(run)[0].label_regime, "af2_all_candidates")

            run2 = Path(tmp) / "cath_train_4ghiD00"
            _write_tier(run2 / "tiers" / "70", plddt={"target:1": 90.0},
                        soluprot={"target:1": 0.9}, seqs={"target:1": "MKT"}, budget=True)
            self.assertEqual(load_cath_run(run2)[0].label_regime, "af2_after_soluprot_filter")

    def test_target_id_strips_split_prefix(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "cath_test_2wejA00"
            _write_tier(run / "tiers" / "30", plddt={"target:1": 90.0},
                        soluprot={"target:1": 0.9}, seqs={"target:1": "MKT"})
            rec = load_cath_run(run)[0]
            self.assertEqual(rec.target_id, "2wejA00")
            self.assertEqual(rec.backbone_source, "target")
            self.assertEqual(rec.tier, "30")

    def test_bare_mpnn_ids_join_to_prefixed_score_ids(self):
        """실데이터 회귀: proteinmpnn.json 은 id 를 '1','2' 로, soluprot/af2 는
        'target:1' 로 쓴다. 정규화하지 않으면 union 이 두 배로 불고 서열이 라벨에
        전혀 조인되지 않는다."""
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "cath_test_6bbbA00"
            tier = run / "tiers" / "30"
            tier.mkdir(parents=True)
            (tier / "af2_scores.json").write_text(json.dumps({
                "scores": {"target:1": 95.0, "target:2": 91.0},
                "rmsd_scores": {"target:1": 1.0, "target:2": 1.5},
                "failed_ids": [], "prediction_errors": {},
                "candidate_budget_applied": False,
            }))
            (tier / "soluprot.json").write_text(json.dumps({
                "scores": {"target:1": 0.7, "target:2": 0.6}, "cutoff": 0.5,
            }))
            (tier / "proteinmpnn.json").write_text(json.dumps({
                "samples": [{"id": "1", "sequence": "MKT"}, {"id": "2", "sequence": "MKA"}],
            }))
            recs = load_cath_run(run)
            self.assertEqual(len(recs), 2)
            by_id = {r.design_id: r for r in recs}
            self.assertEqual(sorted(by_id), ["target:1", "target:2"])
            self.assertEqual(by_id["target:1"].sequence, "MKT")
            self.assertEqual(by_id["target:2"].sequence, "MKA")

    def test_backbone_id_read_from_backbones_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "cath_test_7cccA00"
            run.mkdir(parents=True)
            (run / "backbones.json").write_text(json.dumps({
                "backbones": [{"id": "target", "source": "target", "primary": True}]
            }))
            tier = run / "tiers" / "30"
            _write_tier(tier, plddt={"target:1": 90.0}, soluprot={"target:1": 0.9},
                        seqs={"1": "MKT"})
            recs = load_cath_run(run)
            self.assertEqual(len(recs), 1)
            self.assertEqual(recs[0].design_id, "target:1")
            self.assertEqual(recs[0].sequence, "MKT")

    def test_proteinmpnn_fallback_unit_is_dropped_entirely(self):
        """ProteinMPNN 이 실패하면 pipeline.py:8231 이 `fallback_NNN` 샘플을
        num_seq_per_tier 개 만드는데, 전부 **동일한 야생형 서열**이다. 설계가
        아니므로 마스킹이 아니라 통째로 버려야 한다. SoluProt 점수는 정상적으로
        붙어 있어서 남겨두면 동일 서열 수천 행이 학습 데이터에 들어간다."""
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "cath_test_8fbkA00"
            wt = "MKTAYIAKQR"
            _write_tier(
                run / "tiers" / "30",
                plddt={"target:fallback_001": 91.0, "target:fallback_002": 91.0},
                soluprot={"target:fallback_001": 0.7, "target:fallback_002": 0.7},
                seqs={"fallback_001": wt, "fallback_002": wt},
            )
            self.assertEqual(load_cath_run(run), [])

    def test_degenerate_unit_without_fallback_ids_is_also_dropped(self):
        """id 규칙이 바뀌어도 잡히도록 서열 중복으로도 판정한다."""
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "cath_test_9dupA00"
            wt = "MKTAYIAKQR"
            _write_tier(
                run / "tiers" / "30",
                plddt={"target:1": 90.0, "target:2": 90.0},
                soluprot={"target:1": 0.7, "target:2": 0.7},
                seqs={"1": wt, "2": wt},
            )
            self.assertEqual(load_cath_run(run), [])

    def test_only_the_degenerate_tier_is_dropped(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "cath_test_7mixA00"
            wt = "MKTAYIAKQR"
            _write_tier(run / "tiers" / "30",
                        plddt={"target:fallback_001": 90.0},
                        soluprot={"target:fallback_001": 0.7},
                        seqs={"fallback_001": wt})
            _write_tier(run / "tiers" / "50",
                        plddt={"target:1": 95.0, "target:2": 93.0},
                        soluprot={"target:1": 0.8, "target:2": 0.6},
                        seqs={"1": "MKTA", "2": "MKTC"})
            recs = load_cath_run(run)
            self.assertEqual({r.tier for r in recs}, {"50"})
            self.assertEqual(len(recs), 2)

    def test_single_design_unit_is_not_treated_as_degenerate(self):
        """서열이 하나뿐인 unit 은 중복이 아니라 표본이 작은 것이다."""
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "cath_test_6oneA00"
            _write_tier(run / "tiers" / "30", plddt={"target:1": 90.0},
                        soluprot={"target:1": 0.7}, seqs={"1": "MKTA"})
            self.assertEqual(len(load_cath_run(run)), 1)

    def test_rmsd_is_carried_through(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "cath_test_5aaaA00"
            _write_tier(run / "tiers" / "30", plddt={"target:1": 90.0},
                        soluprot={"target:1": 0.9}, seqs={"target:1": "MKT"},
                        rmsd={"target:1": 1.42})
            self.assertEqual(load_cath_run(run)[0].rmsd_af2, 1.42)


if __name__ == "__main__":
    unittest.main()
