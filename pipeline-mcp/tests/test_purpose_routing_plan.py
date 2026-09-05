"""설계 목적이 계획을 바꾼다는 계약.

목적(purpose)은 RAPID 의 라우팅 단위인 타겟보다 한 단계 위다. 어떤 모델을
쓸지는 목표 가중치가 아니라 목적이 정한다. 가중치는 그 다음이다.
"""

from __future__ import annotations

from pathlib import Path
import sys
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "pipeline-mcp" / "src"))

from pipeline_mcp.objective_planner import (
    Objective,
    build_plan,
    suggest_questions,
)


class PurposeOnObjectiveTests(unittest.TestCase):
    def test_default_purpose_is_the_validated_route(self):
        self.assertEqual(Objective().purpose, "monomer_solubility_redesign")

    def test_unknown_purpose_is_rejected_at_construction(self):
        with self.assertRaises(ValueError):
            Objective(purpose="cure_everything")

    def test_measurable_objectives_come_from_the_registry_not_a_literal(self):
        obj = Objective(weights={"solubility": 1.0, "activity": 1.0})
        self.assertEqual(obj.unsupported(), ["activity"])

    def test_binding_is_unsupported_until_a_binding_evaluator_is_validated(self):
        obj = Objective(weights={"binding": 1.0}, purpose="protein_binder_design")
        self.assertIn("binding", obj.unsupported())


class PlanRouteTests(unittest.TestCase):
    def test_plan_carries_the_route_for_the_purpose(self):
        plan = build_plan(Objective(weights={"solubility": 1.0}))
        route = plan["route"]
        self.assertEqual(route["purpose"], "monomer_solubility_redesign")
        self.assertTrue(route["executable"])
        self.assertTrue(route["validated"])
        self.assertTrue(route["stages"])

    def test_model_selection_is_a_decision_with_evidence(self):
        plan = build_plan(Objective(weights={"solubility": 1.0}))
        picks = [d for d in plan["decisions"] if d["field"] == "design_purpose"]
        self.assertEqual(len(picks), 1)
        self.assertTrue(picks[0]["evidence"])

    def test_binder_purpose_selects_the_interface_stages(self):
        plan = build_plan(Objective(weights={"binding": 1.0}, purpose="protein_binder_design"))
        models = [s["model_id"] for s in plan["route"]["stages"]]
        self.assertIn("ppiformer_ddg", models)
        self.assertIn("binder_score", models)

    def test_binder_plan_says_out_loud_that_it_is_unvalidated(self):
        plan = build_plan(Objective(weights={"binding": 1.0}, purpose="protein_binder_design"))
        self.assertFalse(plan["route"]["validated"])
        warnings = " ".join(plan.get("warnings", []))
        self.assertIn("검증", warnings)

    def test_blocked_purpose_yields_a_plan_that_refuses_to_run(self):
        plan = build_plan(Objective(weights={"binding": 1.0}, purpose="antibody_design"))
        self.assertFalse(plan["route"]["executable"])
        self.assertTrue(plan["route"]["blocked_reason"])
        self.assertFalse(plan["approvable"])

    def test_blocked_purpose_names_the_missing_models_not_a_substitute(self):
        plan = build_plan(Objective(weights={"binding": 1.0}, purpose="antibody_design"))
        reason = plan["route"]["blocked_reason"]
        self.assertIn("antifold", reason)
        self.assertNotIn("proteinmpnn 로 대체", reason)

    def test_executable_validated_plan_is_approvable(self):
        plan = build_plan(Objective(weights={"solubility": 1.0}))
        self.assertTrue(plan["approvable"])

    def test_plan_reports_a_cost_estimate_with_its_unknowns(self):
        plan = build_plan(Objective(weights={"solubility": 1.0}, budget={"designs": 40, "length_aa": 200}))
        est = plan["cost_estimate"]
        self.assertGreater(est["known_seconds"], 0)
        self.assertIn("unknown_stages", est)
        self.assertFalse(est["complete"])

    def test_cost_estimate_scales_with_declared_length(self):
        short = build_plan(Objective(budget={"designs": 10, "length_aa": 60}))["cost_estimate"]
        long = build_plan(Objective(budget={"designs": 10, "length_aa": 300}))["cost_estimate"]
        self.assertGreater(long["known_seconds"], short["known_seconds"] * 2)


class PurposeSuggestionTests(unittest.TestCase):
    def test_a_binding_weight_on_the_monomer_route_becomes_a_question(self):
        plan = build_plan(Objective(weights={"binding": 1.0, "solubility": 0.5}))
        asked = " ".join(q["question"] for q in suggest_questions(plan))
        self.assertIn("binding", asked)

    def test_suggested_purposes_are_offered_when_the_route_cannot_measure_a_goal(self):
        plan = build_plan(Objective(weights={"binding": 1.0, "solubility": 0.5}))
        questions = [q for q in suggest_questions(plan) if q.get("field") == "design_purpose"]
        self.assertTrue(questions)
        self.assertIn("protein_binder_design", questions[0]["options"])

    def test_no_purpose_question_when_the_route_covers_every_goal(self):
        plan = build_plan(Objective(weights={"solubility": 1.0}))
        self.assertFalse([q for q in suggest_questions(plan) if q.get("field") == "design_purpose"])


if __name__ == "__main__":
    unittest.main()
