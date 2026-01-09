from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import time
import uuid


_SAFE_NAME_RE = re.compile(r"[^a-zA-Z0-9_.-]+")


def new_run_id(prefix: str = "run") -> str:
    ts = time.strftime("%Y%m%d_%H%M%S", time.gmtime())
    rand = uuid.uuid4().hex[:8]
    safe_prefix = _SAFE_NAME_RE.sub("_", prefix).strip("._-") or "run"
    return f"{safe_prefix}_{ts}_{rand}"


def normalize_run_id(run_id: str) -> str:
    candidate = str(run_id or "").strip()
    if not candidate:
        raise ValueError("run_id is empty")
    if len(candidate) > 128:
        raise ValueError("run_id is too long (max 128 chars)")
    if candidate in {".", ".."}:
        raise ValueError("run_id is invalid")
    safe = _SAFE_NAME_RE.sub("_", candidate).strip("._-")
    if safe != candidate or not safe:
        raise ValueError("run_id contains invalid characters; allowed: [a-zA-Z0-9_.-]")
    return candidate


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def append_jsonl(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(data, ensure_ascii=False) + "\n")


@dataclass(frozen=True)
class RunPaths:
    run_id: str
    root: Path

    @property
    def request_json(self) -> Path:
        return self.root / "request.json"

    @property
    def summary_json(self) -> Path:
        return self.root / "summary.json"

    @property
    def status_json(self) -> Path:
        return self.root / "status.json"

    @property
    def events_jsonl(self) -> Path:
        return self.root / "events.jsonl"


def init_run(output_root: str, run_id: str) -> RunPaths:
    root = ensure_dir(Path(output_root).resolve() / run_id)
    return RunPaths(run_id=run_id, root=root)


def set_status(paths: RunPaths, *, stage: str, state: str, detail: str | None = None) -> None:
    payload: dict[str, object] = {
        "run_id": paths.run_id,
        "stage": stage,
        "state": state,
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()),
    }
    if detail:
        payload["detail"] = detail
    write_json(paths.status_json, payload)
    append_jsonl(paths.events_jsonl, {"kind": "status", **payload})


def list_runs(output_root: str, *, limit: int = 50) -> list[str]:
    root = Path(output_root).resolve()
    if not root.exists():
        return []
    runs = [p.name for p in root.iterdir() if p.is_dir()]
    runs.sort(reverse=True)
    return runs[: max(0, int(limit))]


def load_status(output_root: str, run_id: str) -> dict[str, object] | None:
    path = Path(output_root).resolve() / run_id / "status.json"
    if not path.exists():
        return None
    data = read_json(path)
    if isinstance(data, dict):
        return data
    return None
