from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from collections.abc import Callable

from .runpod import RunPodClient


@dataclass(frozen=True)
class MMseqsClient:
    runpod: RunPodClient
    endpoint_id: str

    def search(
        self,
        *,
        query_fasta: str,
        target_db: str = "uniref90",
        threads: int = 4,
        use_gpu: bool = True,
        include_taxonomy: bool = False,
        return_a3m: bool = False,
        a3m_max_return_bytes: int = 5 * 1024 * 1024,
        a3m_format_mode: int = 6,
        max_seqs: int | None = None,
        on_job_id: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "task": "search",
            "query_fasta": query_fasta,
            "target_db": target_db,
            "threads": int(threads),
            "use_gpu": bool(use_gpu),
            "include_taxonomy": bool(include_taxonomy),
        }
        if return_a3m:
            payload["return_a3m"] = True
            payload["a3m_max_return_bytes"] = int(a3m_max_return_bytes)
            payload["a3m_format_mode"] = int(a3m_format_mode)
        if max_seqs is not None:
            payload["max_seqs"] = int(max_seqs)

        _, result = self.runpod.run_and_wait_with_job_id(self.endpoint_id, payload, on_job_id=on_job_id)
        if result.get("status") != "COMPLETED":
            raise RuntimeError(f"MMseqs RunPod job not completed: {result}")
        output = result.get("output")
        if not isinstance(output, dict):
            raise RuntimeError(f"MMseqs output missing/invalid: {result}")
        if output.get("error"):
            raise RuntimeError(f"MMseqs error: {output.get('error')}")
        return output
