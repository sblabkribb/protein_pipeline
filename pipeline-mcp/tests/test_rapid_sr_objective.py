from __future__ import annotations

from pathlib import Path
import sys
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "transcoder"))

from rapid_sr.objective import Decision, Evidence, Objective


class EvidenceTests(unittest.TestCase):
    def test_measurement_requires_a_source(self):
        with self.assertRaises(ValueError):
            Evidence(kind="internal_measurement", statement="AUC 0.725")

    def test_literature_requires_a_source(self):
        with self.assertRaises(ValueError):
            Evidence(kind="literature", statement="temperature helps")

    def test_assumption_may_have_no_source(self):
        ev = Evidence(kind="assumption", statement="사용자가 단량체를 원한다고 가정")
        self.assertEqual(ev.source, "")

    def test_unknown_kind_rejected(self):
        with self.assertRaises(ValueError):
            Evidence(kind="vibes", statement="느낌상 좋음", source="x")


class DecisionTests(unittest.TestCase):
    def test_decision_without_evidence_is_rejected(self):
        with self.assertRaises(ValueError):
            Decision(field_name="sampling_temp", value=0.1, rationale="관행")

    def test_decision_serialises_evidence(self):
        d = Decision(
            field_name="af2_provider", value="colabfold", rationale="기본 검증 경로",
            evidence=(Evidence(kind="internal_measurement", statement="pLDDT 91s/fold",
                               source="af2_length_scaling.json"),),
        )
        out = d.to_dict()
        self.assertEqual(out["field"], "af2_provider")
        self.assertEqual(out["evidence"][0]["kind"], "internal_measurement")
        self.assertTrue(out["editable"])


class ObjectiveTests(unittest.TestCase):
    def test_unknown_objective_rejected(self):
        with self.assertRaises(ValueError):
            Objective(weights={"deliciousness": 1.0})

    def test_weight_range_enforced(self):
        with self.assertRaises(ValueError):
            Objective(weights={"solubility": 1.5})

    def test_weights_are_normalised(self):
        obj = Objective(weights={"solubility": 2.0 / 4, "stability": 2.0 / 4})
        self.assertEqual(obj.normalized_weights(), {"solubility": 0.5, "stability": 0.5})

    def test_unmeasurable_objectives_are_reported_not_silently_dropped(self):
        obj = Objective(weights={"solubility": 0.5, "activity": 0.3, "stability": 0.2})
        self.assertEqual(obj.unsupported(), ["activity", "stability"])
        self.assertIn("activity", obj.to_dict()["unsupported_objectives"])

    def test_constraints_stay_separate_from_weights(self):
        obj = Objective(weights={"solubility": 1.0}, constraints={"rmsd_max": 2.0})
        out = obj.to_dict()
        self.assertNotIn("rmsd_max", out["weights"])
        self.assertEqual(out["constraints"]["rmsd_max"], 2.0)


if __name__ == "__main__":
    unittest.main()
