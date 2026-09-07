import dataclasses
import shutil
import tempfile
import unittest

from pipeline_mcp.pipeline import PipelineRunner
from pipeline_mcp.plan_council import (
    EXPERTS,
    GEMINI_ERROR_PREFIX,
    Expert,
    build_expert_prompt,
    parse_expert_reply,
    review_suggestions,
    run_council,
)
from pipeline_mcp.tools import ToolDispatcher, tool_definitions


class FakeGemini:
    """build_expert_prompt 가 '전문가 ID: <id>' 줄을 넣으므로 id 로 응답을 고른다."""

    def __init__(self, replies=None, raise_for=None, error_for=None):
        self.replies = dict(replies or {})
        self.raise_for = set(raise_for or ())
        self.error_for = set(error_for or ())

    def is_available(self) -> bool:
        return True

    def chat(self, system: str, user: str) -> str:
        for expert_id in self.raise_for:
            if f"전문가 ID: {expert_id}" in user:
                raise RuntimeError("boom")
        for expert_id in self.error_for:
            if f"전문가 ID: {expert_id}" in user:
                return f"{GEMINI_ERROR_PREFIX}: quota"
        for expert_id, reply in self.replies.items():
            if f"전문가 ID: {expert_id}" in user:
                return reply
        return "```json\n{\"verdict\": \"ok\", \"reasons\": [], \"suggestions\": []}\n```"


PLAN = {
    "objective": {
        "normalized_weights": {"solubility": 0.5, "structural_preservation": 0.3, "diversity": 0.2},
        "budget": {"designs": 48, "length_aa": 120},
    },
    "route": {"purpose": "monomer_solubility_redesign", "executable": True, "validated": True},
    "cost_estimate": {"estimated_seconds": 600},
    "decisions": [
        {"field": "design_purpose", "value": "monomer_solubility_redesign", "rationale": "기본 경로",
         "editable": False, "evidence": []},
        {"field": "use_soluble_model", "value": True, "rationale": "용해도 목표", "editable": True,
         "evidence": [{"kind": "literature", "statement": "ProteinMPNN soluble 가중치 공개",
                       "source": "Dauparas et al. 2022"}]},
        {"field": "soluprot_cutoff", "value": 0.5, "rationale": "게이트 1 임계값", "editable": True, "evidence": []},
        {"field": "sampling_temp", "value": 0.3, "rationale": "다양성 가중치", "editable": True, "evidence": []},
        {"field": "af2_verification", "value": "keep", "rationale": "검증됨", "editable": False, "evidence": []},
    ],
    "editable_fields": ["use_soluble_model", "soluprot_cutoff", "sampling_temp"],
    "locked_fields": ["design_purpose", "af2_verification"],
}


class TestExperts(unittest.TestCase):
    def test_expert_tables_are_disjoint(self) -> None:
        seen_fields = [f for e in EXPERTS for f in e.decision_fields]
        seen_weights = [w for e in EXPERTS for w in e.weight_scope]
        self.assertEqual(len(seen_fields), len(set(seen_fields)))
        self.assertEqual(len(seen_weights), len(set(seen_weights)))
        self.assertEqual(len(EXPERTS), 5)

    def test_prompt_contains_plan_and_ownership(self) -> None:
        expert = EXPERTS[0]
        prompt = build_expert_prompt(PLAN, expert)
        self.assertIn("전문가 ID: solubility", prompt)
        self.assertIn("당신이 제안할 수 있는 필드: ['use_soluble_model', 'soluprot_cutoff']", prompt)
        self.assertIn("고정 필드", prompt)

    def test_prompt_renders_warnings(self) -> None:
        plan = dict(PLAN, warnings=["'activity': 평가자 없음"])
        prompt = build_expert_prompt(plan, EXPERTS[0])
        self.assertIn("경고: 'activity': 평가자 없음", prompt)


class TestParse(unittest.TestCase):
    def test_fenced_json_is_parsed(self) -> None:
        raw = "좋습니다.\n```json\n{\"verdict\": \"warn\", \"reasons\": [\"컷오프가 높다\"], \"suggestions\": []}\n```"
        parsed = parse_expert_reply(raw)
        self.assertEqual(parsed["verdict"], "warn")
        self.assertEqual(parsed["reasons"], ["컷오프가 높다"])
        self.assertEqual(parsed["parse_error"], "")

    def test_invalid_reply_is_unavailable(self) -> None:
        for raw in ("", "말만 있고 json 없음", "```json\nnot json\n```",
                    "```json\n{\"verdict\": \"maybe\"}\n```"):
            parsed = parse_expert_reply(raw)
            self.assertTrue(parsed["parse_error"], raw)
            self.assertEqual(parsed["verdict"], "")


class TestReview(unittest.TestCase):
    def test_owned_and_editable_suggestion_applies(self) -> None:
        expert = Expert("t", "테스트", "", decision_fields=("soluprot_cutoff",))
        applicable, rejected = review_suggestions(PLAN, expert, [{
            "field": "soluprot_cutoff", "value": 0.4, "rationale": "완화",
            "evidence": [{"kind": "assumption", "statement": "낮춰도 안전하다고 본다"}],
        }])
        self.assertEqual(applicable, {"soluprot_cutoff": 0.4})
        self.assertEqual(rejected, {})

    def test_ownership_violation_is_rejected(self) -> None:
        expert = EXPERTS[0]  # solubility: use_soluble_model, soluprot_cutoff
        applicable, rejected = review_suggestions(PLAN, expert, [
            {"field": "sampling_temp", "value": 0.5, "rationale": "x",
             "evidence": [{"kind": "assumption", "statement": "s"}]},
        ])
        self.assertEqual(applicable, {})
        self.assertIn("sampling_temp", rejected)
        self.assertIn("소유", rejected["sampling_temp"]["reason"])

    def test_locked_field_is_rejected(self) -> None:
        expert = Expert("t", "테스트", "", decision_fields=("af2_verification",))
        applicable, rejected = review_suggestions(PLAN, expert, [
            {"field": "af2_verification", "value": "drop", "rationale": "x",
             "evidence": [{"kind": "assumption", "statement": "s"}]},
        ])
        self.assertEqual(applicable, {})
        self.assertIn("고정", rejected["af2_verification"]["reason"])

    def test_out_of_range_value_is_rejected(self) -> None:
        expert = Expert("t", "테스트", "", decision_fields=("soluprot_cutoff",))
        applicable, rejected = review_suggestions(PLAN, expert, [
            {"field": "soluprot_cutoff", "value": 1.5, "rationale": "x",
             "evidence": [{"kind": "assumption", "statement": "s"}]},
        ])
        self.assertEqual(applicable, {})
        self.assertIn("범위", rejected["soluprot_cutoff"]["reason"])

    def test_evidence_without_source_is_rejected(self) -> None:
        expert = Expert("t", "테스트", "", decision_fields=("soluprot_cutoff",))
        applicable, rejected = review_suggestions(PLAN, expert, [
            {"field": "soluprot_cutoff", "value": 0.4, "rationale": "x",
             "evidence": [{"kind": "literature", "statement": "어딘가에 있다"}]},
        ])
        self.assertEqual(applicable, {})
        self.assertIn("근거", rejected["soluprot_cutoff"]["reason"])

    def test_suggestion_without_evidence_is_rejected(self) -> None:
        expert = Expert("t", "테스트", "", decision_fields=("soluprot_cutoff",))
        applicable, rejected = review_suggestions(PLAN, expert, [
            {"field": "soluprot_cutoff", "value": 0.4, "rationale": "x", "evidence": []},
        ])
        self.assertEqual(applicable, {})
        self.assertIn("근거 없는 제안", rejected["soluprot_cutoff"]["reason"])


class TestCouncil(unittest.TestCase):
    def test_without_gemini_skips(self) -> None:
        for gemini in (None, object()):
            out = run_council(PLAN, gemini)
            self.assertEqual(out["council"], [])
            self.assertTrue(out["notes"])

    def test_all_experts_answer(self) -> None:
        reply = ("```json\n{\"verdict\": \"warn\", \"reasons\": [\"r\"], "
                 "\"suggestions\": [{\"field\": \"soluprot_cutoff\", \"value\": 0.4, "
                 "\"rationale\": \"완화\", \"evidence\": "
                 "[{\"kind\": \"assumption\", \"statement\": \"s\"}]}]}\n```")
        gemini = FakeGemini(replies={e.id: reply for e in EXPERTS})
        out = run_council(PLAN, gemini)
        self.assertEqual(len(out["council"]), 5)
        self.assertEqual([row["status"] for row in out["council"]], ["ok"] * 5)
        self.assertEqual(out["applicable_edits"], {"soluprot_cutoff": 0.4})

    def test_gemini_error_string_marks_error(self) -> None:
        gemini = FakeGemini(error_for={"stability"})
        out = run_council(PLAN, gemini)
        row = next(r for r in out["council"] if r["expert_id"] == "stability")
        self.assertEqual(row["status"], "error")

    def test_raising_expert_is_error_and_others_survive(self) -> None:
        gemini = FakeGemini(raise_for={"experiment"})
        out = run_council(PLAN, gemini)
        row = next(r for r in out["council"] if r["expert_id"] == "experiment")
        self.assertEqual(row["status"], "error")
        self.assertEqual(sum(1 for r in out["council"] if r["status"] == "ok"), 4)

    def test_council_is_sorted_by_expert_order(self) -> None:
        gemini = FakeGemini()
        out = run_council(PLAN, gemini)
        self.assertEqual([r["expert_id"] for r in out["council"]], [e.id for e in EXPERTS])


class TestRegistration(unittest.TestCase):
    def test_tool_is_listed(self) -> None:
        names = [t["name"] for t in tool_definitions()]
        self.assertIn("pipeline.plan_council", names)

    def test_dispatch_rejects_non_object_plan(self) -> None:
        runner = PipelineRunner(output_root="/tmp/unused-council", mmseqs=None,
                                proteinmpnn=None, soluprot=None, af2=None)
        out = ToolDispatcher(runner).call_tool("pipeline.plan_council", {"plan": "nope"})
        self.assertIn("error", out)

    def test_dispatch_uses_runner_gemini(self) -> None:
        tmp = tempfile.mkdtemp(prefix="council_")
        try:
            runner = dataclasses.replace(
                PipelineRunner(output_root=tmp, mmseqs=None, proteinmpnn=None,
                               soluprot=None, af2=None),
                gemini=FakeGemini(replies={e.id: (
                    "```json\n{\"verdict\": \"ok\", \"reasons\": [], \"suggestions\": []}\n```"
                ) for e in EXPERTS}),
            )
            out = ToolDispatcher(runner).call_tool("pipeline.plan_council", {"plan": PLAN})
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        self.assertEqual(len(out["council"]), 5)
        self.assertEqual(out["notes"], [])


if __name__ == "__main__":
    unittest.main()
