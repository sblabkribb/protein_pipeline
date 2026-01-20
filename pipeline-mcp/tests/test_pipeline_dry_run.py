import json
import unittest
import uuid
from contextlib import contextmanager
from pathlib import Path

from pipeline_mcp.models import PipelineRequest
from pipeline_mcp.pipeline import PipelineRunner


@contextmanager
def _tmpdir():
    base = Path(__file__).resolve().parent / "_tmp"
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"run_{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    yield str(path)


class TestPipelineDryRun(unittest.TestCase):
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

            self.assertEqual(len(res.tiers), 2)
            for tier_result in res.tiers:
                tier_dir = out / "tiers" / str(int(round(tier_result.tier * 100.0)))
                self.assertTrue((tier_dir / "fixed_positions.json").exists())
                self.assertTrue((tier_dir / "proteinmpnn.json").exists())
                self.assertTrue((tier_dir / "designs.fasta").exists())
                self.assertTrue((tier_dir / "fixed_positions_check.json").exists())
                self.assertTrue((tier_dir / "soluprot.json").exists())
                self.assertTrue((tier_dir / "designs_filtered.fasta").exists())
                self.assertTrue((tier_dir / "af2_scores.json").exists())
                self.assertTrue((tier_dir / "af2_selected.fasta").exists())

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


if __name__ == "__main__":
    unittest.main()
