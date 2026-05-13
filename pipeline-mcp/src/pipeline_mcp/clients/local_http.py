from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from collections.abc import Callable
from pathlib import Path
import tempfile

import requests

from ..models import SequenceRecord


@dataclass(frozen=True)
class LocalHttpRunClient:
    base_url: str
    token: str | None = None
    timeout_s: float = 21600.0

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = requests.post(
            self.base_url.rstrip("/") + "/run",
            headers=self._headers(),
            json={"input": payload},
            timeout=float(self.timeout_s),
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise RuntimeError(f"Local HTTP model response invalid: {data!r}")
        if data.get("error"):
            raise RuntimeError(str(data.get("error")))
        status = str(data.get("status") or "COMPLETED").upper()
        if status and status not in {"COMPLETED", "SUCCESS", "OK"}:
            raise RuntimeError(f"Local HTTP model job not completed: {data}")
        output = data.get("output")
        if isinstance(output, dict):
            return output
        return data


@dataclass(frozen=True)
class LocalHTTPMMseqsClient:
    base_url: str
    token: str | None = None
    timeout_s: float = 21600.0

    def _client(self) -> LocalHttpRunClient:
        return LocalHttpRunClient(self.base_url, self.token, self.timeout_s)

    def wait_job(self, job_id: str) -> dict[str, Any]:
        return self._client().run({"task": "wait", "job_id": str(job_id or "").strip()})

    def search(self, *, query_fasta: str, target_db: str = "uniref90", threads: int = 4, use_gpu: bool = True, include_taxonomy: bool = False, return_a3m: bool = False, a3m_max_return_bytes: int = 5 * 1024 * 1024, a3m_format_mode: int = 0, max_seqs: int | None = None, on_job_id: Callable[[str], None] | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "task": "search",
            "query_fasta": query_fasta,
            "target_db": target_db,
            "threads": int(threads),
            "use_gpu": bool(use_gpu),
            "include_taxonomy": bool(include_taxonomy),
            "return_a3m": bool(return_a3m),
            "a3m_max_return_bytes": int(a3m_max_return_bytes),
            "a3m_format_mode": int(a3m_format_mode),
        }
        if max_seqs is not None:
            payload["max_seqs"] = int(max_seqs)
        output = self._client().run(payload)
        job_id = str(output.get("job_id") or "").strip()
        if job_id and on_job_id:
            on_job_id(job_id)
        return output

    def cluster(self, *, sequences_fasta: str, threads: int = 4, cluster_method: str = "linclust", min_seq_id: float | None = None, coverage: float | None = None, cov_mode: int | None = None, kmer_per_seq: int | None = None, return_representatives: bool = False, on_job_id: Callable[[str], None] | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "task": "cluster",
            "sequences_fasta": sequences_fasta,
            "threads": int(threads),
            "cluster_method": str(cluster_method or "linclust"),
            "return_representatives": bool(return_representatives),
        }
        for key, value in {
            "min_seq_id": min_seq_id,
            "coverage": coverage,
            "cov_mode": cov_mode,
            "kmer_per_seq": kmer_per_seq,
        }.items():
            if value is not None:
                payload[key] = value
        output = self._client().run(payload)
        job_id = str(output.get("job_id") or "").strip()
        if job_id and on_job_id:
            on_job_id(job_id)
        return output


@dataclass(frozen=True)
class LocalHTTPBioEmuClient:
    base_url: str
    token: str | None = None
    timeout_s: float = 21600.0

    def sample(self, **kwargs: Any) -> dict[str, Any]:
        return LocalHttpRunClient(self.base_url, self.token, self.timeout_s).run(dict(kwargs))


@dataclass(frozen=True)
class LocalHTTPRFD3Client:
    base_url: str
    token: str | None = None
    timeout_s: float = 21600.0

    def design(self, **kwargs: Any) -> dict[str, Any]:
        return LocalHttpRunClient(self.base_url, self.token, self.timeout_s).run(dict(kwargs))


@dataclass(frozen=True)
class LocalHTTPDiffDockClient:
    base_url: str
    token: str | None = None
    timeout_s: float = 21600.0

    def dock(self, **kwargs: Any) -> dict[str, Any]:
        output = LocalHttpRunClient(self.base_url, self.token, self.timeout_s).run(dict(kwargs))
        if "sdf_text" in output:
            return output
        if "selected_sdf_name" in output:
            return output
        return {
            "job_id": str(output.get("job_id") or ""),
            "output": output,
            "zip_bytes": b"",
            "selected_sdf_name": str(output.get("rank1_sdf") or output.get("sdf_path") or "rank1.sdf"),
            "sdf_text": str(output.get("sdf_text") or output.get("rank1_sdf_text") or ""),
        }


@dataclass(frozen=True)
class LocalHTTPRosettaRelaxClient:
    base_url: str
    token: str | None = None
    timeout_s: float = 21600.0

    def _call_relax(
        self,
        *,
        target_id: str,
        pdb_text: str,
        nstruct: int = 1,
        extra_flags: str | None = None,
    ) -> dict[str, Any]:
        output = LocalHttpRunClient(self.base_url, self.token, self.timeout_s).run(
            {
                "target_id": target_id,
                "pdb_content": pdb_text,
                "nstruct": max(1, int(nstruct or 1)),
                "extra_flags": extra_flags or "",
                "timeout_s": max(60, int(self.timeout_s)),
            }
        )
        relaxed_pdb_text = str(
            output.get("relaxed_pdb_content")
            or output.get("best_pdb_text")
            or output.get("pdb_content")
            or ""
        )
        if not relaxed_pdb_text.strip():
            raise RuntimeError(f"Local HTTP Rosetta relax returned no PDB content: {output}")
        score_per_residue = float(output.get("score_per_res", output.get("score_per_residue", 0.0)) or 0.0)
        return {
            "relaxed_pdb_text": relaxed_pdb_text,
            "score_per_residue": score_per_residue,
        }

    @staticmethod
    def _ca_count(pdb_text: str) -> int:
        return sum(
            1
            for line in pdb_text.splitlines()
            if line.startswith("ATOM") and line[12:16].strip() == "CA"
        )

    def run(
        self,
        input_pdb: Path,
        output_dir: Path,
        nstruct: int = 1,
        extra_flags: str | None = None,
    ) -> dict[str, Any]:
        input_pdb = Path(input_pdb)
        output_dir = Path(output_dir)
        output = self._call_relax(
            target_id=input_pdb.stem,
            pdb_text=input_pdb.read_text(encoding="utf-8"),
            nstruct=nstruct,
            extra_flags=extra_flags,
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        best_pdb_path = output_dir / f"{input_pdb.stem}_relaxed.pdb"
        best_pdb_path.write_text(output["relaxed_pdb_text"], encoding="utf-8")
        score_per_residue = float(output["score_per_residue"])
        total_score = score_per_residue * max(self._ca_count(output["relaxed_pdb_text"]), 1)
        score_path = output_dir / "score.sc"
        score_path.write_text(
            "SCORE: total_score description\n"
            f"SCORE: {total_score} {best_pdb_path.stem}\n",
            encoding="utf-8",
        )
        return {
            "best_pdb": best_pdb_path,
            "best_score": total_score,
            "score_per_residue": score_per_residue,
            "scorefile": score_path,
        }

    def relax(
        self,
        pdb_text: str,
        nstruct: int = 1,
        extra_flags: str | None = None,
    ) -> dict[str, Any]:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            input_pdb = tmp_path / "input.pdb"
            input_pdb.write_text(pdb_text, encoding="utf-8")
            result = self.run(input_pdb, tmp_path / "output", nstruct, extra_flags)
            best_pdb_path = result.get("best_pdb")
            best_pdb_text = (
                best_pdb_path.read_text(encoding="utf-8")
                if isinstance(best_pdb_path, Path) and best_pdb_path.exists()
                else ""
            )
            score_per_residue = float(result.get("score_per_residue") or 0.0)
            total_score = score_per_residue * max(self._ca_count(best_pdb_text), 1)
            return {
                "best_pdb_text": best_pdb_text,
                "total_score": total_score,
                "delta_total_score": 0.0,
                "input_total_score": 0.0,
                "description": best_pdb_path.stem if isinstance(best_pdb_path, Path) else "",
                "mode": "http_api",
            }


@dataclass(frozen=True)
class LocalHTTPAlphaFold2Client:
    base_url: str
    token: str | None = None
    timeout_s: float = 21600.0
    endpoint_id: str | None = None

    def predict(self, sequences: list[SequenceRecord], *, model_preset: str = "monomer", db_preset: str = "full_dbs", max_template_date: str = "2020-05-14", extra_flags: str | None = None, on_job_id: Callable[[str, str], None] | None = None, resume_job_ids: dict[str, str] | None = None) -> dict[str, Any]:
        payload = {
            "sequences": [{"id": seq.id, "sequence": seq.sequence} for seq in sequences],
            "model_preset": model_preset,
            "db_preset": db_preset,
            "max_template_date": max_template_date,
            "alphafold_extra_flags": extra_flags,
            "resume_job_ids": resume_job_ids or {},
        }
        output = LocalHttpRunClient(self.base_url, self.token, self.timeout_s).run(payload)
        job_id = str(output.get("job_id") or "").strip()
        if job_id and on_job_id:
            for seq in sequences:
                on_job_id(seq.id, job_id)
        results = output.get("results") if isinstance(output.get("results"), dict) else output
        if all(seq.id in results for seq in sequences):
            return results
        if len(sequences) == 1 and ("ranked_0_pdb" in output or "best_plddt" in output):
            return {sequences[0].id: output}
        return results
