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
                    "rfd3_contig": "A1-2",
                    "rfd3_input_pdb": pdb,
                    "dry_run": True,
                    "num_seq_per_tier": 1,
                    "conservation_tiers": [0.3],
                },
            )
            self.assertIn("run_id", out)
            self.assertIn("output_dir", out)

    def test_pipeline_af2_predict_dry_run(self) -> None:
        fasta = ">s1\nACDEFGHIK\n"
        with _tmpdir() as tmp:
            runner = PipelineRunner(output_root=tmp, mmseqs=None, proteinmpnn=None, soluprot=None, af2=None)
            dispatcher = ToolDispatcher(runner)
            out = dispatcher.call_tool(
                "pipeline.af2_predict",
                {"target_fasta": fasta, "dry_run": True},
            )
            run_id = str(out.get("run_id") or "")
            self.assertTrue(run_id)

            listing = dispatcher.call_tool("pipeline.list_artifacts", {"run_id": run_id, "limit": 200})
            artifacts = listing.get("artifacts") or []
            paths = {str(a.get("path")) for a in artifacts if isinstance(a, dict)}
            self.assertIn("af2/s1/ranked_0.pdb", paths)

    def test_pipeline_diffdock_dry_run(self) -> None:
        pdb = (
            "ATOM      1  CA  ALA A   1       0.000   0.000   0.000  1.00 20.00           C\n"
            "ATOM      2  CA  GLY A   2       1.000   0.000   0.000  1.00 20.00           C\n"
            "END\n"
        )
        with _tmpdir() as tmp:
            runner = PipelineRunner(output_root=tmp, mmseqs=None, proteinmpnn=None, soluprot=None, af2=None)
            dispatcher = ToolDispatcher(runner)
            out = dispatcher.call_tool(
                "pipeline.diffdock",
                {"protein_pdb": pdb, "ligand_smiles": "CCO", "dry_run": True},
            )
            run_id = str(out.get("run_id") or "")
            self.assertTrue(run_id)

            listing = dispatcher.call_tool("pipeline.list_artifacts", {"run_id": run_id, "limit": 200})
            artifacts = listing.get("artifacts") or []
            paths = {str(a.get("path")) for a in artifacts if isinstance(a, dict)}
            self.assertIn("diffdock/output.json", paths)

    def test_pipeline_feedback_and_report(self) -> None:
        fasta = ">q1\nACDEFGHIK\n"
        with _tmpdir() as tmp:
            runner = PipelineRunner(output_root=tmp, mmseqs=None, proteinmpnn=None, soluprot=None, af2=None)
            dispatcher = ToolDispatcher(runner)
            out = dispatcher.call_tool(
                "pipeline.run",
                {"target_fasta": fasta, "dry_run": True, "num_seq_per_tier": 1, "conservation_tiers": [0.3]},
            )
            run_id = str(out.get("run_id") or "")
            self.assertTrue(run_id)

            dispatcher.call_tool(
                "pipeline.submit_feedback",
                {"run_id": run_id, "rating": "good", "reasons": ["low_novelty"], "comment": "ok"},
            )
            feedback = dispatcher.call_tool("pipeline.list_feedback", {"run_id": run_id, "limit": 5})
            items = feedback.get("items") or []
            self.assertTrue(items)

            dispatcher.call_tool(
                "pipeline.submit_experiment",
                {"run_id": run_id, "result": "success", "assay_type": "binding"},
            )
            experiments = dispatcher.call_tool("pipeline.list_experiments", {"run_id": run_id, "limit": 5})
            self.assertTrue(experiments.get("items"))

            report = dispatcher.call_tool("pipeline.generate_report", {"run_id": run_id})
            self.assertIn("report", report)
            self.assertIn("Score", str(report.get("report")))

    def test_pipeline_artifact_tools(self) -> None:
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
                    "num_seq_per_tier": 1,
                    "conservation_tiers": [0.3],
                },
            )
            run_id = str(out.get("run_id") or "")
            self.assertTrue(run_id)

            listing = dispatcher.call_tool("pipeline.list_artifacts", {"run_id": run_id, "limit": 200})
            artifacts = listing.get("artifacts") or []
            paths = {str(a.get("path")) for a in artifacts if isinstance(a, dict)}
            self.assertIn("request.json", paths)

            read_out = dispatcher.call_tool(
                "pipeline.read_artifact",
                {"run_id": run_id, "path": "request.json", "max_bytes": 64},
            )
            self.assertIn("text", read_out)
            self.assertLessEqual(int(read_out.get("read_bytes") or 0), 64)




    def test_pipeline_plan_from_prompt_missing_target(self) -> None:
        with _tmpdir() as tmp:
            runner = PipelineRunner(output_root=tmp, mmseqs=None, proteinmpnn=None, soluprot=None, af2=None)
            dispatcher = ToolDispatcher(runner)
            out = dispatcher.call_tool(
                "pipeline.plan_from_prompt",
                {"prompt": "run design with rfd3 diffusion"},
            )
            missing = out.get("missing") or []
            self.assertIn("target_input", missing)

    def test_pipeline_plan_from_prompt_parses_contig(self) -> None:
        pdb = (
            "ATOM      1  CA  ALA A   1       0.000   0.000   0.000  1.00 20.00           C\n"
            "ATOM      2  CA  GLY A   2       1.000   0.000   0.000  1.00 20.00           C\n"
            "END\n"
        )
        with _tmpdir() as tmp:
            runner = PipelineRunner(output_root=tmp, mmseqs=None, proteinmpnn=None, soluprot=None, af2=None)
            dispatcher = ToolDispatcher(runner)
            out = dispatcher.call_tool(
                "pipeline.plan_from_prompt",
                {
                    "prompt": "rfd3 contig A1-2 design",
                    "target_pdb": pdb,
                },
            )
            routed = out.get("routed_request") or {}
            self.assertEqual(routed.get("rfd3_contig"), "A1-2")
if __name__ == "__main__":
    unittest.main()
