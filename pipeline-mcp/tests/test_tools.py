import unittest
import json
import uuid
from contextlib import contextmanager
from pathlib import Path

from pipeline_mcp.models import PipelineRequest
from pipeline_mcp.pipeline import PipelineRunner
from pipeline_mcp.storage import init_run
from pipeline_mcp.storage import set_status
from pipeline_mcp.tools import ToolDispatcher
from pipeline_mcp.tools import AutoRetryConfig
from pipeline_mcp.tools import _run_with_auto_retry
from pipeline_mcp.tools import pipeline_request_from_args


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

    def test_pipeline_run_rejects_running_run_id(self) -> None:
        fasta = ">q1\nACDEFGHIK\n"
        with _tmpdir() as tmp:
            runner = PipelineRunner(output_root=tmp, mmseqs=None, proteinmpnn=None, soluprot=None, af2=None)
            dispatcher = ToolDispatcher(runner)
            paths = init_run(tmp, "busy_run")
            set_status(paths, stage="init", state="running")
            with self.assertRaisesRegex(ValueError, "already running"):
                dispatcher.call_tool(
                    "pipeline.run",
                    {"target_fasta": fasta, "dry_run": True, "run_id": "busy_run"},
                )

    def test_pipeline_preflight_without_target_returns_required_inputs(self) -> None:
        with _tmpdir() as tmp:
            runner = PipelineRunner(output_root=tmp, mmseqs=None, proteinmpnn=None, soluprot=None, af2=None)
            dispatcher = ToolDispatcher(runner)
            out = dispatcher.call_tool("pipeline.preflight", {})
            self.assertFalse(bool(out.get("ok")))
            required = out.get("required_inputs") or []
            ids = {str(item.get("id")) for item in required if isinstance(item, dict)}
            self.assertIn("target_input", ids)

    def test_pipeline_preflight_bioemu_stop_requires_bioemu_use(self) -> None:
        with _tmpdir() as tmp:
            runner = PipelineRunner(output_root=tmp, mmseqs=None, proteinmpnn=None, soluprot=None, af2=None)
            dispatcher = ToolDispatcher(runner)
            out = dispatcher.call_tool(
                "pipeline.preflight",
                {
                    "target_fasta": ">q1\nACDEFGHIK\n",
                    "stop_after": "bioemu",
                },
            )
            self.assertFalse(bool(out.get("ok")))
            errors = [str(x) for x in (out.get("errors") or [])]
            self.assertTrue(any("bioemu_use" in e for e in errors))

    def test_pipeline_preflight_rfd3_stop_requires_rfd3_inputs(self) -> None:
        with _tmpdir() as tmp:
            runner = PipelineRunner(output_root=tmp, mmseqs=None, proteinmpnn=None, soluprot=None, af2=None)
            dispatcher = ToolDispatcher(runner)
            out = dispatcher.call_tool(
                "pipeline.preflight",
                {
                    "target_fasta": ">q1\nACDEFGHIK\n",
                    "stop_after": "rfd3",
                },
            )
            self.assertFalse(bool(out.get("ok")))
            errors = [str(x) for x in (out.get("errors") or [])]
            self.assertTrue(any("stop_after='rfd3'" in e for e in errors))

    def test_pipeline_preflight_accepts_sequence_only_bioemu(self) -> None:
        with _tmpdir() as tmp:
            runner = PipelineRunner(output_root=tmp, mmseqs=None, proteinmpnn=None, soluprot=None, af2=None)
            dispatcher = ToolDispatcher(runner)
            out = dispatcher.call_tool(
                "pipeline.preflight",
                {
                    "bioemu_use": True,
                    "bioemu_sequence": "ACDEFGHIK",
                    "stop_after": "bioemu",
                },
            )
            self.assertTrue(bool(out.get("ok")))
            required = out.get("required_inputs") or []
            ids = {str(item.get("id")) for item in required if isinstance(item, dict)}
            self.assertNotIn("target_input", ids)
            self.assertNotIn("fixed_positions_extra", ids)

    def test_pipeline_run_rfd3_stop_requires_rfd3_inputs(self) -> None:
        with _tmpdir() as tmp:
            runner = PipelineRunner(output_root=tmp, mmseqs=None, proteinmpnn=None, soluprot=None, af2=None)
            dispatcher = ToolDispatcher(runner)
            with self.assertRaisesRegex(ValueError, "stop_after='rfd3' requires rfd3 inputs"):
                dispatcher.call_tool(
                    "pipeline.run",
                    {
                        "target_fasta": ">q1\nACDEFGHIK\n",
                        "stop_after": "rfd3",
                        "dry_run": True,
                    },
                )

    def test_auto_retry_does_not_retry_cancelled_error(self) -> None:
        req = PipelineRequest(target_fasta=">q1\nACDE\n", target_pdb="", dry_run=False)

        class _StubRunner:
            def __init__(self) -> None:
                self.calls = 0

            def run(self, request: PipelineRequest, *, run_id: str | None = None):  # type: ignore[no-untyped-def]
                self.calls += 1
                raise RuntimeError("MMseqs RunPod job not completed: {'status': 'CANCELLED'}")

        stub = _StubRunner()
        retry = AutoRetryConfig(enabled=True, max_attempts=3, backoff_s=0.0)
        with self.assertRaisesRegex(RuntimeError, "CANCELLED"):
            _run_with_auto_retry(stub, req, run_id="cancel_case", retry=retry)  # type: ignore[arg-type]
        self.assertEqual(stub.calls, 1)

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

    def test_pipeline_request_parses_bioemu_args(self) -> None:
        req = pipeline_request_from_args(
            {
                "target_fasta": ">q1\nACDEFGHIK\n",
                "bioemu_use": True,
                "bioemu_num_samples": 25,
                "bioemu_model_name": "bioemu-v1.1",
                "bioemu_max_return_structures": 12,
                "bioemu_base_seed": 7,
                "af2_max_candidates_per_tier": 5,
                "bioemu_env": {"BIOEMU_COLABFOLD_DIR": "/runpod-volume/bioemu/colabfold"},
                "ligand_mask_use_original_target": False,
            }
        )
        self.assertTrue(req.bioemu_use)
        self.assertEqual(req.bioemu_num_samples, 25)
        self.assertEqual(req.bioemu_model_name, "bioemu-v1.1")
        self.assertEqual(req.bioemu_max_return_structures, 12)
        self.assertEqual(req.bioemu_base_seed, 7)
        self.assertEqual(req.af2_max_candidates_per_tier, 5)
        self.assertEqual(req.bioemu_env, {"BIOEMU_COLABFOLD_DIR": "/runpod-volume/bioemu/colabfold"})
        self.assertFalse(req.ligand_mask_use_original_target)

    def test_pipeline_request_defaults_original_ligand_mask_on(self) -> None:
        req = pipeline_request_from_args({"target_fasta": ">q1\nACDEFGHIK\n"})
        self.assertTrue(req.ligand_mask_use_original_target)

    def test_pipeline_run_bioemu_stop_dry_run_without_target_pdb(self) -> None:
        fasta = ">q1\nACDEFGHIK\n"
        with _tmpdir() as tmp:
            runner = PipelineRunner(output_root=tmp, mmseqs=None, proteinmpnn=None, soluprot=None, af2=None, bioemu=None)
            dispatcher = ToolDispatcher(runner)
            out = dispatcher.call_tool(
                "pipeline.run",
                {
                    "target_fasta": fasta,
                    "bioemu_use": True,
                    "stop_after": "bioemu",
                    "bioemu_num_samples": 2,
                    "bioemu_max_return_structures": 2,
                    "dry_run": True,
                },
            )
            run_id = str(out.get("run_id") or "")
            self.assertTrue(run_id)

            listing = dispatcher.call_tool("pipeline.list_artifacts", {"run_id": run_id, "limit": 200})
            artifacts = listing.get("artifacts") or []
            paths = {str(a.get("path")) for a in artifacts if isinstance(a, dict)}
            self.assertIn("bioemu/sample_pdbs.json", paths)

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
            report_text = str(report.get("report"))
            self.assertIn("Score", report_text)
            self.assertIn("WT Comparison", report_text)
            self.assertIn("Backbone Source Comparison", report_text)
            comparison_summary = report.get("comparison_summary") or {}
            self.assertIn("wt_vs_design", comparison_summary)
            self.assertIn("source_compare", comparison_summary)
            self.assertIn("funnel", comparison_summary)
            self.assertIn("tier_compare", comparison_summary)
            self.assertIn("distributions", comparison_summary)
            self.assertIn("diversity", comparison_summary)

            listing = dispatcher.call_tool("pipeline.list_artifacts", {"run_id": run_id, "limit": 200})
            artifacts = listing.get("artifacts") or []
            paths = {str(a.get("path")) for a in artifacts if isinstance(a, dict)}
            self.assertIn("comparisons.json", paths)

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

    def test_get_report_includes_comparison_summary_even_without_prebuilt_artifact(self) -> None:
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

            dispatcher.call_tool("pipeline.generate_report", {"run_id": run_id})
            comp_path = Path(tmp) / run_id / "comparisons.json"
            if comp_path.exists():
                comp_path.unlink()

            report_payload = dispatcher.call_tool("pipeline.get_report", {"run_id": run_id})
            comparison_summary = report_payload.get("comparison_summary") or {}
            self.assertIn("wt_vs_design", comparison_summary)
            self.assertIn("source_compare", comparison_summary)
            self.assertIn("funnel", comparison_summary)
            self.assertIn("tier_compare", comparison_summary)

    def test_compare_runs_hit_list_and_export_package_tools(self) -> None:
        fasta = ">q1\nACDEFGHIK\n"
        with _tmpdir() as tmp:
            runner = PipelineRunner(output_root=tmp, mmseqs=None, proteinmpnn=None, soluprot=None, af2=None)
            dispatcher = ToolDispatcher(runner)
            out1 = dispatcher.call_tool(
                "pipeline.run",
                {"target_fasta": fasta, "dry_run": True, "num_seq_per_tier": 1, "conservation_tiers": [0.3]},
            )
            run1 = str(out1.get("run_id") or "")
            self.assertTrue(run1)
            out2 = dispatcher.call_tool(
                "pipeline.run",
                {"target_fasta": fasta, "dry_run": True, "num_seq_per_tier": 1, "conservation_tiers": [0.3]},
            )
            run2 = str(out2.get("run_id") or "")
            self.assertTrue(run2)

            compare = dispatcher.call_tool(
                "pipeline.compare_runs",
                {"run_id": run2, "baseline_run_id": run1},
            )
            self.assertEqual(compare.get("run_id"), run2)
            self.assertEqual(compare.get("baseline_run_id"), run1)
            self.assertIn("delta", compare)

            hit_list = dispatcher.call_tool(
                "pipeline.get_hit_list",
                {"run_id": run2, "limit": 50, "min_score": 0.0},
            )
            self.assertEqual(hit_list.get("run_id"), run2)
            self.assertIn("rows", hit_list)
            self.assertIsInstance(hit_list.get("rows"), list)

            dispatcher.call_tool("pipeline.generate_report", {"run_id": run2})
            package = dispatcher.call_tool(
                "pipeline.export_results_package",
                {"run_id": run2, "include_top_n": 5},
            )
            path = str(package.get("path") or "")
            self.assertTrue(path.endswith(".zip"))
            self.assertTrue(path.startswith("exports/"))

            listing = dispatcher.call_tool("pipeline.list_artifacts", {"run_id": run2, "limit": 500})
            artifacts = listing.get("artifacts") or []
            paths = {str(a.get("path")) for a in artifacts if isinstance(a, dict)}
            self.assertIn(path, paths)




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

    def test_pipeline_plan_from_prompt_enables_bioemu(self) -> None:
        with _tmpdir() as tmp:
            runner = PipelineRunner(output_root=tmp, mmseqs=None, proteinmpnn=None, soluprot=None, af2=None)
            dispatcher = ToolDispatcher(runner)
            out = dispatcher.call_tool(
                "pipeline.plan_from_prompt",
                {"prompt": "run bioemu backbone sampling"},
            )
            routed = out.get("routed_request") or {}
            self.assertTrue(bool(routed.get("bioemu_use")))

    def test_pipeline_plan_from_prompt_defaults_af2_and_num_seq_questions(self) -> None:
        with _tmpdir() as tmp:
            runner = PipelineRunner(output_root=tmp, mmseqs=None, proteinmpnn=None, soluprot=None, af2=None)
            dispatcher = ToolDispatcher(runner)
            out = dispatcher.call_tool(
                "pipeline.plan_from_prompt",
                {"prompt": "run full pipeline"},
            )
            questions = out.get("questions") or []
            by_id = {
                str(item.get("id")): item
                for item in questions
                if isinstance(item, dict) and str(item.get("id") or "").strip()
            }
            self.assertEqual((by_id.get("af2_max_candidates_per_tier") or {}).get("default"), 0)
            self.assertEqual((by_id.get("num_seq_per_tier") or {}).get("default"), 2)
if __name__ == "__main__":
    unittest.main()
