"""Cancellation must stop new worker submissions in the middle of a stage.

The stage-level check only runs at stage boundaries. A stage that submits one
job per candidate used to keep feeding the workers for the whole loop after the
run had already been cancelled, so `pipeline.cancel_run` cancelled the jobs that
were in flight at that instant and the loop promptly submitted more.
"""

import base64
import gzip
import unittest
import uuid
from contextlib import contextmanager
from pathlib import Path

from pipeline_mcp.models import PipelineRequest
from pipeline_mcp.models import SequenceRecord
from pipeline_mcp.pipeline import PipelineCancelled
from pipeline_mcp.pipeline import PipelineRunner
from pipeline_mcp.storage import mark_cancel_requested


@contextmanager
def _tmpdir():
    base = Path(__file__).resolve().parent / "_tmp"
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"run_{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    yield str(path)


def _simple_ca_backbone(offset: float) -> str:
    return (
        f"ATOM      1  CA  ALA A   1      {offset:8.3f}{0.000:8.3f}{0.000:8.3f}  1.00 20.00           C\n"
        f"ATOM      2  CA  GLY A   2      {offset + 1.000:8.3f}{0.000:8.3f}{0.000:8.3f}  1.00 20.00           C\n"
        f"ATOM      3  CA  SER A   3      {offset + 2.000:8.3f}{0.000:8.3f}{0.000:8.3f}  1.00 20.00           C\n"
        "END\n"
    )


class _MMseqsStub:
    def search(self, query_fasta, **kwargs):  # type: ignore[no-untyped-def]
        _ = query_fasta
        _ = kwargs
        a3m = ">query\nAG\n>hit1\nAG\n"
        a3m_b64 = base64.b64encode(gzip.compress(a3m.encode("utf-8"))).decode("ascii")
        return {"tsv": "", "a3m_gz_b64": a3m_b64}


class _RFD3Stub:
    def design(self, **kwargs):  # type: ignore[no-untyped-def]
        requested = int(kwargs.get("max_return_designs") or 0)
        designs = [
            {
                "id": f"design_{idx}",
                "pdb": _simple_ca_backbone(float(idx) * 5.0),
                "score": None,
                "source": "rfd3",
            }
            for idx in range(requested)
        ]
        return {"selected": designs[0], "designs": designs}


def _pdb_9mer() -> str:
    lines = []
    residues = ["ALA", "CYS", "ASP", "GLU", "PHE", "GLY", "HIS", "ILE", "LYS"]
    for idx, resname in enumerate(residues, start=1):
        lines.append(
            f"ATOM  {idx:5d}  CA  {resname} A{idx:4d}    "
            f"{float(idx - 1):8.3f}{0.0:8.3f}{0.0:8.3f}  1.00 20.00           C"
        )
    lines.append("END")
    return "\n".join(lines) + "\n"


class _MMseqs9merStub:
    def search(self, **kwargs):  # type: ignore[no-untyped-def]
        _ = kwargs
        fasta = ">query\nACDEFGHIK\n>hit1\nACDEFGHIK\n>hit2\nACDEFGHIA\n"
        return {
            "tsv": "",
            "a3m_gz_b64": base64.b64encode(gzip.compress(fasta.encode())).decode(),
        }


class _ProteinMPNN9merStub:
    def design(self, **kwargs):  # type: ignore[no-untyped-def]
        count = int(kwargs.get("num_seq_per_target") or 0)
        query = "ACDEFGHIK"
        native = SequenceRecord(id="native", header="native", sequence=query)
        samples = [
            SequenceRecord(
                id=f"s{i + 1}",
                header=f"sample={i + 1}",
                sequence=query[:-1] + query[i % 9],
            )
            for i in range(count)
        ]
        return native, samples, {}


class _CancellingAf2Stub:
    """Requests cancellation from inside its first fold, like a user hitting stop."""

    def __init__(self, output_root: str, run_id: str, cancel_on_call: int) -> None:
        self.output_root = output_root
        self.run_id = run_id
        self.cancel_on_call = cancel_on_call
        self.calls = 0

    def predict(self, batch_inputs, **kwargs):  # type: ignore[no-untyped-def]
        _ = kwargs
        self.calls += 1
        if self.calls == self.cancel_on_call:
            mark_cancel_requested(self.output_root, self.run_id, reason="test")
        return {
            rec.id: {
                "best_plddt": 70.0 + idx,
                "best_model": "fake",
                "ranking_debug": {},
                "ranked_0_pdb": "",
            }
            for idx, rec in enumerate(batch_inputs)
        }


class TestCancelStopsAf2Submissions(unittest.TestCase):
    """AF2 folds one candidate at a time; this is the loop the fix targets."""

    def _request(self) -> PipelineRequest:
        return PipelineRequest(
            target_fasta=">q1\nACDEFGHIK\n",
            target_pdb=_pdb_9mer(),
            dry_run=False,
            conservation_tiers=[0.3],
            num_seq_per_tier=8,
            soluprot_cutoff=0.0,
            rfd3_use=False,
            bioemu_use=False,
            af2_top_k=0,
        )

    def _runner(self, tmp: str, af2) -> PipelineRunner:  # type: ignore[no-untyped-def]
        return PipelineRunner(
            output_root=tmp,
            mmseqs=_MMseqs9merStub(),
            proteinmpnn=_ProteinMPNN9merStub(),
            soluprot=None,
            af2=af2,
        )

    def test_cancel_inside_the_candidate_loop_stops_the_remaining_candidates(
        self,
    ) -> None:
        # Call 1 folds the WT baseline; calls 2..9 are the eight tier candidates,
        # all inside one stage. Cancelling on call 2 must stop calls 3..9, which
        # the stage-boundary check alone cannot do.
        run_id = "cancel_af2_test"
        with _tmpdir() as tmp:
            af2 = _CancellingAf2Stub(tmp, run_id, cancel_on_call=2)
            with self.assertRaises(PipelineCancelled):
                self._runner(tmp, af2).run(self._request(), run_id=run_id)
            self.assertEqual(af2.calls, 2)

    def test_without_cancellation_every_candidate_is_folded(self) -> None:
        run_id = "cancel_af2_control"
        with _tmpdir() as tmp:
            af2 = _CancellingAf2Stub(tmp, run_id, cancel_on_call=999)
            self._runner(tmp, af2).run(self._request(), run_id=run_id)
            self.assertEqual(af2.calls, 9)


class _CancellingProteinMPNNStub:
    """Requests cancellation from inside its first call, like a user hitting stop."""

    def __init__(self, output_root: str, run_id: str, cancel_on_call: int) -> None:
        self.output_root = output_root
        self.run_id = run_id
        self.cancel_on_call = cancel_on_call
        self.calls = 0

    def design(self, **kwargs):  # type: ignore[no-untyped-def]
        self.calls += 1
        if self.calls == self.cancel_on_call:
            mark_cancel_requested(self.output_root, self.run_id, reason="test")
        count = int(kwargs.get("num_seq_per_target") or 0)
        native = SequenceRecord(id="native", header="native", sequence="AG")
        samples = [
            SequenceRecord(id=f"s{idx}", header=f"s{idx}", sequence="AG")
            for idx in range(count)
        ]
        return native, samples, {}


class TestCancelStopsMidStageSubmissions(unittest.TestCase):
    def _request(self) -> PipelineRequest:
        pdb = (
            "ATOM      1  CA  ALA A   1       0.000   0.000   0.000  1.00 20.00           C\n"
            "ATOM      2  CA  GLY A   2       1.000   0.000   0.000  1.00 20.00           C\n"
            "END\n"
        )
        return PipelineRequest(
            target_fasta=">q1\nAG\n",
            target_pdb=pdb,
            dry_run=False,
            rfd3_use=True,
            rfd3_max_return_designs=3,
            num_seq_per_tier=2,
            conservation_tiers=[0.3],
            stop_after="design",
        )

    def test_cancel_during_first_backbone_stops_the_remaining_ones(self) -> None:
        run_id = "cancel_midstage_test"
        with _tmpdir() as tmp:
            proteinmpnn = _CancellingProteinMPNNStub(tmp, run_id, cancel_on_call=1)
            runner = PipelineRunner(
                output_root=tmp,
                mmseqs=_MMseqsStub(),
                proteinmpnn=proteinmpnn,
                soluprot=None,
                af2=None,
                rfd3=_RFD3Stub(),
            )
            with self.assertRaises(PipelineCancelled):
                runner.run(self._request(), run_id=run_id)
            # Three backbones were available; only the first was ever submitted.
            self.assertEqual(proteinmpnn.calls, 1)

    def test_without_cancellation_every_backbone_is_submitted(self) -> None:
        run_id = "cancel_midstage_control"
        with _tmpdir() as tmp:
            # cancel_on_call is unreachable, so this is the uncancelled baseline.
            proteinmpnn = _CancellingProteinMPNNStub(tmp, run_id, cancel_on_call=99)
            runner = PipelineRunner(
                output_root=tmp,
                mmseqs=_MMseqsStub(),
                proteinmpnn=proteinmpnn,
                soluprot=None,
                af2=None,
                rfd3=_RFD3Stub(),
            )
            runner.run(self._request(), run_id=run_id)
            self.assertEqual(proteinmpnn.calls, 3)


if __name__ == "__main__":
    unittest.main()
