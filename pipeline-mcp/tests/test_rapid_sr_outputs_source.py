from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "transcoder"))

from rapid_sr.outputs_source import load_output_run


def _make_run(root: Path, *, budget=False, degenerate=False, tier="50"):
    run = root / "gate0_w1_rfd3_2wejA00"
    run.mkdir(parents=True, exist_ok=True)
    (run / "backbones.json").write_text(json.dumps({"backbones": [
        {"id": "rfd3_m0", "source": "rfd3"},
        {"id": "rfd3_m1", "source": "rfd3"},
    ]}))
    t = run / "tiers" / tier
    t.mkdir(parents=True, exist_ok=True)
    if degenerate:
        samples = [{"id": "rfd3_m0:fallback_001", "sequence": "MKT"},
                   {"id": "rfd3_m0:fallback_002", "sequence": "MKT"}]
    else:
        samples = [{"id": "rfd3_m0:sample_1", "sequence": "MKTA"},
                   {"id": "rfd3_m1:sample_1", "sequence": "MKTC"}]
    (t / "proteinmpnn.json").write_text(json.dumps({"samples": samples}))
    ids = [s["id"] for s in samples]
    (t / "soluprot.json").write_text(json.dumps({"scores": {i: 0.7 for i in ids}, "cutoff": 0.0}))
    (t / "af2_scores.json").write_text(json.dumps({
        "scores": {i: 92.0 for i in ids},
        "rmsd_scores": {i: 1.2 for i in ids},
        "failed_ids": [], "prediction_errors": {},
        "candidate_budget_applied": budget,
    }))
    return run


class OutputsSourceTests(unittest.TestCase):
    def test_backbone_id_comes_from_design_id_prefix(self):
        with tempfile.TemporaryDirectory() as tmp:
            recs = {r.design_id: r for r in load_output_run(_make_run(Path(tmp)))}
            self.assertEqual(recs["rfd3_m0:sample_1"].backbone_id, "rfd3_m0")
            self.assertEqual(recs["rfd3_m1:sample_1"].backbone_id, "rfd3_m1")

    def test_source_resolved_from_backbones_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            recs = load_output_run(_make_run(Path(tmp)))
            self.assertEqual({r.backbone_source for r in recs}, {"rfd3"})

    def test_unbiased_run_is_all_candidates(self):
        with tempfile.TemporaryDirectory() as tmp:
            recs = load_output_run(_make_run(Path(tmp), budget=False))
            self.assertTrue(all(r.label_regime == "af2_all_candidates" for r in recs))

    def test_budgeted_run_is_marked_censored(self):
        with tempfile.TemporaryDirectory() as tmp:
            recs = load_output_run(_make_run(Path(tmp), budget=True))
            self.assertTrue(all(r.label_regime == "af2_after_soluprot_filter" for r in recs))

    def test_degenerate_fallback_unit_is_dropped(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(load_output_run(_make_run(Path(tmp), degenerate=True)), [])

    def test_target_id_taken_from_run_name_suffix(self):
        with tempfile.TemporaryDirectory() as tmp:
            recs = load_output_run(_make_run(Path(tmp)))
            self.assertEqual({r.target_id for r in recs}, {"2wejA00"})

    def test_reads_per_backbone_mpnn_when_tier_level_is_absent(self):
        """다중 백본 run 은 tier 레벨에 proteinmpnn.json 이 없고
        proteinmpnn_backbones.json 이 백본별 경로를 가리킨다. 이걸 따라가지 않으면
        모든 서열이 빈 문자열이 되어 특징이 전부 같아진다."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run = root / "gate0_w1_rfd3_2wejA00"
            run.mkdir(parents=True)
            (run / "backbones.json").write_text(json.dumps({"backbones": [
                {"id": "rfd3_m0", "source": "rfd3"}, {"id": "rfd3_m1", "source": "rfd3"},
            ]}))
            tier = run / "tiers" / "50"
            tier.mkdir(parents=True)
            entries = []
            for bid, seq in (("rfd3_m0", "MKTA"), ("rfd3_m1", "MKTC")):
                bdir = run / "backbones" / bid / "tiers" / "50"
                bdir.mkdir(parents=True)
                (bdir / "proteinmpnn.json").write_text(json.dumps({
                    "samples": [{"id": "sample_1", "sequence": seq}]
                }))
                entries.append({"id": bid, "source": "rfd3",
                                "proteinmpnn_json": str(bdir / "proteinmpnn.json")})
            (tier / "proteinmpnn_backbones.json").write_text(
                json.dumps({"backbones": entries})
            )
            ids = ["rfd3_m0:sample_1", "rfd3_m1:sample_1"]
            (tier / "soluprot.json").write_text(
                json.dumps({"scores": {i: 0.7 for i in ids}, "cutoff": 0.0})
            )
            (tier / "af2_scores.json").write_text(json.dumps({
                "scores": {i: 92.0 for i in ids},
                "rmsd_scores": {i: 1.2 for i in ids},
                "failed_ids": [], "prediction_errors": {},
                "candidate_budget_applied": False,
            }))
            recs = {r.design_id: r for r in load_output_run(run)}
            self.assertEqual(len(recs), 2)
            self.assertEqual(recs["rfd3_m0:sample_1"].sequence, "MKTA")
            self.assertEqual(recs["rfd3_m1:sample_1"].sequence, "MKTC")

    def test_records_without_any_sequence_are_dropped(self):
        """서열을 못 찾으면 특징이 전부 같아져 조용히 학습을 망친다. 남기지 않는다."""
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "gate0_w1_rfd3_2wejA00"
            (run / "tiers" / "50").mkdir(parents=True)
            (run / "backbones.json").write_text(json.dumps({"backbones": []}))
            ids = ["rfd3_m0:sample_1"]
            (run / "tiers/50/soluprot.json").write_text(
                json.dumps({"scores": {i: 0.7 for i in ids}})
            )
            (run / "tiers/50/af2_scores.json").write_text(json.dumps({
                "scores": {i: 92.0 for i in ids}, "rmsd_scores": {},
                "failed_ids": [], "prediction_errors": {},
                "candidate_budget_applied": False,
            }))
            self.assertEqual(load_output_run(run), [])

    def test_reads_whichever_tier_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            recs = load_output_run(_make_run(Path(tmp), tier="30"))
            self.assertEqual({r.tier for r in recs}, {"30"})


if __name__ == "__main__":
    unittest.main()
