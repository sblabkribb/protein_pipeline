"""계획을 대화로 다듬는 기능.

LLM 이 계획을 설명하는 것까지는 있었지만, 사용자가 되물어보고 고치는 길이
없었다. 그렇다고 LLM 이 계획을 직접 고치게 하면, 이 저장소가 세션 내내 지켜온
규칙 - 근거 없는 결정은 만들 수 없고, 고정된 필드는 편집을 거부한다 - 이
무너진다.

그래서 대화는 **제안** 만 만든다. 적용은 기존 apply_edits 를 지나가고, 거기서
고정 필드는 거부된다. LLM 이 제안한 것과 실제로 반영된 것이 다를 수 있고, 그
차이가 사용자에게 보여야 한다.
"""

from __future__ import annotations

from pathlib import Path
import json
import sys
import unittest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "pipeline-mcp" / "src"))

from pipeline_mcp.objective_planner import (
    Objective,
    build_plan,
    build_discussion_prompt,
    parse_discussion_reply,
    DISCUSS_SYSTEM_INSTRUCTION,
)


class PromptTests(unittest.TestCase):
    def setUp(self):
        self.plan = build_plan(Objective(weights={"solubility": 1.0}))

    def test_the_prompt_carries_the_plan_and_the_conversation(self):
        prompt = build_discussion_prompt(self.plan, [
            {"role": "user", "content": "온도를 왜 0.1 로 했나요?"},
        ])
        self.assertIn("sampling_temp", prompt)
        self.assertIn("온도를 왜", prompt)

    def test_the_prompt_lists_which_fields_can_be_changed(self):
        prompt = build_discussion_prompt(self.plan, [])
        self.assertIn("수정 가능", prompt)
        for field in self.plan["locked_fields"]:
            self.assertIn(field, prompt)

    def test_the_system_instruction_forbids_inventing_evidence(self):
        for phrase in ("근거", "지어내"):
            self.assertIn(phrase, DISCUSS_SYSTEM_INSTRUCTION)

    def test_the_system_instruction_requires_edits_to_be_proposals(self):
        self.assertIn("proposed_edits", DISCUSS_SYSTEM_INSTRUCTION)


class ReplyParsingTests(unittest.TestCase):
    def test_a_plain_answer_yields_no_edits(self):
        out = parse_discussion_reply("온도는 기존 기본값입니다.")
        self.assertEqual(out["proposed_edits"], {})
        self.assertIn("기본값", out["reply"])

    def test_a_fenced_json_block_becomes_proposed_edits(self):
        text = ('온도를 올리면 다양성이 늘어납니다.\n'
                '```json\n{"proposed_edits": {"sampling_temp": 0.3}}\n```')
        out = parse_discussion_reply(text)
        self.assertEqual(out["proposed_edits"], {"sampling_temp": 0.3})
        self.assertNotIn("```", out["reply"])

    def test_malformed_json_is_dropped_rather_than_guessed(self):
        out = parse_discussion_reply('설명\n```json\n{"proposed_edits": {oops}\n```')
        self.assertEqual(out["proposed_edits"], {})
        self.assertTrue(out["parse_warning"])

    def test_a_non_object_edit_block_is_refused(self):
        out = parse_discussion_reply('설명\n```json\n{"proposed_edits": [1,2]}\n```')
        self.assertEqual(out["proposed_edits"], {})

    def test_the_reply_never_comes_back_empty_when_there_was_text(self):
        out = parse_discussion_reply('```json\n{"proposed_edits": {"sampling_temp": 0.3}}\n```')
        self.assertTrue(out["reply"].strip())


class ToolTests(unittest.TestCase):
    def _dispatch(self, reply_text):
        from pipeline_mcp import tools

        class _Gemini:
            def is_available(self):
                return True

            def chat(self, system, prompt):
                return reply_text

        return tools.ToolDispatcher(type("R", (), {"gemini": _Gemini()})())

    def test_the_tool_is_listed(self):
        from pipeline_mcp import tools

        self.assertIn("pipeline.discuss_plan",
                      {t["name"] for t in tools.tool_definitions()})

    def test_a_proposed_edit_to_a_locked_field_is_reported_as_rejected(self):
        """LLM 이 고정 필드를 바꾸자고 해도 반영되지 않는다."""
        plan = build_plan(Objective(weights={"solubility": 1.0}))
        locked = plan["locked_fields"][0]
        out = self._dispatch(
            '바꾸는 게 좋겠습니다.\n```json\n'
            + json.dumps({"proposed_edits": {locked: "something"}}) + '\n```'
        ).call_tool("pipeline.discuss_plan", {"plan": plan, "messages": [
            {"role": "user", "content": "바꿔주세요"}]})
        self.assertIn(locked, out["rejected_edits"])
        self.assertNotIn(locked, out["applicable_edits"])

    def test_an_editable_field_is_offered_for_confirmation_not_applied(self):
        plan = build_plan(Objective(weights={"solubility": 1.0}))
        out = self._dispatch(
            '온도를 올리시죠.\n```json\n{"proposed_edits": {"sampling_temp": 0.3}}\n```'
        ).call_tool("pipeline.discuss_plan", {"plan": plan, "messages": []})
        self.assertEqual(out["applicable_edits"]["sampling_temp"], 0.3)
        # 계획 자체는 그대로다. 적용은 사용자가 승인 단계에서 한다.
        temp = next(d for d in out["plan"]["decisions"] if d["field"] == "sampling_temp")
        self.assertEqual(temp["value"], 0.1)

    def test_the_reply_is_marked_as_generated_prose(self):
        plan = build_plan(Objective(weights={"solubility": 1.0}))
        out = self._dispatch("설명입니다").call_tool(
            "pipeline.discuss_plan", {"plan": plan, "messages": []})
        self.assertTrue(out["reply_is_generated"])

    def test_without_an_llm_the_tool_says_so_instead_of_pretending(self):
        from pipeline_mcp import tools

        plan = build_plan(Objective(weights={"solubility": 1.0}))
        dispatcher = tools.ToolDispatcher(type("R", (), {"gemini": None})())
        out = dispatcher.call_tool("pipeline.discuss_plan", {"plan": plan, "messages": []})
        self.assertIn("llm_unavailable", out.get("reply_source", ""))
        self.assertEqual(out["applicable_edits"], {})

    def test_a_missing_plan_is_a_message_not_a_crash(self):
        from pipeline_mcp import tools

        out = tools.ToolDispatcher(type("R", (), {"gemini": None})()).call_tool(
            "pipeline.discuss_plan", {"messages": []})
        self.assertIn("error", out)


if __name__ == "__main__":
    unittest.main()
