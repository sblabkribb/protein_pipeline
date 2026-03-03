from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from collections.abc import Callable

from .runpod import RunPodClient


@dataclass(frozen=True)
class BioEmuRunPodClient:
    runpod: RunPodClient
    endpoint_id: str

    def sample(
        self,
        *,
        sequence: str,
        num_samples: int = 50,
        batch_size_100: int | None = None,
        model_name: str = "bioemu-v1.1",
        filter_samples: bool = True,
        base_seed: int | None = None,
        env: dict[str, str] | None = None,
        return_pdb: bool = True,
        return_sample_pdbs: bool = True,
        max_return_sample_pdbs: int = 50,
        on_job_id: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "sequence": str(sequence),
            "num_samples": int(max(1, num_samples)),
            "model_name": str(model_name or "bioemu-v1.1"),
            "filter_samples": bool(filter_samples),
            "return_pdb": bool(return_pdb),
            "return_sample_pdbs": bool(return_sample_pdbs),
            "max_return_sample_pdbs": int(max(1, max_return_sample_pdbs)),
        }
        if batch_size_100 is not None:
            payload["batch_size_100"] = int(batch_size_100)
        if base_seed is not None:
            payload["base_seed"] = int(base_seed)
        if env:
            payload["env"] = dict(env)

        _, result = self.runpod.run_and_wait_with_job_id(self.endpoint_id, payload, on_job_id=on_job_id)
        if result.get("status") != "COMPLETED":
            raise RuntimeError(f"BioEmu RunPod job not completed: {result}")
        output = result.get("output")
        if not isinstance(output, dict):
            raise RuntimeError(f"BioEmu output missing/invalid: {result}")

        status = output.get("status")
        if isinstance(status, str) and status.lower() in {"error", "failed"}:
            message = output.get("message") or output.get("details") or output
            raise RuntimeError(f"BioEmu endpoint error: {message}")

        return output
