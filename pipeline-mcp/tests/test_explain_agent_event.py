import unittest
import uuid
from contextlib import contextmanager
from pathlib import Path

from pipeline_mcp.agent_panel import build_agent_panel_event
from pipeline_mcp.pipeline import PipelineRunner
from pipeline_mcp.storage import append_run_event
from pipeline_mcp.storage import init_run
from pipeline_mcp.tools import ToolDispatcher


@contextmanager
def _tmpdir():
    base = Path(__file__).resolve().parent / "_tmp"
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"run_{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    yield str(path)


class FakeGemini:
    def __init__(self, reply="af2 판정을 풀어쓴 문장입니다.", available=True, error=None):
        self.reply = reply
        self.available = available
        self.error = error
        self.calls = []

    def is_available(self):
        return self.available

    def chat(self, system_instruction, user_prompt):
        self.calls.append({"system": system_instruction, "prompt": user_prompt})
        if self.error is not None:
            raise self.error
        return self.reply


class TestExplainAgentEvent(unittest.TestCase):
    def _setup_run(self, tmp):
        outputs_root = Path(tmp) / "outputs"
        outputs_root.mkdir(parents=True, exist_ok=True)
        run_id = f"explain_{uuid.uuid4().hex[:8]}"
        init_run(str(outputs_root), run_id)
        event = build_agent_panel_event(
            output_root=str(outputs_root), run_id=run_id, stage="af2_50"
        )
        append_run_event(
            str(outputs_root), run_id, filename="agent_panel.jsonl", payload=event
        )
        error_event = build_agent_panel_event(
            output_root=str(outputs_root),
            run_id=run_id,
            stage="design_40",
            error="proteinmpnn failed",
        )
        append_run_event(
            str(outputs_root), run_id, filename="agent_panel.jsonl", payload=error_event
        )
        return str(outputs_root), run_id, event, error_event

    def test_found_event_calls_gemini_and_returns_generated_reply(self) -> None:
        with _tmpdir() as tmp:
            outputs_root, run_id, event, _ = self._setup_run(tmp)
            gemini = FakeGemini(reply="구조 판정을 풀어 쓴 문장입니다.")
            runner = PipelineRunner(output_root=outputs_root, mmseqs=None, proteinmpnn=None, soluprot=None, af2=None, gemini=gemini)
            dispatcher = ToolDispatcher(runner)

            out = dispatcher.call_tool(
                "pipeline.explain_agent_event",
                {"run_id": run_id, "event_id": str(event.get("id"))},
            )

            self.assertEqual(out.get("reply"), "구조 판정을 풀어 쓴 문장입니다.")
            self.assertIs(out.get("reply_is_generated"), True)
            self.assertEqual(str(out.get("event_id")), str(event.get("id")))
            self.assertEqual(str(out.get("run_id")), run_id)
            self.assertNotIn("llm_unavailable", out)
            # 프롬프트는 이벤트 데이터로만 좁혀진다 - 스테이지와 합의 판정이 들어간다.
            self.assertEqual(len(gemini.calls), 1)
            prompt = gemini.calls[0]["prompt"]
            self.assertIn("af2_50", prompt)
            self.assertIn(str(event.get("consensus", {}).get("decision")), prompt)
            # 시스템 지시는 invented facts 를 금지한다.
            system = gemini.calls[0]["system"]
            self.assertIn("금지", system)

    def test_unknown_event_id_returns_contract_error(self) -> None:
        with _tmpdir() as tmp:
            outputs_root, run_id, _, _ = self._setup_run(tmp)
            runner = PipelineRunner(output_root=outputs_root, mmseqs=None, proteinmpnn=None, soluprot=None, af2=None, gemini=FakeGemini())
            dispatcher = ToolDispatcher(runner)

            out = dispatcher.call_tool(
                "pipeline.explain_agent_event",
                {"run_id": run_id, "event_id": "does_not_exist"},
            )

            self.assertEqual(out.get("error"), "event not found")
            self.assertNotIn("reply", out)

    def test_gemini_none_returns_llm_unavailable_contract(self) -> None:
        with _tmpdir() as tmp:
            outputs_root, run_id, event, _ = self._setup_run(tmp)
            runner = PipelineRunner(output_root=outputs_root, mmseqs=None, proteinmpnn=None, soluprot=None, af2=None, gemini=None)
            dispatcher = ToolDispatcher(runner)

            out = dispatcher.call_tool(
                "pipeline.explain_agent_event",
                {"run_id": run_id, "event_id": str(event.get("id"))},
            )

            self.assertIs(out.get("llm_unavailable"), True)
            self.assertIs(out.get("reply_is_generated"), False)
            self.assertTrue(str(out.get("reply") or ""))
            self.assertIn("LLM", str(out.get("reply")))

    def test_error_string_reply_returns_llm_unavailable_contract(self) -> None:
        with _tmpdir() as tmp:
            outputs_root, run_id, event, _ = self._setup_run(tmp)
            runner = PipelineRunner(
                output_root=outputs_root, mmseqs=None, proteinmpnn=None, soluprot=None, af2=None,
                gemini=FakeGemini(reply="Error communicating with Gemini: TimeoutError: boom"),
            )
            dispatcher = ToolDispatcher(runner)

            out = dispatcher.call_tool(
                "pipeline.explain_agent_event",
                {"run_id": run_id, "event_id": str(event.get("id"))},
            )

            self.assertIs(out.get("llm_unavailable"), True)
            self.assertIs(out.get("reply_is_generated"), False)

    def test_chat_exception_returns_llm_unavailable_contract(self) -> None:
        with _tmpdir() as tmp:
            outputs_root, run_id, event, _ = self._setup_run(tmp)
            runner = PipelineRunner(output_root=outputs_root, mmseqs=None, proteinmpnn=None, soluprot=None, af2=None, gemini=FakeGemini(error=RuntimeError("endpoint down")))
            dispatcher = ToolDispatcher(runner)

            out = dispatcher.call_tool(
                "pipeline.explain_agent_event",
                {"run_id": run_id, "event_id": str(event.get("id"))},
            )

            self.assertIs(out.get("llm_unavailable"), True)
            self.assertIs(out.get("reply_is_generated"), False)

    def test_tool_is_listed_and_dispatches(self) -> None:
        with _tmpdir() as tmp:
            outputs_root, run_id, event, _ = self._setup_run(tmp)
            runner = PipelineRunner(output_root=outputs_root, mmseqs=None, proteinmpnn=None, soluprot=None, af2=None, gemini=FakeGemini())
            dispatcher = ToolDispatcher(runner)

            names = [t.get("name") for t in dispatcher.list_tools().get("tools", [])]
            self.assertIn("pipeline.explain_agent_event", names)

            with self.assertRaises(ValueError):
                dispatcher.call_tool(
                    "pipeline.explain_agent_event", {"run_id": "", "event_id": "x"}
                )

            out = dispatcher.call_tool(
                "pipeline.explain_agent_event",
                {"run_id": run_id, "event_id": str(event.get("id"))},
            )
            self.assertEqual(out.get("reply"), "af2 판정을 풀어쓴 문장입니다.")


if __name__ == "__main__":
    unittest.main()
