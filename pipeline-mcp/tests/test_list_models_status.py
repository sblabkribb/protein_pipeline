import tempfile
import unittest

from pipeline_mcp.model_routing import load_registry
from pipeline_mcp.pipeline import PipelineRunner
from pipeline_mcp.tools import ToolDispatcher


class TestListModelsStatus(unittest.TestCase):
    def test_response_carries_objective_status(self) -> None:
        runner = PipelineRunner(output_root=tempfile.mkdtemp(prefix="lm_"),
                                mmseqs=None, proteinmpnn=None, soluprot=None, af2=None)
        out = ToolDispatcher(runner).call_tool("pipeline.list_models", {})
        self.assertIn("objective_status", out)
        registry = load_registry()
        self.assertEqual(set(out["objective_status"].keys()),
                         set(registry.objective_status.keys()))
        entry = next(iter(out["objective_status"].values()))
        self.assertIn("status", entry)
        self.assertIn("detail", entry)


if __name__ == "__main__":
    unittest.main()
