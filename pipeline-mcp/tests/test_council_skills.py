import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pipeline_mcp.plan_council as plan_council
from pipeline_mcp.plan_council import (
    EXPERTS,
    user_charter_path,
)
from pipeline_mcp.pipeline import PipelineRunner
from pipeline_mcp.tools import ToolDispatcher, tool_definitions


class TestSkillsStore(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        patcher = mock.patch.object(plan_council, "user_charter_root", lambda: self.root)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _mk_skill(self, expert_id: str, payload: dict | str) -> Path:
        d = self.root / "_council_skills"
        d.mkdir(parents=True, exist_ok=True)
        path = d / f"{expert_id}.json"
        path.write_text(payload if isinstance(payload, str) else json.dumps(payload), encoding="utf-8")
        return path

    def test_user_charter_path_joins_id(self) -> None:
        path = user_charter_path("solubility")
        self.assertEqual(path.parent.name, "_council_skills")
        self.assertEqual(path.name, "solubility.json")

    def test_list_merges_builtin_and_user(self) -> None:
        out = plan_council.list_council_skills()
        self.assertEqual([s["expert_id"] for s in out["skills"]], [e.id for e in EXPERTS])
        self.assertTrue(all(s["source"] == "builtin" for s in out["skills"]))
        self._mk_skill("solubility", {"charter": "사용자 헌장", "updated_utc": "2026-09-07"})
        out = plan_council.list_council_skills()
        row = next(s for s in out["skills"] if s["expert_id"] == "solubility")
        self.assertEqual(row["source"], "user")
        self.assertEqual(row["charter"], "사용자 헌장")
        self.assertEqual(row["updated_utc"], "2026-09-07")

    def test_broken_user_file_falls_back_to_builtin(self) -> None:
        self._mk_skill("stability", "{broken")
        out = plan_council.list_council_skills()
        row = next(s for s in out["skills"] if s["expert_id"] == "stability")
        self.assertEqual(row["source"], "builtin")

    def test_save_validates_expert_and_length(self) -> None:
        self.assertIn("error", plan_council.save_council_skill("nope", "헌장"))
        self.assertIn("error", plan_council.save_council_skill("solubility", "   "))
        self.assertIn("error", plan_council.save_council_skill("solubility", "x" * 8001))
        out = plan_council.save_council_skill("solubility", "바뀐 헌장")
        self.assertNotIn("error", out)
        saved = json.loads((self.root / "_council_skills" / "solubility.json").read_text())
        self.assertEqual(saved["charter"], "바뀐 헌장")

    def test_reset_removes_user_file(self) -> None:
        self._mk_skill("solubility", {"charter": "x"})
        plan_council.reset_council_skill("solubility")
        self.assertFalse((self.root / "_council_skills" / "solubility.json").exists())
        plan_council.reset_council_skill("solubility")  # 없어도 ok

    def test_expert_system_prefers_user_charter(self) -> None:
        self._mk_skill("solubility", {"charter": "사용자 헌장"})
        expert = next(e for e in EXPERTS if e.id == "solubility")
        system = plan_council._expert_system(expert)
        self.assertIn("사용자 헌장", system)
        self.assertIn(plan_council.COUNCIL_OUTPUT_CONTRACT, system)  # 계약 유지

    def test_ask_expert_uses_user_charter(self) -> None:
        self._mk_skill("solubility", {"charter": "사용자 헌장"})
        expert = next(e for e in EXPERTS if e.id == "solubility")
        seen = {}

        class FakeGemini:
            def is_available(self):
                return True
            def chat(self, system, prompt):
                seen["system"] = system
                return "```json\n{\"verdict\": \"ok\", \"reasons\": [], \"suggestions\": []}\n```"

        plan_council._ask_expert(FakeGemini(), {}, expert)
        self.assertIn("사용자 헌장", seen["system"])
        self.assertIn(plan_council.COUNCIL_OUTPUT_CONTRACT, seen["system"])

    def test_ask_expert_broken_user_file_falls_back(self) -> None:
        self._mk_skill("solubility", "{")
        expert = next(e for e in EXPERTS if e.id == "solubility")
        seen = {}

        class FakeGemini:
            def is_available(self):
                return True
            def chat(self, system, prompt):
                seen["system"] = system
                return "```json\n{\"verdict\": \"ok\", \"reasons\": [], \"suggestions\": []}\n```"

        plan_council._ask_expert(FakeGemini(), {}, expert)
        self.assertIn(expert.charter[:20], seen["system"])


class TestRegistration(unittest.TestCase):
    def test_tools_are_listed(self) -> None:
        names = [t["name"] for t in tool_definitions()]
        for name in ("pipeline.list_council_skills", "pipeline.save_council_skill",
                     "pipeline.reset_council_skill"):
            self.assertIn(name, names)

    def test_dispatch_roundtrip(self) -> None:
        tmp = tempfile.mkdtemp(prefix="skills_")
        runner = PipelineRunner(output_root=tmp, mmseqs=None, proteinmpnn=None,
                                soluprot=None, af2=None)
        dispatcher = ToolDispatcher(runner)
        try:
            out = dispatcher.call_tool("pipeline.save_council_skill",
                                       {"expert_id": "solubility", "charter": "헌장"})
            self.assertNotIn("error", out)
            listed = dispatcher.call_tool("pipeline.list_council_skills", {})
            row = next(s for s in listed["skills"] if s["expert_id"] == "solubility")
            self.assertEqual(row["source"], "user")
            dispatcher.call_tool("pipeline.reset_council_skill", {"expert_id": "solubility"})
            listed = dispatcher.call_tool("pipeline.list_council_skills", {})
            row = next(s for s in listed["skills"] if s["expert_id"] == "solubility")
            self.assertEqual(row["source"], "builtin")
        finally:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
