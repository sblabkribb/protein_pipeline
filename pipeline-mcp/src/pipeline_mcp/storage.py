from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import time
import uuid
import shutil


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


def read_jsonl(path: Path, *, limit: int | None = None) -> list[object]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    if limit is not None:
        lines = lines[-int(limit) :] if limit > 0 else []
    out: list[object] = []
    for raw in lines:
        if not raw.strip():
            continue
        try:
            out.append(json.loads(raw))
        except Exception:
            continue
    return out


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


def delete_run(output_root: str, run_id: str) -> dict[str, object]:
    root = resolve_run_path(output_root, run_id)
    if not root.exists():
        return {"run_id": run_id, "found": False, "deleted": False}
    shutil.rmtree(root)
    return {"run_id": run_id, "found": True, "deleted": True}


def load_status(output_root: str, run_id: str) -> dict[str, object] | None:
    path = Path(output_root).resolve() / run_id / "status.json"
    if not path.exists():
        return None
    data = read_json(path)
    if isinstance(data, dict):
        return data
    return None


def _safe_relpath(path: str) -> Path:
    raw = str(path or "").replace("\\", "/")
    rel = Path(raw)
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError("path must be a relative path without '..'")
    return rel


def resolve_run_path(output_root: str, run_id: str, rel_path: str | None = None) -> Path:
    run_id = normalize_run_id(run_id)
    root = Path(output_root).resolve() / run_id
    if rel_path is None or str(rel_path).strip() == "":
        return root
    return root / _safe_relpath(rel_path)


def run_exists(output_root: str, run_id: str) -> bool:
    root = resolve_run_path(output_root, run_id)
    return root.exists()


def append_run_event(output_root: str, run_id: str, *, filename: str, payload: dict[str, object]) -> dict[str, object]:
    root = resolve_run_path(output_root, run_id)
    if not root.exists():
        raise ValueError("run_id not found")
    path = root / filename
    append_jsonl(path, payload)
    return payload


def list_run_events(
    output_root: str,
    run_id: str,
    *,
    filename: str,
    limit: int | None = None,
) -> list[dict[str, object]]:
    root = resolve_run_path(output_root, run_id)
    if not root.exists():
        raise ValueError("run_id not found")
    path = root / filename
    items = read_jsonl(path, limit=limit)
    out: list[dict[str, object]] = []
    for item in items:
        if isinstance(item, dict):
            out.append(item)
    return out


def list_artifacts(
    output_root: str,
    run_id: str,
    *,
    prefix: str | None = None,
    max_depth: int = 4,
    limit: int = 200,
) -> list[dict[str, object]]:
    root = resolve_run_path(output_root, run_id)
    base = resolve_run_path(output_root, run_id, prefix) if prefix else root
    if not base.exists():
        return []

    results: list[dict[str, object]] = []
    root = root.resolve()
    base = base.resolve()
    max_depth = max(0, int(max_depth))
    limit = max(0, int(limit))

    if base.is_file():
        rel = base.resolve().relative_to(root)
        stat = base.stat()
        return [
            {
                "path": str(rel).replace("\\", "/"),
                "type": "file",
                "size": int(stat.st_size),
                "modified_at": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(stat.st_mtime)),
            }
        ]

    for dirpath, dirnames, filenames in os.walk(base):
        rel_dir = Path(dirpath).resolve().relative_to(base)
        depth = len(rel_dir.parts)
        if depth >= max_depth:
            dirnames[:] = []
        dirnames.sort()
        filenames.sort()

        for name in dirnames:
            if limit and len(results) >= limit:
                return results
            path = Path(dirpath) / name
            rel = path.resolve().relative_to(root)
            stat = path.stat()
            results.append(
                {
                    "path": str(rel).replace("\\", "/"),
                    "type": "dir",
                    "size": int(stat.st_size),
                    "modified_at": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(stat.st_mtime)),
                }
            )
        for name in filenames:
            if limit and len(results) >= limit:
                return results
            path = Path(dirpath) / name
            rel = path.resolve().relative_to(root)
            stat = path.stat()
            results.append(
                {
                    "path": str(rel).replace("\\", "/"),
                    "type": "file",
                    "size": int(stat.st_size),
                    "modified_at": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(stat.st_mtime)),
                }
            )
        if limit and len(results) >= limit:
            return results

    return results


def read_artifact(
    output_root: str,
    run_id: str,
    *,
    path: str,
    max_bytes: int = 2_000_000,
    offset: int = 0,
) -> tuple[bytes, dict[str, object]]:
    target = resolve_run_path(output_root, run_id, path)
    if not target.exists():
        raise ValueError("artifact not found")
    if not target.is_file():
        raise ValueError("artifact is not a file")
    size = target.stat().st_size
    offset = max(0, int(offset))
    max_bytes = max(0, int(max_bytes))
    with target.open("rb") as f:
        if offset:
            f.seek(offset)
        data = f.read(max_bytes if max_bytes > 0 else None)
    read_bytes = len(data)
    truncated = (offset + read_bytes) < size
    meta = {
        "path": str(Path(path).as_posix()),
        "size": int(size),
        "offset": int(offset),
        "read_bytes": int(read_bytes),
        "truncated": bool(truncated),
    }
    return data, meta
