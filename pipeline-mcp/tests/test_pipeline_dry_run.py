import base64
import gzip
import json
import unittest
import uuid
from contextlib import contextmanager
from pathlib import Path

from pipeline_mcp.bio.pdb import residues_by_chain
from pipeline_mcp.bio.pdb import sequence_by_chain
from pipeline_mcp.models import PipelineRequest
from pipeline_mcp.pipeline import _build_backbone_source_summaries
from pipeline_mcp.pipeline import _clear_stage_outputs_from
from pipeline_mcp.pipeline import _preprocess_pdb_text
from pipeline_mcp.pipeline import _resolve_backbone_preprocess_options
from pipeline_mcp.pipeline import PipelineInputRequired
from pipeline_mcp.pipeline import PipelineRunner


@contextmanager
def _tmpdir():
    base = Path(__file__).resolve().parent / "_tmp"
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"run_{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    yield str(path)


class TestPipelineDryRun(unittest.TestCase):
    def test_backbone_source_summary_marks_selected_only_when_observed_exceeds_used(self) -> None:
        req = PipelineRequest(
            target_fasta=">q1\nACDEFGHIK\n",
            target_pdb="",
            dry_run=True,
            rfd3_contig="A1-2",
            rfd3_input_pdb="ATOM      1  CA  ALA A   1       0.000   0.000   0.000  1.00 20.00           C\nEND\n",
            rfd3_max_return_designs=10,
        )
        summaries, mode = _build_backbone_source_summaries(
            req,
            backbone_entries=[
                {
                    "id": "rfd3_model_1",
                    "source": "rfd3",
                    "materialized": True,
                    "propagated": True,
                }
            ],
            observed_counts={"rfd3": 10},
            selected_ids={"rfd3": "rfd3_model_1"},
        )
        rfd3 = summaries.get("rfd3") if isinstance(summaries.get("rfd3"), dict) else {}
        self.assertEqual(rfd3.get("requested_count"), 10)
        self.assertEqual(rfd3.get("observed_count"), 10)
        self.assertEqual(rfd3.get("materialized_count"), 1)
        self.assertEqual(rfd3.get("propagated_count"), 1)
        self.assertEqual(rfd3.get("propagation_mode"), "selected_only")
        self.assertEqual(rfd3.get("selected_backbone_id"), "rfd3_model_1")
        self.assertEqual(mode, "selected_only")

    def test_bioemu_zero_resseq_is_renumbered_not_dropped(self) -> None:
        pdb = (
            "ATOM      1  CA  ALA A   0       0.000   0.000   0.000  1.00 20.00           C\n"
            "ATOM      2  CA  GLY A   1       1.000   0.000   0.000  1.00 20.00           C\n"
            "END\n"
        )

        strip_nonpositive, renumber_from_1, detail = _resolve_backbone_preprocess_options(
            pdb_text=pdb,
            source="bioemu",
            strip_nonpositive_resseq=True,
            renumber_resseq_from_1=False,
        )
        self.assertFalse(strip_nonpositive)
        self.assertTrue(renumber_from_1)
        self.assertEqual(detail, "bioemu_zero_resseq_renumbered_from_1")

        processed = _preprocess_pdb_text(
            pdb,
            chains=["A"],
            strip_nonpositive_resseq=strip_nonpositive,
            renumber_resseq_from_1=renumber_from_1,
        )
        self.assertEqual(sequence_by_chain(processed, chains=["A"]).get("A"), "AG")
        residues = residues_by_chain(processed, only_atom_records=True).get("A") or []
        self.assertEqual([res.resseq for res in residues], [1, 2])

    def test_pipeline_runs_and_writes_artifacts(self) -> None:
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
            req = PipelineRequest(target_fasta=fasta, target_pdb=pdb, dry_run=True, num_seq_per_tier=2, conservation_tiers=[0.3, 0.5])
            res = runner.run(req)

            out = Path(res.output_dir)
            self.assertTrue((out / "request.json").exists())
            self.assertTrue((out / "status.json").exists())
            self.assertTrue((out / "events.jsonl").exists())
            self.assertTrue((out / "msa" / "result.a3m").exists())
            self.assertTrue((out / "msa" / "quality.json").exists())
            self.assertTrue((out / "conservation.json").exists())
            self.assertTrue((out / "ligand_mask.json").exists())
            self.assertTrue((out / "query_pdb_alignment.json").exists())
            self.assertTrue((out / "agent_panel.jsonl").exists())
            self.assertTrue((out / "agent_panel_report.md").exists())

            self.assertEqual(len(res.tiers), 2)
            for tier_result in res.tiers:
                tier_dir = out / "tiers" / str(int(round(tier_result.tier * 100.0)))
                self.assertTrue((tier_dir / "fixed_positions.json").exists())
                self.assertTrue((tier_dir / "proteinmpnn.json").exists())
                self.assertTrue((tier_dir / "designs.fasta").exists())
                self.assertTrue((tier_dir / "fixed_positions_check.json").exists())
                self.assertTrue((tier_dir / "mutation_report.json").exists())
                self.assertTrue((tier_dir / "mutations_by_position.tsv").exists())
                self.assertTrue((tier_dir / "mutations_by_position.svg").exists())
                self.assertTrue((tier_dir / "mutations_by_sequence.tsv").exists())
                self.assertTrue((tier_dir / "soluprot.json").exists())
                self.assertTrue((tier_dir / "designs_filtered.fasta").exists())
                self.assertTrue((tier_dir / "af2_scores.json").exists())
                self.assertTrue((tier_dir / "af2_selected.fasta").exists())

    def test_surface_and_pi_filters(self) -> None:
        fasta = ">q1\nDDDDDDDD\n"
        pdb = (
            "ATOM      1  CA  ASP A   1       0.000   0.000   0.000  1.00 20.00           C\n"
            "ATOM      2  CA  ASP A   2       2.000   0.000   0.000  1.00 20.00           C\n"
            "ATOM      3  CA  ASP A   3       4.000   0.000   0.000  1.00 20.00           C\n"
            "ATOM      4  CA  ASP A   4       6.000   0.000   0.000  1.00 20.00           C\n"
            "ATOM      5  CA  ASP A   5       8.000   0.000   0.000  1.00 20.00           C\n"
            "ATOM      6  CA  ASP A   6      10.000   0.000   0.000  1.00 20.00           C\n"
            "END\n"
        )
        with _tmpdir() as tmp:
            runner = PipelineRunner(output_root=tmp, mmseqs=None, proteinmpnn=None, soluprot=None, af2=None)
            req = PipelineRequest(
                target_fasta=fasta,
                target_pdb=pdb,
                dry_run=True,
                conservation_tiers=[0.3],
                surface_only=True,
                pi_max=6.0,
            )
            res = runner.run(req)
            out = Path(res.output_dir)
            self.assertTrue((out / "surface_mask.json").exists())
            self.assertTrue((out / "tiers" / "30" / "pi_scores.json").exists())

    def test_pipeline_dry_run_generates_dummy_pdb_when_missing(self) -> None:
        fasta = ">q1\nACDEFGHIK\n"
        with _tmpdir() as tmp:
            runner = PipelineRunner(output_root=tmp, mmseqs=None, proteinmpnn=None, soluprot=None, af2=None)
            req = PipelineRequest(target_fasta=fasta, target_pdb="", dry_run=True, num_seq_per_tier=2, conservation_tiers=[0.3])
            res = runner.run(req)
            out = Path(res.output_dir)
            self.assertTrue((out / "ligand_mask.json").exists())

    def test_pipeline_dry_run_accepts_pdb_only(self) -> None:
        pdb = (
            "ATOM      1  CA  ALA A   1       0.000   0.000   0.000  1.00 20.00           C\n"
            "ATOM      2  CA  GLY A   2       1.000   0.000   0.000  1.00 20.00           C\n"
            "END\n"
        )
        with _tmpdir() as tmp:
            runner = PipelineRunner(output_root=tmp, mmseqs=None, proteinmpnn=None, soluprot=None, af2=None)
            req = PipelineRequest(target_fasta="", target_pdb=pdb, dry_run=True, num_seq_per_tier=2, conservation_tiers=[0.3])
            res = runner.run(req)
            out = Path(res.output_dir)
            self.assertTrue((out / "target.fasta").exists())
            self.assertTrue((out / "target.pdb").exists())
            self.assertTrue((out / "msa" / "result.a3m").exists())

    def test_pipeline_auto_recover_msa_without_mmseqs(self) -> None:
        fasta = ">q1\nACDEFGHIK\n"
        with _tmpdir() as tmp:
            runner = PipelineRunner(output_root=tmp, mmseqs=None, proteinmpnn=None, soluprot=None, af2=None)
            req = PipelineRequest(
                target_fasta=fasta,
                target_pdb="",
                dry_run=False,
                stop_after="msa",
                auto_recover=True,
            )
            res = runner.run(req)
            out = Path(res.output_dir)
            self.assertTrue((out / "msa" / "result.a3m").exists())
            self.assertTrue((out / "agent_panel.jsonl").exists())

    def test_pipeline_pdb_preprocess_strips_nonpositive_resseq(self) -> None:
        pdb = (
            "ATOM      1  CA  ALA A  -1       0.000   0.000   0.000  1.00 20.00           C\n"
            "ATOM      2  CA  GLY A   1       1.000   0.000   0.000  1.00 20.00           C\n"
            "END\n"
        )
        with _tmpdir() as tmp:
            runner = PipelineRunner(output_root=tmp, mmseqs=None, proteinmpnn=None, soluprot=None, af2=None)
            req = PipelineRequest(
                target_fasta="",
                target_pdb=pdb,
                dry_run=True,
                num_seq_per_tier=2,
                conservation_tiers=[0.3],
                design_chains=["A"],
                pdb_strip_nonpositive_resseq=True,
                pdb_renumber_resseq_from_1=True,
            )
            res = runner.run(req)
            out = Path(res.output_dir)
            self.assertTrue((out / "target.original.pdb").exists())
            self.assertTrue((out / "pdb_numbering.json").exists())

            target_fasta = (out / "target.fasta").read_text(encoding="utf-8")
            self.assertIn("\nG\n", target_fasta)

            processed_pdb = (out / "target.pdb").read_text(encoding="utf-8")
            self.assertNotIn("  -1", processed_pdb)

    def test_pipeline_rfd3_auto_strips_nonpositive_resseq(self) -> None:
        pdb = (
            "ATOM      1  CA  ALA A  -1       0.000   0.000   0.000  1.00 20.00           C\n"
            "ATOM      2  CA  GLY A   1       1.000   0.000   0.000  1.00 20.00           C\n"
            "END\n"
        )
        with _tmpdir() as tmp:
            runner = PipelineRunner(output_root=tmp, mmseqs=None, proteinmpnn=None, soluprot=None, af2=None)
            req = PipelineRequest(
                target_fasta="",
                target_pdb="",
                rfd3_input_pdb=pdb,
                rfd3_contig="A1-2",
                dry_run=True,
                num_seq_per_tier=2,
                conservation_tiers=[0.3],
            )
            res = runner.run(req)
            out = Path(res.output_dir)
            input_pdb = (out / "rfd3" / "input_files" / "input.pdb").read_text(encoding="utf-8")
            selected_pdb = (out / "rfd3" / "selected.pdb").read_text(encoding="utf-8")
            self.assertNotIn("  -1", input_pdb)
            self.assertNotIn("  -1", selected_pdb)

    def test_pipeline_dry_run_accepts_conservation_weighting_flag(self) -> None:
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
            req = PipelineRequest(
                target_fasta=fasta,
                target_pdb=pdb,
                dry_run=True,
                conservation_weighting="mmseqs_cluster",
                num_seq_per_tier=2,
                conservation_tiers=[0.3],
            )
            res = runner.run(req)
            out = Path(res.output_dir)
            self.assertTrue((out / "conservation.json").exists())

    def test_pipeline_dry_run_rfd3_writes_selected_pdb(self) -> None:
        pdb = (
            "ATOM      1  CA  ALA A   1       0.000   0.000   0.000  1.00 20.00           C\n"
            "ATOM      2  CA  GLY A   2       1.000   0.000   0.000  1.00 20.00           C\n"
            "END\n"
        )
        with _tmpdir() as tmp:
            runner = PipelineRunner(output_root=tmp, mmseqs=None, proteinmpnn=None, soluprot=None, af2=None, rfd3=None)
            req = PipelineRequest(
                target_fasta="",
                target_pdb="",
                dry_run=True,
                rfd3_contig="A1-2",
                rfd3_input_pdb=pdb,
                num_seq_per_tier=1,
                conservation_tiers=[0.3],
            )
            res = runner.run(req)
            out = Path(res.output_dir)
            self.assertTrue((out / "rfd3" / "selected.pdb").exists())
            self.assertTrue((out / "target.pdb").exists())

    def test_pipeline_rfd3_simple_inputs_written(self) -> None:
        pdb = (
            "ATOM      1  CA  ALA A   1       0.000   0.000   0.000  1.00 20.00           C\n"
            "ATOM      2  CA  GLY A   2       1.000   0.000   0.000  1.00 20.00           C\n"
            "END\n"
        )
        with _tmpdir() as tmp:
            runner = PipelineRunner(output_root=tmp, mmseqs=None, proteinmpnn=None, soluprot=None, af2=None, rfd3=None)
            req = PipelineRequest(
                target_fasta="",
                target_pdb="",
                dry_run=True,
                rfd3_contig="A1-2",
                rfd3_ligand="LIG",
                rfd3_select_unfixed_sequence="A1-2",
                rfd3_input_pdb=pdb,
                num_seq_per_tier=1,
                conservation_tiers=[0.3],
            )
            res = runner.run(req)
            out = Path(res.output_dir)
            inputs = json.loads((out / "rfd3" / "inputs.json").read_text(encoding="utf-8"))
            spec = inputs.get("spec-1") or {}
            self.assertEqual(spec.get("input"), "input.pdb")
            self.assertEqual(spec.get("contig"), "A1-2")
            self.assertEqual(spec.get("ligand"), "LIG")
            self.assertEqual(spec.get("select_unfixed_sequence"), "A1-2")

    def test_pipeline_rfd3_partial_t_default_injected(self) -> None:
        pdb = (
            "ATOM      1  CA  ALA A   1       0.000   0.000   0.000  1.00 20.00           C\n"
            "ATOM      2  CA  GLY A   2       1.000   0.000   0.000  1.00 20.00           C\n"
            "END\n"
        )
        with _tmpdir() as tmp:
            runner = PipelineRunner(output_root=tmp, mmseqs=None, proteinmpnn=None, soluprot=None, af2=None, rfd3=None)
            req = PipelineRequest(
                target_fasta="",
                target_pdb="",
                dry_run=True,
                rfd3_contig="A1-2",
                rfd3_input_pdb=pdb,
                num_seq_per_tier=1,
                conservation_tiers=[0.3],
            )
            res = runner.run(req)
            out = Path(res.output_dir)
            inputs = json.loads((out / "rfd3" / "inputs.json").read_text(encoding="utf-8"))
            spec = inputs.get("spec-1") or {}
            self.assertEqual(spec.get("partial_t"), 20.0)

    def test_pipeline_rfd3_partial_t_respects_override(self) -> None:
        pdb = (
            "ATOM      1  CA  ALA A   1       0.000   0.000   0.000  1.00 20.00           C\n"
            "ATOM      2  CA  GLY A   2       1.000   0.000   0.000  1.00 20.00           C\n"
            "END\n"
        )
        with _tmpdir() as tmp:
            runner = PipelineRunner(output_root=tmp, mmseqs=None, proteinmpnn=None, soluprot=None, af2=None, rfd3=None)
            req = PipelineRequest(
                target_fasta="",
                target_pdb="",
                dry_run=True,
                rfd3_inputs={"spec-1": {"input": "input.pdb", "contig": "A1-2", "partial_t": 5}},
                rfd3_input_pdb=pdb,
                num_seq_per_tier=1,
                conservation_tiers=[0.3],
            )
            res = runner.run(req)
            out = Path(res.output_dir)
            inputs = json.loads((out / "rfd3" / "inputs.json").read_text(encoding="utf-8"))
            spec = inputs.get("spec-1") or {}
            self.assertEqual(spec.get("partial_t"), 5)

    def test_pipeline_rfd3_reuses_cached_selected_on_rerun(self) -> None:
        pdb = (
            "ATOM      1  CA  ALA A   1       0.000   0.000   0.000  1.00 20.00           C\n"
            "ATOM      2  CA  GLY A   2       1.000   0.000   0.000  1.00 20.00           C\n"
            "END\n"
        )

        class _MMseqsStub:
            def search(self, query_fasta, **kwargs):  # type: ignore[no-untyped-def]
                _ = kwargs
                _ = query_fasta
                a3m = ">query\nAG\n>hit1\nAG\n"
                a3m_b64 = base64.b64encode(gzip.compress(a3m.encode("utf-8"))).decode("ascii")
                return {"tsv": "", "a3m_gz_b64": a3m_b64}

        class _RFD3Stub:
            def __init__(self, selected_pdb: str) -> None:
                self.selected_pdb = selected_pdb
                self.calls = 0

            def design(self, **kwargs):  # type: ignore[no-untyped-def]
                self.calls += 1
                on_job_id = kwargs.get("on_job_id")
                if callable(on_job_id):
                    on_job_id(f"rfd3_job_{self.calls}")
                return {
                    "selected": {
                        "id": "inputs_spec-1_0_model_0",
                        "pdb": self.selected_pdb,
                        "cif_gz_name": "inputs_spec-1_0_model_0.cif.gz",
                        "json_name": "inputs_spec-1_0_model_0.json",
                    },
                    "designs": [
                        {
                            "id": "inputs_spec-1_0_model_0",
                            "pdb": self.selected_pdb,
                            "cif_gz_name": "inputs_spec-1_0_model_0.cif.gz",
                            "json_name": "inputs_spec-1_0_model_0.json",
                        }
                    ],
                }

        with _tmpdir() as tmp:
            rfd3 = _RFD3Stub(pdb)
            runner = PipelineRunner(
                output_root=tmp,
                mmseqs=_MMseqsStub(),
                proteinmpnn=None,
                soluprot=None,
                af2=None,
                rfd3=rfd3,
            )
            req = PipelineRequest(
                target_fasta=">q1\nAG\n",
                target_pdb=pdb,
                dry_run=False,
                stop_after="rfd3",
                rfd3_input_pdb=pdb,
                rfd3_contig="A1-2",
                conservation_tiers=[0.3],
                num_seq_per_tier=1,
            )

            run_id = "resume_rfd3_cache"
            runner.run(req, run_id=run_id)
            run_root = Path(tmp) / run_id
            selected_meta = json.loads((run_root / "rfd3" / "selected.json").read_text(encoding="utf-8"))
            self.assertEqual(selected_meta.get("id"), "rfd3_spec-1_0_model_0")
            self.assertEqual(selected_meta.get("upstream_id"), "inputs_spec-1_0_model_0")
            self.assertEqual(selected_meta.get("json_name"), "rfd3_spec-1_0_model_0.json")
            designs_meta = json.loads((run_root / "rfd3" / "designs.json").read_text(encoding="utf-8"))
            self.assertEqual(designs_meta[0].get("id"), "rfd3_spec-1_0_model_0")
            self.assertTrue((run_root / "rfd3" / "designs" / "rfd3_spec-1_0_model_0.pdb").exists())
            runpod_job_path = run_root / "rfd3" / "runpod_job.json"
            runpod_meta = json.loads(runpod_job_path.read_text(encoding="utf-8"))
            runpod_meta["job_id"] = "cancelled_job"
            runpod_job_path.write_text(json.dumps(runpod_meta), encoding="utf-8")

            runner.run(req, run_id=run_id)

            self.assertEqual(rfd3.calls, 1)
            events = [
                json.loads(line)
                for line in (run_root / "events.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            rfd3_completed = [e for e in events if e.get("stage") == "rfd3" and e.get("state") == "completed"]
            self.assertTrue(rfd3_completed)
            self.assertEqual(rfd3_completed[-1].get("detail"), "cached")

    def test_pipeline_bioemu_reuses_cached_outputs_on_rerun(self) -> None:
        pdb = (
            "ATOM      1  CA  ALA A   1       0.000   0.000   0.000  1.00 20.00           C\n"
            "ATOM      2  CA  GLY A   2       1.000   0.000   0.000  1.00 20.00           C\n"
            "END\n"
        )

        class _MMseqsStub:
            def search(self, query_fasta, **kwargs):  # type: ignore[no-untyped-def]
                _ = kwargs
                _ = query_fasta
                a3m = ">query\nAG\n>hit1\nAG\n"
                a3m_b64 = base64.b64encode(gzip.compress(a3m.encode("utf-8"))).decode("ascii")
                return {"tsv": "", "a3m_gz_b64": a3m_b64}

        class _BioEmuStub:
            def __init__(self, sample_pdb: str) -> None:
                self.sample_pdb = sample_pdb
                self.calls = 0

            def sample(self, **kwargs):  # type: ignore[no-untyped-def]
                self.calls += 1
                on_job_id = kwargs.get("on_job_id")
                if callable(on_job_id):
                    on_job_id(f"bioemu_job_{self.calls}")
                return {
                    "sample_pdbs": [{"id": "bioemu_topology", "pdb": self.sample_pdb, "frame_index": 0}],
                    "topology_pdb": self.sample_pdb,
                }

        with _tmpdir() as tmp:
            bioemu = _BioEmuStub(pdb)
            runner = PipelineRunner(
                output_root=tmp,
                mmseqs=_MMseqsStub(),
                proteinmpnn=None,
                soluprot=None,
                af2=None,
                bioemu=bioemu,
            )
            req = PipelineRequest(
                target_fasta=">q1\nAG\n",
                target_pdb=pdb,
                dry_run=False,
                stop_after="bioemu",
                bioemu_use=True,
                bioemu_num_samples=2,
                bioemu_max_return_structures=1,
                conservation_tiers=[0.3],
                num_seq_per_tier=1,
            )

            run_id = "resume_bioemu_cache"
            runner.run(req, run_id=run_id)
            run_root = Path(tmp) / run_id
            runpod_job_path = run_root / "bioemu" / "runpod_job.json"
            runpod_meta = json.loads(runpod_job_path.read_text(encoding="utf-8"))
            runpod_meta["job_id"] = "cancelled_job"
            runpod_job_path.write_text(json.dumps(runpod_meta), encoding="utf-8")

            runner.run(req, run_id=run_id)

            self.assertEqual(bioemu.calls, 1)
            events = [
                json.loads(line)
                for line in (run_root / "events.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            bioemu_completed = [e for e in events if e.get("stage") == "bioemu" and e.get("state") == "completed"]
            self.assertTrue(bioemu_completed)
            self.assertIn("cached", str(bioemu_completed[-1].get("detail") or ""))

    def test_pipeline_bioemu_processed_stage_pdb_is_synced_for_compare(self) -> None:
        target_pdb = (
            "ATOM      1  CA  ALA A   1       0.000   0.000   0.000  1.00 20.00           C\n"
            "ATOM      2  CA  GLY A   2       1.000   0.000   0.000  1.00 20.00           C\n"
            "END\n"
        )
        bioemu_pdb = (
            "ATOM      1  CA  ALA A   0       0.000   0.000   0.000  1.00 20.00           C\n"
            "ATOM      2  CA  GLY A   1       1.000   0.000   0.000  1.00 20.00           C\n"
            "END\n"
        )

        class _MMseqsStub:
            def search(self, query_fasta, **kwargs):  # type: ignore[no-untyped-def]
                _ = kwargs
                _ = query_fasta
                a3m = ">query\nAG\n>hit1\nAG\n"
                a3m_b64 = base64.b64encode(gzip.compress(a3m.encode("utf-8"))).decode("ascii")
                return {"tsv": "", "a3m_gz_b64": a3m_b64}

        class _BioEmuStub:
            def sample(self, **kwargs):  # type: ignore[no-untyped-def]
                on_job_id = kwargs.get("on_job_id")
                if callable(on_job_id):
                    on_job_id("bioemu_job_sync")
                return {"topology_pdb": bioemu_pdb}

        with _tmpdir() as tmp:
            runner = PipelineRunner(
                output_root=tmp,
                mmseqs=_MMseqsStub(),
                proteinmpnn=None,
                soluprot=None,
                af2=None,
                bioemu=_BioEmuStub(),
            )
            req = PipelineRequest(
                target_fasta=">q1\nAG\n",
                target_pdb=target_pdb,
                dry_run=False,
                bioemu_use=True,
                bioemu_sequence="AG",
                stop_after="design",
                num_seq_per_tier=1,
                conservation_tiers=[0.3],
                pdb_strip_nonpositive_resseq=True,
                pdb_renumber_resseq_from_1=False,
            )
            res = runner.run(req)
            out = Path(res.output_dir)
            stage_pdb = (out / "bioemu" / "designs" / "bioemu_topology.pdb").read_text(encoding="utf-8")
            self.assertIn("ALA A   1", stage_pdb)
            self.assertNotIn("ALA A   0", stage_pdb)
            output_payload = json.loads((out / "bioemu" / "output.json").read_text(encoding="utf-8"))
            self.assertIn("ALA A   1", str(output_payload.get("topology_pdb") or ""))
            self.assertNotIn("ALA A   0", str(output_payload.get("topology_pdb") or ""))

    def test_pipeline_wt_diff_reuses_cached_outputs_on_rerun(self) -> None:
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

        class _MMseqsStub:
            def __init__(self) -> None:
                self.novelty_calls = 0

            def search(self, query_fasta, **kwargs):  # type: ignore[no-untyped-def]
                _ = query_fasta
                if bool(kwargs.get("return_a3m")):
                    a3m = ">query\nACDEFGHIK\n>hit1\nACDEFGHIK\n"
                    a3m_b64 = base64.b64encode(gzip.compress(a3m.encode("utf-8"))).decode("ascii")
                    return {"tsv": "", "a3m_gz_b64": a3m_b64}
                self.novelty_calls += 1
                return {"tsv": "q1\thit1\t99.0\n"}

        with _tmpdir() as tmp:
            mmseqs = _MMseqsStub()
            runner = PipelineRunner(output_root=tmp, mmseqs=mmseqs, proteinmpnn=None, soluprot=None, af2=None)
            req = PipelineRequest(
                target_fasta=fasta,
                target_pdb=pdb,
                dry_run=True,
                novelty_enabled=True,
                conservation_tiers=[0.3],
                num_seq_per_tier=2,
                soluprot_cutoff=0.0,
                af2_plddt_cutoff=0.0,
                af2_rmsd_cutoff=0.0,
            )

            run_id = "resume_novelty_cache"
            runner.run(req, run_id=run_id)
            runner.run(req, run_id=run_id)

            self.assertEqual(mmseqs.novelty_calls, 0)
            run_root = Path(tmp) / run_id
            events = [
                json.loads(line)
                for line in (run_root / "events.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            novelty_completed = [e for e in events if e.get("stage") == "novelty_30" and e.get("state") == "completed"]
            self.assertTrue(novelty_completed)
            self.assertEqual(novelty_completed[-1].get("detail"), "cached")

    def test_pipeline_dry_run_merges_rfd3_and_bioemu_backbones(self) -> None:
        pdb = (
            "ATOM      1  CA  ALA A   1       0.000   0.000   0.000  1.00 20.00           C\n"
            "ATOM      2  CA  GLY A   2       1.000   0.000   0.000  1.00 20.00           C\n"
            "END\n"
        )
        with _tmpdir() as tmp:
            runner = PipelineRunner(output_root=tmp, mmseqs=None, proteinmpnn=None, soluprot=None, af2=None, rfd3=None)
            req = PipelineRequest(
                target_fasta="",
                target_pdb="",
                dry_run=True,
                rfd3_contig="A1-2",
                rfd3_input_pdb=pdb,
                rfd3_use_ensemble=True,
                rfd3_max_return_designs=2,
                bioemu_use=True,
                bioemu_num_samples=3,
                bioemu_max_return_structures=3,
                num_seq_per_tier=1,
                conservation_tiers=[0.3],
            )
            res = runner.run(req)
            out = Path(res.output_dir)
            payload = json.loads((out / "backbones.json").read_text(encoding="utf-8"))
            backbones = payload.get("backbones") or []
            sources = [str(item.get("source") or "") for item in backbones if isinstance(item, dict)]
            self.assertEqual(sources.count("rfd3"), 2)
            self.assertEqual(sources.count("bioemu"), 3)
            rfd3_ids = [str(item.get("id") or "") for item in backbones if isinstance(item, dict) and item.get("source") == "rfd3"]
            self.assertTrue(all(rid.startswith("rfd3_") for rid in rfd3_ids))
            self.assertFalse(any("inputs_spec" in rid for rid in rfd3_ids))

            source_summary = payload.get("sources") if isinstance(payload.get("sources"), dict) else {}
            rfd3_summary = source_summary.get("rfd3") if isinstance(source_summary.get("rfd3"), dict) else {}
            bioemu_summary = source_summary.get("bioemu") if isinstance(source_summary.get("bioemu"), dict) else {}
            self.assertEqual(rfd3_summary.get("requested_count"), 2)
            self.assertEqual(rfd3_summary.get("observed_count"), 2)
            self.assertEqual(rfd3_summary.get("materialized_count"), 2)
            self.assertEqual(rfd3_summary.get("propagated_count"), 2)
            self.assertEqual(rfd3_summary.get("propagation_mode"), "all_materialized")
            self.assertEqual(rfd3_summary.get("selected_backbone_id"), rfd3_ids[0])
            self.assertEqual(bioemu_summary.get("requested_count"), 3)
            self.assertEqual(bioemu_summary.get("observed_count"), 3)
            self.assertEqual(bioemu_summary.get("materialized_count"), 3)
            self.assertEqual(bioemu_summary.get("propagated_count"), 3)
            self.assertEqual(bioemu_summary.get("propagation_mode"), "all_materialized")
            self.assertEqual(payload.get("propagation_mode"), "all_materialized")

            primary = backbones[0] if isinstance(backbones[0], dict) else {}
            self.assertTrue(primary.get("primary"))
            self.assertTrue(primary.get("selected"))
            self.assertTrue(primary.get("propagated"))
            self.assertTrue(primary.get("materialized"))
            self.assertEqual(primary.get("origin_stage"), "rfd3")

            first_bioemu = next(item for item in backbones if isinstance(item, dict) and item.get("source") == "bioemu")
            self.assertTrue(first_bioemu.get("propagated"))
            self.assertTrue(first_bioemu.get("materialized"))
            self.assertEqual(first_bioemu.get("origin_stage"), "bioemu")
            self.assertIsInstance(first_bioemu.get("frame_index"), int)

            tier_payload = json.loads(
                (out / "tiers" / "30" / "proteinmpnn_backbones.json").read_text(encoding="utf-8")
            )
            tier_backbones = tier_payload.get("backbones") if isinstance(tier_payload.get("backbones"), list) else []
            self.assertEqual(len(tier_backbones), 5)
            self.assertTrue(all(isinstance(item, dict) and item.get("propagated") for item in tier_backbones))
            self.assertTrue(all(isinstance(item, dict) and item.get("source") in {"rfd3", "bioemu"} for item in tier_backbones))
            self.assertTrue(
                all(
                    isinstance(item, dict)
                    and isinstance(item.get("sequence_count"), int)
                    and int(item.get("sequence_count") or 0) >= 1
                    for item in tier_backbones
                )
            )

    def test_pipeline_includes_fixed_positions_extra(self) -> None:
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
            req = PipelineRequest(
                target_fasta=fasta,
                target_pdb=pdb,
                dry_run=True,
                num_seq_per_tier=2,
                conservation_tiers=[0.3],
                fixed_positions_extra={"A": [9]},
            )
            res = runner.run(req)
            out = Path(res.output_dir)
            fixed = json.loads((out / "tiers" / "30" / "fixed_positions.json").read_text(encoding="utf-8"))
            self.assertIn(9, fixed.get("A", []))

    def test_pipeline_projects_original_ligand_mask_to_rfd3_backbone(self) -> None:
        target_pdb_with_ligand = (
            "ATOM      1  CA  ALA A   1       0.000   0.000   0.000  1.00 20.00           C\n"
            "ATOM      2  CA  CYS A   2       2.000   0.000   0.000  1.00 20.00           C\n"
            "ATOM      3  CA  ASP A   3       4.000   0.000   0.000  1.00 20.00           C\n"
            "HETATM    4  C1  LIG Z   1       2.200   0.000   0.000  1.00 20.00           C\n"
            "END\n"
        )
        rfd3_input_pdb = (
            "ATOM      1  CA  ALA A   1       0.000   1.000   0.000  1.00 20.00           C\n"
            "ATOM      2  CA  CYS A   2       2.000   1.000   0.000  1.00 20.00           C\n"
            "ATOM      3  CA  ASP A   3       4.000   1.000   0.000  1.00 20.00           C\n"
            "END\n"
        )
        with _tmpdir() as tmp:
            runner = PipelineRunner(output_root=tmp, mmseqs=None, proteinmpnn=None, soluprot=None, af2=None, rfd3=None)
            req = PipelineRequest(
                target_fasta=">q1\nACD\n",
                target_pdb=target_pdb_with_ligand,
                rfd3_input_pdb=rfd3_input_pdb,
                rfd3_contig="A1-3",
                ligand_mask_use_original_target=True,
                dry_run=True,
                num_seq_per_tier=1,
                conservation_tiers=[0.3],
            )
            res = runner.run(req)
            out = Path(res.output_dir)
            projected = json.loads((out / "ligand_mask_original_target.json").read_text(encoding="utf-8"))
            query_by_chain = projected.get("query_positions_by_chain") or {}
            projected_positions = query_by_chain.get("A") or []
            self.assertTrue(projected_positions)

            fixed = json.loads((out / "tiers" / "30" / "fixed_positions.json").read_text(encoding="utf-8"))
            fixed_a = set(fixed.get("A") or [])
            self.assertTrue(set(int(p) for p in projected_positions).issubset(fixed_a))

    def test_pipeline_requires_fixed_positions_extra_for_sequence_only(self) -> None:
        fasta = ">q1\nACDEFGHIK\n"
        with _tmpdir() as tmp:
            runner = PipelineRunner(output_root=tmp, mmseqs=None, proteinmpnn=None, soluprot=None, af2=None)
            req = PipelineRequest(
                target_fasta=fasta,
                target_pdb="",
                dry_run=False,
                conservation_tiers=[0.3],
            )
            run_id = "sequence_only_requires_fixed_positions_extra"
            with self.assertRaises(Exception) as ctx:
                runner.run(req, run_id=run_id)
            self.assertIn("fixed_positions_extra", str(ctx.exception))
            status = json.loads((Path(tmp) / run_id / "status.json").read_text(encoding="utf-8"))
            self.assertEqual(status.get("stage"), "needs_fixed_positions_extra")
            self.assertEqual(status.get("state"), "failed")

    def test_pipeline_limits_af2_candidates_per_tier_by_soluprot_rank(self) -> None:
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
            req = PipelineRequest(
                target_fasta=fasta,
                target_pdb=pdb,
                dry_run=True,
                num_seq_per_tier=6,
                conservation_tiers=[0.3],
                soluprot_cutoff=0.0,
                af2_max_candidates_per_tier=1,
            )
            res = runner.run(req)
            out = Path(res.output_dir)
            af2_scores = json.loads((out / "tiers" / "30" / "af2_scores.json").read_text(encoding="utf-8"))
            candidate_ids = af2_scores.get("candidate_ids") or []
            self.assertEqual(len(candidate_ids), 1)
            self.assertTrue(bool(af2_scores.get("candidate_budget_applied")))
            self.assertEqual(int(af2_scores.get("max_candidates_per_tier") or 0), 1)
            self.assertGreater(int(af2_scores.get("candidate_count_before_budget") or 0), 1)

    def test_chain_strategy_forces_single_chain_in_monomer_mode(self) -> None:
        fasta = ">q1\nACD\n"
        pdb = (
            "ATOM      1  CA  ALA A   1       0.000   0.000   0.000  1.00 20.00           C\n"
            "ATOM      2  CA  CYS A   2       1.000   0.000   0.000  1.00 20.00           C\n"
            "ATOM      3  CA  ASP A   3       2.000   0.000   0.000  1.00 20.00           C\n"
            "ATOM      4  CA  GLU B   1       0.000   1.000   0.000  1.00 20.00           C\n"
            "ATOM      5  CA  PHE B   2       1.000   1.000   0.000  1.00 20.00           C\n"
            "ATOM      6  CA  GLY B   3       2.000   1.000   0.000  1.00 20.00           C\n"
            "END\n"
        )

        with _tmpdir() as tmp:
            runner = PipelineRunner(output_root=tmp, mmseqs=None, proteinmpnn=None, soluprot=None, af2=None)
            req = PipelineRequest(
                target_fasta=fasta,
                target_pdb=pdb,
                design_chains=["A", "B"],
                af2_model_preset="monomer",
                dry_run=True,
                num_seq_per_tier=2,
                conservation_tiers=[0.3],
            )
            res = runner.run(req)
            out = Path(res.output_dir)
            payload = json.loads((out / "tiers" / "30" / "proteinmpnn.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["request"]["pdb_path_chains"], ["A"])

    def test_pipeline_rejects_unsafe_partial_rerun_when_design_inputs_change(self) -> None:
        with _tmpdir() as tmp:
            runner = PipelineRunner(output_root=tmp, mmseqs=None, proteinmpnn=None, soluprot=None, af2=None)
            run_id = "partial_rerun_guard"
            initial = PipelineRequest(
                target_fasta=">q1\nACDEFGHIK\n",
                target_pdb="",
                dry_run=True,
                stop_after="af2",
                conservation_tiers=[0.3],
            )
            runner.run(initial, run_id=run_id)

            rerun = PipelineRequest(
                target_fasta=">q1\nYYYYYYYYY\n",
                target_pdb="",
                dry_run=True,
                start_from="af2",
                stop_after="af2",
                conservation_tiers=[0.3],
            )
            with self.assertRaises(PipelineInputRequired) as ctx:
                runner.run(rerun, run_id=run_id)
            self.assertIn("target_fasta", str(ctx.exception))
            self.assertIn("start_from='design'", str(ctx.exception))

    def test_pipeline_design_boundary_rerun_refreshes_design_and_msa_fingerprints(self) -> None:
        with _tmpdir() as tmp:
            runner = PipelineRunner(output_root=tmp, mmseqs=None, proteinmpnn=None, soluprot=None, af2=None)
            run_id = "partial_rerun_design"
            initial = PipelineRequest(
                target_fasta=">q1\nACDEFGHIK\n",
                target_pdb="",
                dry_run=True,
                stop_after="design",
                conservation_tiers=[0.3],
            )
            runner.run(initial, run_id=run_id)

            rerun = PipelineRequest(
                target_fasta=">q1\nYYYYYYYYY\n",
                target_pdb="",
                dry_run=True,
                start_from="design",
                stop_after="design",
                conservation_tiers=[0.3],
            )
            res = runner.run(rerun, run_id=run_id)
            out = Path(res.output_dir)

            designs_fasta = (out / "tiers" / "30" / "designs.fasta").read_text(encoding="utf-8")
            self.assertIn("YYYYYYYYY", designs_fasta)
            self.assertNotIn("ACDEFGHIK", designs_fasta)

            msa_meta = json.loads((out / "msa" / "request_meta.json").read_text(encoding="utf-8"))
            self.assertTrue(str(msa_meta.get("request_hash") or "").strip())

            proteinmpnn_payload = json.loads((out / "tiers" / "30" / "proteinmpnn.json").read_text(encoding="utf-8"))
            self.assertTrue(str(proteinmpnn_payload.get("request_hash") or "").strip())
            self.assertTrue(str(proteinmpnn_payload.get("input_hash") or "").strip())

    def test_pipeline_af2_partial_rerun_allows_af2_only_changes(self) -> None:
        with _tmpdir() as tmp:
            runner = PipelineRunner(output_root=tmp, mmseqs=None, proteinmpnn=None, soluprot=None, af2=None)
            run_id = "partial_rerun_af2"
            initial = PipelineRequest(
                target_fasta=">q1\nACDEFGHIK\n",
                target_pdb="",
                dry_run=True,
                stop_after="af2",
                conservation_tiers=[0.3],
                af2_plddt_cutoff=85.0,
            )
            runner.run(initial, run_id=run_id)

            rerun = PipelineRequest(
                target_fasta=">q1\nACDEFGHIK\n",
                target_pdb="",
                dry_run=True,
                start_from="af2",
                stop_after="af2",
                conservation_tiers=[0.3],
                af2_plddt_cutoff=70.0,
            )
            res = runner.run(rerun, run_id=run_id)
            request_payload = json.loads((Path(res.output_dir) / "request.json").read_text(encoding="utf-8"))
            self.assertEqual(float(request_payload.get("af2_plddt_cutoff") or 0.0), 70.0)

    def test_pipeline_selected_tiers_limits_outputs_to_requested_tier(self) -> None:
        with _tmpdir() as tmp:
            runner = PipelineRunner(output_root=tmp, mmseqs=None, proteinmpnn=None, soluprot=None, af2=None)
            req = PipelineRequest(
                target_fasta=">q1\nACDEFGHIK\n",
                target_pdb="",
                dry_run=True,
                stop_after="af2",
                conservation_tiers=[0.3, 0.5, 0.7],
                selected_tiers=[0.5],
            )
            res = runner.run(req)
            out = Path(res.output_dir)

            self.assertFalse((out / "tiers" / "30").exists())
            self.assertTrue((out / "tiers" / "50" / "af2_scores.json").exists())
            self.assertFalse((out / "tiers" / "70").exists())

            request_payload = json.loads((out / "request.json").read_text(encoding="utf-8"))
            self.assertEqual(request_payload.get("selected_tiers"), [0.5])

    def test_pipeline_partial_rerun_scopes_cleanup_to_selected_tiers(self) -> None:
        with _tmpdir() as tmp:
            runner = PipelineRunner(output_root=tmp, mmseqs=None, proteinmpnn=None, soluprot=None, af2=None)
            run_id = "partial_rerun_selected_tier"
            initial = PipelineRequest(
                target_fasta=">q1\nACDEFGHIK\n",
                target_pdb="",
                dry_run=True,
                stop_after="af2",
                conservation_tiers=[0.3, 0.5],
            )
            res = runner.run(initial, run_id=run_id)
            out = Path(res.output_dir)

            tier30_novelty = out / "tiers" / "30" / "novelty.json"
            tier50_novelty = out / "tiers" / "50" / "novelty.json"
            tier30_novelty.write_text("keep", encoding="utf-8")
            tier50_novelty.write_text("drop", encoding="utf-8")

            rerun = PipelineRequest(
                target_fasta=">q1\nACDEFGHIK\n",
                target_pdb="",
                dry_run=True,
                start_from="af2",
                stop_after="af2",
                conservation_tiers=[0.3, 0.5],
                selected_tiers=[0.5],
            )
            runner.run(rerun, run_id=run_id)

            self.assertTrue(tier30_novelty.exists())
            self.assertFalse(tier50_novelty.exists())

    def test_clear_stage_outputs_removes_korean_reports_and_wt(self) -> None:
        with _tmpdir() as tmp:
            root = Path(tmp) / "cleanup_case"
            root.mkdir(parents=True, exist_ok=True)
            (root / "report_ko.md").write_text("ko", encoding="utf-8")
            (root / "agent_panel_report_ko.md").write_text("agent-ko", encoding="utf-8")
            (root / "wt").mkdir(parents=True, exist_ok=True)
            removed = _clear_stage_outputs_from(root, start_from="af2")
            self.assertFalse((root / "report_ko.md").exists())
            self.assertFalse((root / "agent_panel_report_ko.md").exists())
            self.assertFalse((root / "wt").exists())
            self.assertIn("report_ko.md", removed)
            self.assertIn("agent_panel_report_ko.md", removed)
            self.assertIn("wt", removed)


if __name__ == "__main__":
    unittest.main()
