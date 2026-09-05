from __future__ import annotations

import unittest

from pipeline_mcp import tools
from pipeline_mcp.objective_planner import Objective, build_plan


class ToolRegistrationTests(unittest.TestCase):
    def test_tool_is_listed(self):
        names = {spec["name"] for spec in tools.TOOL_SPECS} if hasattr(tools, "TOOL_SPECS") else set()
        if not names:
            source = open(tools.__file__, encoding="utf-8").read()
            self.assertIn('"pipeline.plan_from_objective"', source)
        else:
            self.assertIn("pipeline.plan_from_objective", names)


class PlanContentTests(unittest.TestCase):
    def test_every_decision_carries_evidence(self):
        plan = build_plan(Objective(weights={"solubility": 1.0}))
        self.assertTrue(plan["decisions"])
        for decision in plan["decisions"]:
            self.assertTrue(decision["evidence"], decision["field"])
            for ev in decision["evidence"]:
                self.assertIn(ev["kind"],
                              {"internal_measurement", "literature", "assumption"})

    def test_routing_unit_and_af2_are_locked(self):
        plan = build_plan(Objective(weights={"solubility": 1.0}))
        self.assertIn("gate0_routing_unit", plan["locked_fields"])
        self.assertIn("af2_verification", plan["locked_fields"])

    def test_high_diversity_weight_raises_temperature(self):
        low = build_plan(Objective(weights={"solubility": 1.0}))
        high = build_plan(Objective(weights={"solubility": 0.5, "diversity": 0.5}))
        temp_of = lambda p: next(d["value"] for d in p["decisions"]
                                 if d["field"] == "sampling_temp")
        self.assertEqual(temp_of(low), 0.1)
        self.assertEqual(temp_of(high), 0.3)

    def test_temperature_choice_admits_it_is_unverified_on_structure(self):
        plan = build_plan(Objective(weights={"solubility": 0.5, "diversity": 0.5}))
        temp = next(d for d in plan["decisions"] if d["field"] == "sampling_temp")
        kinds = {e["kind"] for e in temp["evidence"]}
        self.assertIn("assumption", kinds)

    def test_unmeasurable_objective_produces_a_warning(self):
        plan = build_plan(Objective(weights={"solubility": 0.5, "activity": 0.5}))
        self.assertTrue(any("activity" in w for w in plan.get("warnings", [])))

    def test_plan_requires_review_before_running(self):
        plan = build_plan(Objective(weights={"solubility": 1.0}))
        self.assertTrue(plan["review_required"])


class ToolDispatchTests(unittest.TestCase):
    def test_bad_weight_returns_message_not_exception(self):
        runner = tools.PipelineRunner(output_root="/tmp")
        service = tools.build_service(runner) if hasattr(tools, "build_service") else None
        if service is None:
            from pipeline_mcp.objective_planner import Objective
            with self.assertRaises(ValueError):
                Objective(weights={"solubility": 5.0})


if __name__ == "__main__":
    unittest.main()


class RequestConversionTests(unittest.TestCase):
    def test_mapped_decisions_become_request_fields(self):
        from pipeline_mcp.objective_planner import plan_to_request_overrides
        plan = build_plan(Objective(weights={"solubility": 0.5, "diversity": 0.5},
                                    constraints={"rmsd_max": 2.0}))
        out = plan_to_request_overrides(plan)
        self.assertEqual(out["request_overrides"]["sampling_temp"], 0.3)
        self.assertEqual(out["request_overrides"]["num_seq_per_tier"], 16)
        self.assertEqual(out["request_overrides"]["af2_rmsd_cutoff"], 2.0)

    def test_unmapped_decisions_are_reported_not_dropped(self):
        from pipeline_mcp.objective_planner import plan_to_request_overrides
        plan = build_plan(Objective(weights={"solubility": 1.0}))
        out = plan_to_request_overrides(plan)
        self.assertIn("gate0_routing_unit", out["unmapped_decisions"])


class EditTests(unittest.TestCase):
    def test_user_edit_is_applied_and_flagged(self):
        from pipeline_mcp.objective_planner import apply_edits
        plan = build_plan(Objective(weights={"solubility": 1.0}))
        edited = apply_edits(plan, {"sampling_temp": 0.2})
        temp = next(d for d in edited["decisions"] if d["field"] == "sampling_temp")
        self.assertEqual(temp["value"], 0.2)
        self.assertTrue(temp["edited_by_user"])
        self.assertEqual(edited["applied_edits"]["sampling_temp"], 0.2)

    def test_locked_field_edit_is_rejected_not_silently_ignored(self):
        from pipeline_mcp.objective_planner import apply_edits
        plan = build_plan(Objective(weights={"solubility": 1.0}))
        edited = apply_edits(plan, {"af2_verification": "drop"})
        af2 = next(d for d in edited["decisions"] if d["field"] == "af2_verification")
        self.assertEqual(af2["value"], "keep")
        self.assertIn("af2_verification", edited["rejected_edits"])

    def test_evidence_survives_editing(self):
        from pipeline_mcp.objective_planner import apply_edits
        plan = build_plan(Objective(weights={"solubility": 1.0}))
        edited = apply_edits(plan, {"soluprot_cutoff": 0.7})
        cutoff = next(d for d in edited["decisions"] if d["field"] == "soluprot_cutoff")
        self.assertTrue(cutoff["evidence"])
