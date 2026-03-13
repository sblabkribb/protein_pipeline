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

    def test_pipeline_run_novelty_stage_wt_based_without_mmseqs_client(self) -> None:
        fasta = ">q1\nACDEFGHIK\n"
        with _tmpdir() as tmp:
            runner = PipelineRunner(output_root=tmp, mmseqs=None, proteinmpnn=None, soluprot=None, af2=None)
            dispatcher = ToolDispatcher(runner)
            out = dispatcher.call_tool(
                "pipeline.run",
                {
                    "target_fasta": fasta,
                    "dry_run": True,
                    "stop_after": "novelty",
                    "novelty_enabled": True,
                    "num_seq_per_tier": 1,
                    "conservation_tiers": [0.3],
                    "soluprot_cutoff": 0.0,
                    "af2_plddt_cutoff": 0.0,
                    "af2_rmsd_cutoff": 999.0,
                },
            )
            run_id = str(out.get("run_id") or "")
            self.assertTrue(run_id)

            status = dispatcher.call_tool("pipeline.read_artifact", {"run_id": run_id, "path": "status.json"})
            status_text = str(status.get("text") or "")
            self.assertIn('"state": "completed"', status_text)
            summary = dispatcher.call_tool("pipeline.read_artifact", {"run_id": run_id, "path": "summary.json"})
            summary_text = str(summary.get("text") or "")
            self.assertNotIn("MMseqs client is not configured", summary_text)

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

    def test_pipeline_list_artifacts_keeps_root_input_snapshot_but_hides_internal_original_pdb(self) -> None:
        pdb = (
            "ATOM      1  CA  ALA A  -1       0.000   0.000   0.000  1.00 20.00           C\n"
            "ATOM      2  CA  GLY A   1       1.000   0.000   0.000  1.00 20.00           C\n"
            "END\n"
        )
        with _tmpdir() as tmp:
            runner = PipelineRunner(output_root=tmp, mmseqs=None, proteinmpnn=None, soluprot=None, af2=None)
            dispatcher = ToolDispatcher(runner)
            out = dispatcher.call_tool(
                "pipeline.run",
                {
                    "target_fasta": "",
                    "target_pdb": pdb,
                    "dry_run": True,
                    "num_seq_per_tier": 1,
                    "conservation_tiers": [0.3],
                    "pdb_strip_nonpositive_resseq": True,
                    "pdb_renumber_resseq_from_1": True,
                },
            )
            output_dir = Path(str(out.get("output_dir") or ""))
            self.assertTrue((output_dir / "target.original.pdb").exists())
            internal_original = output_dir / "backbones" / "demo" / "target.original.pdb"
            internal_original.parent.mkdir(parents=True, exist_ok=True)
            internal_original.write_text("END\n", encoding="utf-8")
            listed = dispatcher.call_tool(
                "pipeline.list_artifacts",
                {"run_id": output_dir.name, "max_depth": 3, "limit": 200},
            )
            paths = {str(item.get("path") or "") for item in (listed.get("artifacts") or []) if isinstance(item, dict)}
            self.assertIn("target.pdb", paths)
            self.assertIn("target.original.pdb", paths)
            self.assertNotIn("backbones/demo/target.original.pdb", paths)

    def test_pipeline_save_and_get_workflow_session(self) -> None:
        fasta = ">q1\nACDEFGHIK\n"
        with _tmpdir() as tmp:
            runner = PipelineRunner(output_root=tmp, mmseqs=None, proteinmpnn=None, soluprot=None, af2=None)
            dispatcher = ToolDispatcher(runner)
            out = dispatcher.call_tool(
                "pipeline.run",
                {"target_fasta": fasta, "dry_run": True, "stop_after": "msa", "run_id": "workflow_session_case"},
            )
            run_id = str(out.get("run_id") or "")
            session = {
                "session_id": "studio_session_001",
                "head_run_id": run_id,
                "nodes": ["msa", "design", "af2"],
            }
            saved = dispatcher.call_tool(
                "pipeline.save_workflow_session",
                {"run_id": run_id, "session": session},
            )
            self.assertTrue(bool(saved.get("saved")))
            self.assertEqual(str(saved.get("path") or ""), "workflow_studio/session.json")

            loaded = dispatcher.call_tool("pipeline.get_workflow_session", {"run_id": run_id})
            self.assertTrue(bool(loaded.get("found")))
            self.assertEqual((loaded.get("session") or {}).get("session_id"), "studio_session_001")

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

    def test_pipeline_preflight_soluprot_start_requires_design_outputs(self) -> None:
        with _tmpdir() as tmp:
            runner = PipelineRunner(output_root=tmp, mmseqs=None, proteinmpnn=None, soluprot=None, af2=None)
            dispatcher = ToolDispatcher(runner)
            run_id = "resume_soluprot_case"
            init_run(tmp, run_id)
            out = dispatcher.call_tool(
                "pipeline.preflight",
                {
                    "run_id": run_id,
                    "target_fasta": ">q1\nACDEFGHIK\n",
                    "start_from": "soluprot",
                    "stop_after": "soluprot",
                },
            )
            self.assertFalse(bool(out.get("ok")))
            errors = [str(x) for x in (out.get("errors") or [])]
            self.assertTrue(any("Design/ProteinMPNN outputs" in e for e in errors))

    def test_pipeline_preflight_af2_start_accepts_existing_soluprot_passed_sequences(self) -> None:
        with _tmpdir() as tmp:
            runner = PipelineRunner(output_root=tmp, mmseqs=None, proteinmpnn=None, soluprot=None, af2=None)
            dispatcher = ToolDispatcher(runner)
            run_id = "resume_af2_case"
            paths = init_run(tmp, run_id)
            tier_dir = paths.root / "tiers" / "30"
            tier_dir.mkdir(parents=True, exist_ok=True)
            (tier_dir / "designs_filtered.fasta").write_text(">seq1\nACDEFGHIK\n", encoding="utf-8")
            out = dispatcher.call_tool(
                "pipeline.preflight",
                {
                    "run_id": run_id,
                    "target_fasta": ">q1\nACDEFGHIK\n",
                    "start_from": "af2",
                    "stop_after": "af2",
                },
            )
            self.assertTrue(bool(out.get("ok")))

    def test_pipeline_preflight_novelty_start_requires_af2_selected_sequences(self) -> None:
        with _tmpdir() as tmp:
            runner = PipelineRunner(output_root=tmp, mmseqs=None, proteinmpnn=None, soluprot=None, af2=None)
            dispatcher = ToolDispatcher(runner)
            run_id = "resume_novelty_case"
            paths = init_run(tmp, run_id)
            tier_dir = paths.root / "tiers" / "30"
            tier_dir.mkdir(parents=True, exist_ok=True)
            (tier_dir / "af2_selected.fasta").write_text("", encoding="utf-8")
            out = dispatcher.call_tool(
                "pipeline.preflight",
                {
                    "run_id": run_id,
                    "target_fasta": ">q1\nACDEFGHIK\n",
                    "start_from": "novelty",
                    "stop_after": "novelty",
                },
            )
            self.assertFalse(bool(out.get("ok")))
            errors = [str(x) for x in (out.get("errors") or [])]
            self.assertTrue(any("AF2-selected sequences" in e for e in errors))

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

    def test_pipeline_request_defaults_wt_diff_enabled(self) -> None:
        req = pipeline_request_from_args({"target_fasta": ">q1\nACDEFGHIK\n"})
        self.assertTrue(req.novelty_enabled)

    def test_pipeline_request_normalizes_wt_diff_stage_alias(self) -> None:
        req = pipeline_request_from_args(
            {
                "target_fasta": ">q1\nACDEFGHIK\n",
                "start_from": "wt_diff",
                "stop_after": "wt_diff",
            }
        )
        self.assertEqual(req.start_from, "novelty")
        self.assertEqual(req.stop_after, "novelty")

    def test_pipeline_request_parses_start_from(self) -> None:
        req = pipeline_request_from_args(
            {
                "target_fasta": ">q1\nACDEFGHIK\n",
                "start_from": "SoLuPrOt",
                "stop_after": "novelty",
            }
        )
        self.assertEqual(req.start_from, "soluprot")
        self.assertEqual(req.stop_after, "novelty")

    def test_pipeline_request_parses_selected_tiers_subset(self) -> None:
        req = pipeline_request_from_args(
            {
                "target_fasta": ">q1\nACDEFGHIK\n",
                "conservation_tiers": [0.3, 0.5, 0.7],
                "selected_tiers": [0.5],
            }
        )
        self.assertEqual(req.conservation_tiers, [0.3, 0.5, 0.7])
        self.assertEqual(req.selected_tiers, [0.5])

    def test_pipeline_preflight_rejects_start_from_after_stop_after(self) -> None:
        with _tmpdir() as tmp:
            runner = PipelineRunner(output_root=tmp, mmseqs=None, proteinmpnn=None, soluprot=None, af2=None)
            dispatcher = ToolDispatcher(runner)
            out = dispatcher.call_tool(
                "pipeline.preflight",
                {
                    "target_fasta": ">q1\nACDEFGHIK\n",
                    "start_from": "af2",
                    "stop_after": "msa",
                },
            )
            self.assertFalse(bool(out.get("ok")))
            errors = [str(x) for x in (out.get("errors") or [])]
            self.assertTrue(any("start_from" in e and "stop_after" in e for e in errors))

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
            self.assertIn("Backbone generation/use", report_text)
            self.assertIn("WT change (n/len · identity)", report_text)
            comparison_summary = report.get("comparison_summary") or {}
            self.assertIn("wt_vs_design", comparison_summary)
            self.assertIn("source_compare", comparison_summary)
            self.assertIn("funnel", comparison_summary)
            self.assertIn("tier_compare", comparison_summary)
            self.assertIn("distributions", comparison_summary)
            self.assertIn("diversity", comparison_summary)
            source_compare = comparison_summary.get("source_compare") or {}
            if isinstance(source_compare, dict):
                for bucket in source_compare.values():
                    if not isinstance(bucket, dict):
                        continue
                    self.assertIn("requested_count", bucket)
                    self.assertIn("observed_count", bucket)
                    self.assertIn("materialized_count", bucket)
                    self.assertIn("propagated_count", bucket)
                    self.assertIn("propagation_mode", bucket)
                    self.assertIn("plddt_median", bucket)
                    self.assertIn("rmsd_median", bucket)
            tier_compare = comparison_summary.get("tier_compare") or []
            if isinstance(tier_compare, list):
                for row in tier_compare:
                    if not isinstance(row, dict):
                        continue
                    self.assertIn("plddt_median", row)
                    self.assertIn("rmsd_median", row)

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
            source_compare = comparison_summary.get("source_compare") or {}
            if isinstance(source_compare, dict):
                for bucket in source_compare.values():
                    if not isinstance(bucket, dict):
                        continue
                    self.assertIn("requested_count", bucket)
                    self.assertIn("observed_count", bucket)
                    self.assertIn("materialized_count", bucket)
                    self.assertIn("propagated_count", bucket)
                    self.assertIn("propagation_mode", bucket)
                    self.assertIn("plddt_median", bucket)
                    self.assertIn("rmsd_median", bucket)

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




    def test_get_hit_list_uses_target_pdb_for_wt_difference_metrics(self) -> None:
        pdb = (
            "ATOM      1  CA  ALA A   1       0.000   0.000   0.000  1.00 20.00           C\n"
            "ATOM      2  CA  CYS A   2       1.000   0.000   0.000  1.00 20.00           C\n"
            "ATOM      3  CA  ASP A   3       2.000   0.000   0.000  1.00 20.00           C\n"
            "ATOM      4  CA  GLU A   4       3.000   0.000   0.000  1.00 20.00           C\n"
            "END\n"
        )
        with _tmpdir() as tmp:
            runner = PipelineRunner(output_root=tmp, mmseqs=None, proteinmpnn=None, soluprot=None, af2=None)
            dispatcher = ToolDispatcher(runner)
            out = dispatcher.call_tool(
                "pipeline.run",
                {"target_pdb": pdb, "dry_run": True, "num_seq_per_tier": 1, "conservation_tiers": [0.3]},
            )
            run_id = str(out.get("run_id") or "")
            self.assertTrue(run_id)

            hit_list = dispatcher.call_tool(
                "pipeline.get_hit_list",
                {"run_id": run_id, "limit": 50, "min_score": 0.0},
            )
            rows = hit_list.get("rows") or []
            self.assertTrue(rows)
            top = rows[0] if isinstance(rows[0], dict) else {}
            self.assertIn("wt_diff_count", top)
            self.assertIn("wt_compare_len", top)
            self.assertIn("wt_diff_pct", top)
            self.assertIsInstance(top.get("wt_compare_len"), (int, float))
            self.assertGreater(float(top.get("wt_compare_len") or 0), 0.0)
            self.assertIsInstance(top.get("novelty"), (int, float))
            self.assertIsInstance(top.get("wt_diff_ratio"), (int, float))
            self.assertAlmostEqual(
                float(top.get("novelty") or 0.0),
                float(top.get("wt_diff_ratio") or 0.0),
                places=6,
            )

    def test_get_hit_list_prefers_saved_design_chains_for_wt_difference_metrics(self) -> None:
        pdb = (
            "ATOM      1  CA  ALA A   1       0.000   0.000   0.000  1.00 20.00           C\n"
            "ATOM      2  CA  ALA A   2       1.000   0.000   0.000  1.00 20.00           C\n"
            "ATOM      3  CA  ALA A   3       2.000   0.000   0.000  1.00 20.00           C\n"
            "ATOM      4  CA  ALA A   4       3.000   0.000   0.000  1.00 20.00           C\n"
            "ATOM      5  CA  CYS B   1       0.000   1.000   0.000  1.00 20.00           C\n"
            "ATOM      6  CA  CYS B   2       1.000   1.000   0.000  1.00 20.00           C\n"
            "ATOM      7  CA  CYS B   3       2.000   1.000   0.000  1.00 20.00           C\n"
            "ATOM      8  CA  CYS B   4       3.000   1.000   0.000  1.00 20.00           C\n"
            "ATOM      9  CA  CYS B   5       4.000   1.000   0.000  1.00 20.00           C\n"
            "ATOM     10  CA  CYS B   6       5.000   1.000   0.000  1.00 20.00           C\n"
            "END\n"
        )
        with _tmpdir() as tmp:
            runner = PipelineRunner(output_root=tmp, mmseqs=None, proteinmpnn=None, soluprot=None, af2=None)
            dispatcher = ToolDispatcher(runner)
            out = dispatcher.call_tool(
                "pipeline.run",
                {"target_pdb": pdb, "dry_run": True, "num_seq_per_tier": 1, "conservation_tiers": [0.3]},
            )
            run_id = str(out.get("run_id") or "")
            run_dir = Path(str(out.get("output_dir") or ""))
            self.assertTrue(run_id)
            self.assertTrue(run_dir.exists())

            saved_chain_payload = {
                "design_chains_used": ["B"],
                "requested_design_chains": None,
                "available_chains": ["A", "B"],
            }
            (run_dir / "query_pdb_alignment.json").write_text(
                json.dumps(saved_chain_payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            (run_dir / "chain_strategy.json").write_text(
                json.dumps(saved_chain_payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            hit_list = dispatcher.call_tool(
                "pipeline.get_hit_list",
                {"run_id": run_id, "limit": 50, "min_score": 0.0},
            )
            rows = hit_list.get("rows") or []
            self.assertTrue(rows)
            top = rows[0] if isinstance(rows[0], dict) else {}
            self.assertEqual(int(top.get("wt_compare_len") or 0), 6)
            self.assertEqual(int(top.get("wt_diff_count") or 0), 6)
            self.assertAlmostEqual(float(top.get("wt_diff_pct") or 0.0), 100.0, places=6)

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

    def test_pipeline_plan_from_prompt_defaults_wt_diff_and_num_seq_questions(self) -> None:
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
            self.assertEqual((by_id.get("stop_after") or {}).get("default"), "novelty")
            self.assertEqual((by_id.get("af2_max_candidates_per_tier") or {}).get("default"), 0)
            self.assertEqual((by_id.get("num_seq_per_tier") or {}).get("default"), 2)
if __name__ == "__main__":
    unittest.main()
