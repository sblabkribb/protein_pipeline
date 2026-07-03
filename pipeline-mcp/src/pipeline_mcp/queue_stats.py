"""Per-endpoint EWMA of completed-job execution duration (seconds).

Single responsibility: persist and read a rolling average duration per RunPod
endpoint, backed by one JSON file under the output root. No RunPod knowledge.
Used by the queue-ETA feature to turn queue depth into a rough wait estimate.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

_ALPHA = 0.3  # EWMA weight for the newest sample


class QueueStatsStore:
    def __init__(self, output_root: str | Path) -> None:
        self.root = Path(output_root) / "_queue_stats"
        self.path = self.root / "durations.json"

    def _load(self) -> dict[str, float]:
        try:
            data = json.loads(self.path.read_text())
        except (FileNotFoundError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _save(self, data: dict[str, float]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.root, suffix=".tmp")
        with os.fdopen(fd, "w") as fh:
            json.dump(data, fh)
        os.replace(tmp, self.path)

    def record_duration(self, endpoint_id: str, seconds: float) -> None:
        try:
            seconds = float(seconds)
        except (TypeError, ValueError):
            return
        if seconds <= 0:
            return
        data = self._load()
        prev = data.get(endpoint_id)
        data[endpoint_id] = (
            seconds if prev is None else (1 - _ALPHA) * prev + _ALPHA * seconds
        )
        self._save(data)

    def avg_duration(self, endpoint_id: str) -> float | None:
        return self._load().get(endpoint_id)
