import unittest
import json
import uuid
from contextlib import contextmanager
from pathlib import Path

from pipeline_mcp.pipeline import PipelineRunner
from pipeline_mcp.tools import ToolDispatcher


@contextmanager
def _tmpdir():
    base = Path(__file__).resolve().parent / "_tmp"
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"run_{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    yield str(path)


class TestTools(unittest.TestCase):
    def test_pipeline_run_tool_dry_run(self) -> None:
        fasta = ">q1\nACDEFGHIK\n"
        pdb = (
            "ATOM      1  CA  ALA A   1       0.000   0.000   0.000  1.00 20.00           C\n"
            "ATOM      2  CA  CYS A   2       1.000   0.000   0.000  1.00 20.00           C\n"
            "ATOM      3  CA  ASP A   3       2.000   0.000   0.000  1.00 20.00           C\n"
            "ATOM      4  CA  GLU A   4       3.000   0.000   0.000  1.00 20.00           C\n"
            "ATOM      5  CA  PHE A   5       4.000   0.000   0.000  1.00 20.00           C\n"
            "ATOM      6  CA  GLY A   6       5.000   0.000   0.000  1.00 20.00           C\n"
            "ATOM      7  CA  HIS A   7       6.000   0.000   0.000  1.00 20.00           C\n"
            "ATOM      8  CA  ILE A   8       7.000   0.000   0.000  1.00 20.00           C\n"
            "ATOM      9  CA  LYS A   9       8.000   0.000   0.000  1.00 20.00           C\n"
            "END\n"
        )
        with _tmpdir() as tmp:
            runner = PipelineRunner(output_root=tmp, mmseqs=None, proteinmpnn=None, soluprot=None, af2=None)
            dispatcher = ToolDispatcher(runner)
            out = dispatcher.call_tool(
                "pipeline.run",
                {
                    "target_fasta": fasta,
                    "target_pdb": pdb,
                    "dry_run": True,
                    "num_seq_per_tier": 2,
                    "conservation_tiers": [0.3],
                    "fixed_positions_extra": {"A": [9]},
                },
            )
            self.assertIn("run_id", out)
            self.assertIn("output_dir", out)
            json.dumps(out)

    def test_pipeline_run_tool_dry_run_without_pdb(self) -> None:
        fasta = ">q1\nACDEFGHIK\n"
        with _tmpdir() as tmp:
            runner = PipelineRunner(output_root=tmp, mmseqs=None, proteinmpnn=None, soluprot=None, af2=None)
            dispatcher = ToolDispatcher(runner)
            out = dispatcher.call_tool(
                "pipeline.run",
                {"target_fasta": fasta, "dry_run": True, "num_seq_per_tier": 2, "conservation_tiers": [0.3]},
            )
            self.assertIn("run_id", out)
            self.assertIn("output_dir", out)
            json.dumps(out)

    def test_pipeline_run_tool_respects_run_id(self) -> None:
        fasta = ">q1\nACDEFGHIK\n"
        pdb = (
            "ATOM      1  CA  ALA A   1       0.000   0.000   0.000  1.00 20.00           C\n"
            "ATOM      2  CA  CYS A   2       1.000   0.000   0.000  1.00 20.00           C\n"
            "ATOM      3  CA  ASP A   3       2.000   0.000   0.000  1.00 20.00           C\n"
            "ATOM      4  CA  GLU A   4       3.000   0.000   0.000  1.00 20.00           C\n"
            "ATOM      5  CA  PHE A   5       4.000   0.000   0.000  1.00 20.00           C\n"
            "ATOM      6  CA  GLY A   6       5.000   0.000   0.000  1.00 20.00           C\n"
            "ATOM      7  CA  HIS A   7       6.000   0.000   0.000  1.00 20.00           C\n"
            "ATOM      8  CA  ILE A   8       7.000   0.000   0.000  1.00 20.00           C\n"
            "ATOM      9  CA  LYS A   9       8.000   0.000   0.000  1.00 20.00           C\n"
            "END\n"
        )
        with _tmpdir() as tmp:
            runner = PipelineRunner(output_root=tmp, mmseqs=None, proteinmpnn=None, soluprot=None, af2=None)
            dispatcher = ToolDispatcher(runner)
            out = dispatcher.call_tool(
                "pipeline.run",
                {"target_fasta": fasta, "target_pdb": pdb, "dry_run": True, "run_id": "my_test_run"},
            )
            self.assertEqual(Path(str(out.get("output_dir") or "")).name, "my_test_run")

    def test_pipeline_run_tool_accepts_rfd3_inputs(self) -> None:
        pdb = (
            "ATOM      1  CA  ALA A   1       0.000   0.000   0.000  1.00 20.00           C\n"
            "ATOM      2  CA  GLY A   2       1.000   0.000   0.000  1.00 20.00           C\n"
            "END\n"
        )
        with _tmpdir() as tmp:
            runner = PipelineRunner(output_root=tmp, mmseqs=None, proteinmpnn=None, soluprot=None, af2=None, rfd3=None)
            dispatcher = ToolDispatcher(runner)
            out = dispatcher.call_tool(
                "pipeline.run",
                {
                    "rfd3_contig": "A:1-2",
                    "rfd3_input_pdb": pdb,
                    "dry_run": True,
                    "num_seq_per_tier": 1,
                    "conservation_tiers": [0.3],
                },
            )
            self.assertIn("run_id", out)
            self.assertIn("output_dir", out)


if __name__ == "__main__":
    unittest.main()
