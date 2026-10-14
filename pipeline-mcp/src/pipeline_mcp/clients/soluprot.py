from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests

from ..models import SequenceRecord


@dataclass(frozen=True)
class SoluProtClient:
    url: str
    # SoluProt 1.0.1.0 은 서열당 약 50 ms 가 걸리므로 큰 배치에는 60초로 부족하다.
    timeout_s: float = 1800.0

    def score(self, sequences: list[SequenceRecord]) -> dict[str, float]:
        payload = {
            "sequences": [{"id": s.id, "sequence": s.sequence} for s in sequences],
        }
        r = requests.post(self.url, json=payload, timeout=self.timeout_s)
        r.raise_for_status()
        data = r.json()
        results = data.get("results")
        if not isinstance(results, list):
            raise RuntimeError(f"SoluProt response missing results: {data}")
        out: dict[str, float] = {}
        for item in results:
            if not isinstance(item, dict):
                continue
            sid = str(item.get("id") or "")
            score = item.get("score")
            if sid and isinstance(score, (int, float)):
                out[sid] = float(score)
        return out

