import dataclasses
import shutil
import tempfile
import unittest

from pipeline_mcp.intake import (
    GEMINI_ERROR_PREFIX,
    _llm_json,
    _merge,
    _rule_extract,
    build_intake_prompt,
    intake_chat,
    strip_fence,
)
from pipeline_mcp.tools import ToolDispatcher, tool_definitions


class FakeGemini:
    """intake_chat 은 단일 chat 호출이므로 응답 문자열 하나로 충분하다."""

    def __init__(self, reply="", error=False):
        self.reply = reply
        self.error = error
        self.calls = []

    def is_available(self) -> bool:
        return True

    def chat(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        if self.error:
            return f"{GEMINI_ERROR_PREFIX}: quota"
        return self.reply


READY_REPLY = (
    "용해도 중심으로 정리했습니다.\n"
    "```json\n"
    "{\"objective\": {\"weights\": {\"solubility\": 0.6, \"structural_preservation\": 0.4}, "
    "\"budget\": {\"designs\": 40, \"length_aa\": 200}, "
    "\"purpose\": \"monomer_solubility_redesign\"}}\n"
    "```"
)


class TestRuleExtract(unittest.TestCase):
    def test_korean_count_maps_to_designs(self) -> None:
        # router 의 실제 키는 num_seq_per_tier 다 — 인테이크에서는 설계 수로 옮긴다.
        out = _rule_extract("20개 만들어줘")
        self.assertEqual(out["budget"]["designs"], 20)

    def test_garbage_is_ignored(self) -> None:
        self.assertEqual(_rule_extract(""), {})
        self.assertEqual(_rule_extract("hello world"), {})


class TestLlmJson(unittest.TestCase):
    def test_fenced_objective_is_parsed(self) -> None:
        obj = _llm_json(READY_REPLY)
        self.assertEqual(obj["weights"]["solubility"], 0.6)
        self.assertEqual(obj["budget"]["designs"], 40)

    def test_bare_objective_dict_is_absorbed(self) -> None:
        raw = "```json\n{\"weights\": {\"diversity\": 0.2}, \"budget\": {\"designs\": 8}}\n```"
        obj = _llm_json(raw)
        self.assertEqual(obj["budget"]["designs"], 8)

    def test_junk_is_dropped(self) -> None:
        for raw in ("산문만 있음", "```json\nnot json\n```", "```json\n[1, 2]\n```", ""):
            self.assertEqual(_llm_json(raw), {})


class TestMerge(unittest.TestCase):
    def test_rule_wins_on_conflict(self) -> None:
        merged = _merge({"budget": {"designs": 20}},
                        {"budget": {"designs": 5, "length_aa": 120}})
        self.assertEqual(merged["budget"]["designs"], 20)
        self.assertEqual(merged["budget"]["length_aa"], 120)

    def test_llm_fills_all_blanks(self) -> None:
        merged = _merge({}, {"weights": {"diversity": 0.2},
                             "budget": {"designs": 8},
                             "purpose": "de_novo_backbone_design"})
        self.assertEqual(merged["weights"], {"diversity": 0.2})
        self.assertEqual(merged["purpose"], "de_novo_backbone_design")


class TestStripFence(unittest.TestCase):
    def test_prose_only(self) -> None:
        self.assertEqual(strip_fence(READY_REPLY), "용해도 중심으로 정리했습니다.")


class TestIntakeChat(unittest.TestCase):
    def test_rules_win_over_llm(self) -> None:
        gemini = FakeGemini(reply=READY_REPLY.replace("\"designs\": 40", "\"designs\": 5"))
        out = intake_chat([{"role": "user", "content": "20개 만들어줘"}], gemini,
                          attached_fasta="MKTV")
        self.assertEqual(out["objective"]["budget"]["designs"], 20)

    def test_llm_fills_blanks_and_readiness(self) -> None:
        gemini = FakeGemini(reply=READY_REPLY)
        out = intake_chat([{"role": "user", "content": "용해도 좋은 단백질 40개"}], gemini,
                          attached_fasta="MKTV")
        self.assertTrue(out["objective_ready"])
        self.assertEqual(out["missing"], [])
        self.assertEqual(out["objective"]["weights"]["solubility"], 0.6)
        self.assertEqual(out["objective"]["budget"]["designs"], 40)
        # fixed_note 가 system 으로 들어갔는지 확인한다 — 계약의 핵심.
        self.assertIn("규칙이 이미 확정한 값", gemini.calls[0][0])

    def test_unknown_objective_weight_blocks_ready(self) -> None:
        reply = ("```json\n{\"objective\": {\"weights\": {\"tastiness\": 0.5}, "
                 "\"budget\": {\"designs\": 8}}}\n```")
        out = intake_chat([{"role": "user", "content": "맛있는 걸로"}], FakeGemini(reply),
                          attached_fasta="MKTV")
        self.assertFalse(out["objective_ready"])
        self.assertTrue(any("알 수 없는 objective" in m for m in out["missing"]))

    def test_out_of_range_weight_blocks_ready(self) -> None:
        reply = ("```json\n{\"objective\": {\"weights\": {\"solubility\": 1.5}, "
                 "\"budget\": {\"designs\": 8}}}\n```")
        out = intake_chat([{"role": "user", "content": "최대한으로"}], FakeGemini(reply),
                          attached_fasta="MKTV")
        self.assertFalse(out["objective_ready"])
        self.assertTrue(any("0..1" in m for m in out["missing"]))

    def test_unknown_purpose_is_rejected(self) -> None:
        reply = ("```json\n{\"objective\": {\"weights\": {\"solubility\": 1.0}, "
                 "\"budget\": {\"designs\": 8}, \"purpose\": \"teleportation\"}}\n```")
        out = intake_chat([{"role": "user", "content": "순간이동하는 단백질"}], FakeGemini(reply),
                          attached_fasta="MKTV")
        self.assertFalse(out["objective_ready"])
        self.assertTrue(any("목적" in m and "teleportation" in m for m in out["missing"]))

    def test_missing_target_is_reported(self) -> None:
        out = intake_chat([{"role": "user", "content": "용해도 좋은 걸로 8개"}],
                          FakeGemini(reply=READY_REPLY))
        self.assertFalse(out["objective_ready"])
        self.assertTrue(any("타겟" in m for m in out["missing"]))
        # 첨부 없음도 LLM 프롬프트로 전달된다.
        prompt = build_intake_prompt(out["messages"], False)
        self.assertIn("아직 없는 필수: 타겟", prompt)

    def test_without_gemini_is_llm_unavailable(self) -> None:
        for gemini in (None, object()):
            out = intake_chat([{"role": "user", "content": "안녕"}], gemini)
            self.assertTrue(out["llm_unavailable"])
            self.assertFalse(out["objective_ready"])
            self.assertTrue(out["reply"])

    def test_error_string_gemini_is_llm_unavailable(self) -> None:
        out = intake_chat([{"role": "user", "content": "안녕"}], FakeGemini(error=True))
        self.assertTrue(out["llm_unavailable"])
        self.assertFalse(out["objective_ready"])
        self.assertTrue(out["reply"].startswith(GEMINI_ERROR_PREFIX))

    def test_raising_gemini_is_llm_unavailable(self) -> None:
        class Boom:
            def is_available(self):
                return True

            def chat(self, system, user):
                raise RuntimeError("boom")

        out = intake_chat([{"role": "user", "content": "안녕"}], Boom())
        self.assertTrue(out["llm_unavailable"])
        self.assertFalse(out["objective_ready"])

    def test_no_user_turn_is_error(self) -> None:
        self.assertIn("error", intake_chat([], FakeGemini()))
        self.assertIn("error", intake_chat([{"role": "assistant", "content": "hi"}], FakeGemini()))


class TestRegistration(unittest.TestCase):
    def test_tool_is_listed(self) -> None:
        names = [t["name"] for t in tool_definitions()]
        self.assertIn("pipeline.intake_chat", names)

    def test_dispatch_rejects_missing_user_turn(self) -> None:
        runner = PipelineRunnerStub()
        out = ToolDispatcher(runner).call_tool("pipeline.intake_chat", {"messages": []})
        self.assertIn("error", out)

    def test_dispatch_uses_runner_gemini(self) -> None:
        tmp = tempfile.mkdtemp(prefix="intake_")
        try:
            runner = dataclasses.replace(
                PipelineRunnerStub(),
                gemini=FakeGemini(reply=READY_REPLY),
            )
            out = ToolDispatcher(runner).call_tool("pipeline.intake_chat", {
                "messages": [{"role": "user", "content": "용해도 좋은 단백질 40개"}],
                "attached_fasta": "MKTV",
            })
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        self.assertTrue(out["objective_ready"])
        self.assertEqual(out["objective"]["budget"]["designs"], 40)


def PipelineRunnerStub():
    from pipeline_mcp.pipeline import PipelineRunner

    return PipelineRunner(output_root=tempfile.mkdtemp(prefix="intake_runner_"),
                          mmseqs=None, proteinmpnn=None, soluprot=None, af2=None)


if __name__ == "__main__":
    unittest.main()
