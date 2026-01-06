from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any

from .runpod import RunPodClient
from ..models import SequenceRecord


def _b64encode_text(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


@dataclass(frozen=True)
class ProteinMPNNClient:
    runpod: RunPodClient
    endpoint_id: str

    def design(
        self,
        *,
        pdb_text: str,
        pdb_name: str = "input",
        pdb_path_chains: list[str] | str | None = None,
        fixed_positions: dict[str, list[int]] | None = None,
        use_soluble_model: bool = True,
        model_name: str = "v_48_020",
        num_seq_per_target: int = 16,
        batch_size: int = 1,
        sampling_temp: float = 0.1,
        seed: int = 0,
        backbone_noise: float = 0.0,
    ) -> tuple[SequenceRecord, list[SequenceRecord], dict[str, Any]]:
        payload: dict[str, Any] = {
            "pdb_base64": _b64encode_text(pdb_text),
            "pdb_name": pdb_name,
            "use_soluble_model": bool(use_soluble_model),
            "model_name": model_name,
            "num_seq_per_target": int(num_seq_per_target),
            "batch_size": int(batch_size),
            "sampling_temp": float(sampling_temp),
            "seed": int(seed),
            "backbone_noise": float(backbone_noise),
            "cleanup": True,
        }
        if pdb_path_chains is not None:
            payload["pdb_path_chains"] = pdb_path_chains
        if fixed_positions is not None:
            payload["fixed_positions"] = fixed_positions

        result = self.runpod.run_and_wait(self.endpoint_id, payload)
        if result.get("status") != "COMPLETED":
            raise RuntimeError(f"ProteinMPNN RunPod job not completed: {result}")
        output = result.get("output")
        if not isinstance(output, dict):
            raise RuntimeError(f"ProteinMPNN output missing/invalid: {result}")

        native = output.get("native") or {}
        samples = output.get("samples") or []
        if not isinstance(native, dict) or not isinstance(samples, list):
            raise RuntimeError(f"ProteinMPNN output malformed: {output}")

        native_rec = SequenceRecord(
            id=str(native.get("name") or "native"),
            header=str(native.get("header") or "native"),
            sequence=str(native.get("sequence") or ""),
            meta={k: v for k, v in native.items() if k not in {"header", "sequence"}},
        )
        sample_recs: list[SequenceRecord] = []
        for i, s in enumerate(samples):
            if not isinstance(s, dict):
                continue
            header = str(s.get("header") or f"sample_{i+1}")
            seq = str(s.get("sequence") or "")
            sample_id = str(s.get("name") or s.get("sample") or f"s{i+1}")
            sample_recs.append(
                SequenceRecord(
                    id=sample_id,
                    header=header,
                    sequence=seq,
                    meta={k: v for k, v in s.items() if k not in {"header", "sequence"}},
                )
            )

        return native_rec, sample_recs, output

