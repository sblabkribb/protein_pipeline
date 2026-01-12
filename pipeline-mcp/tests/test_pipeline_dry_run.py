import tempfile
import unittest
from pathlib import Path

from pipeline_mcp.models import PipelineRequest
from pipeline_mcp.pipeline import PipelineRunner


class TestPipelineDryRun(unittest.TestCase):
    def test_pipeline_runs_and_writes_artifacts(self) -> None:
        fasta = ">q1\nACDEFGHIK\n"
        pdb = (
            "ATOM      1  CA  ALA A   1       0.000   0.000   0.000  1.00 20.00           C\n"
            "ATOM      2  CA  ALA A   2       1.000   0.000   0.000  1.00 20.00           C\n"
            "END\n"
        )

        with tempfile.TemporaryDirectory() as tmp:
            runner = PipelineRunner(output_root=tmp, mmseqs=None, proteinmpnn=None, soluprot=None, af2=None)
            req = PipelineRequest(target_fasta=fasta, target_pdb=pdb, dry_run=True, num_seq_per_tier=2, conservation_tiers=[0.3, 0.5])
            res = runner.run(req)

            out = Path(res.output_dir)
            self.assertTrue((out / "request.json").exists())
            self.assertTrue((out / "status.json").exists())
            self.assertTrue((out / "events.jsonl").exists())
            self.assertTrue((out / "msa" / "result.a3m").exists())
            self.assertTrue((out / "conservation.json").exists())
            self.assertTrue((out / "ligand_mask.json").exists())

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
        with tempfile.TemporaryDirectory() as tmp:
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
        with tempfile.TemporaryDirectory() as tmp:
            runner = PipelineRunner(output_root=tmp, mmseqs=None, proteinmpnn=None, soluprot=None, af2=None)
            req = PipelineRequest(target_fasta="", target_pdb=pdb, dry_run=True, num_seq_per_tier=2, conservation_tiers=[0.3])
            res = runner.run(req)
            out = Path(res.output_dir)
            self.assertTrue((out / "target.fasta").exists())
            self.assertTrue((out / "target.pdb").exists())
            self.assertTrue((out / "msa" / "result.a3m").exists())


if __name__ == "__main__":
    unittest.main()
