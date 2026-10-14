"""SoluProt scoring service.

Scores sequences with the official SoluProt 1.0.1.0 release (Hon et al. 2021).
SoluProt needs Python 3.7 with scikit-learn 0.20.1, so it cannot be imported
here; it is executed as a subprocess in its own environment. Paths come from
the environment so that the installation can move without a code change:

    SOLUPROT_DIR      directory holding soluprot.py (soluprot-1.0.1.0)
    SOLUPROT_PYTHON   interpreter of the SoluProt environment
    SOLUPROT_USEARCH  usearch binary used for the sequence identity feature
    SOLUPROT_CACHE    sqlite file caching scores per sequence
    SOLUPROT_PROCS    worker processes handed to SoluProt (default 2)
    SOLUPROT_CHUNK    sequences per subprocess call (default 256)
    SOLUPROT_TIMEOUT  seconds allowed for one subprocess call (default 1800)

TMHMM requires a separate academic registration, so the TMHMM-independent
model shipped by the authors (grad_clf_v1_tc_notmhmm) is used via --no_tmhmm.
This matches the scoring used for the published benchmark results.

Sequences shorter than 20 residues are outside the model's domain and are
reported with a null score instead of a guess; a single such sequence would
otherwise abort the whole SoluProt batch.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

_SEQ_RE = re.compile(r"[^A-Za-z]+")

MIN_LENGTH = 20
MODEL_ID = "soluprot-1.0.1.0/grad_clf_v1_tc_notmhmm"

SOLUPROT_DIR = Path(
    os.environ.get("SOLUPROT_DIR") or "/opt/soluprot_dl/extracted/soluprot-1.0.1.0"
)
SOLUPROT_PYTHON = Path(
    os.environ.get("SOLUPROT_PYTHON")
    or "/opt/soluprot_env/mamba/envs/soluprot/bin/python"
)
SOLUPROT_USEARCH = Path(
    os.environ.get("SOLUPROT_USEARCH") or "/opt/soluprot_env/tools/usearch11"
)
CACHE_PATH = Path(
    os.environ.get("SOLUPROT_CACHE") or "/opt/soluprot_env/cache/scores.sqlite3"
)
PROCS = int(os.environ.get("SOLUPROT_PROCS") or "2")
CHUNK = int(os.environ.get("SOLUPROT_CHUNK") or "256")
TIMEOUT_S = float(os.environ.get("SOLUPROT_TIMEOUT") or "1800")

# SoluProt 은 CPU 를 많이 쓰므로 한 번에 한 배치만 실행한다.
_RUN_LOCK = threading.Lock()


def clean_sequence(seq: str) -> str:
    return _SEQ_RE.sub("", (seq or "")).upper()


def cache_key(sequence: str) -> str:
    return hashlib.sha256(f"{MODEL_ID}\n{sequence}".encode("utf-8")).hexdigest()


class ScoreCache:
    """같은 서열을 다시 채점하지 않도록 점수를 파일에 보관한다."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as con:
            con.execute(
                "CREATE TABLE IF NOT EXISTS scores ("
                "key TEXT PRIMARY KEY, score REAL NOT NULL, created_at REAL NOT NULL)"
            )

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(str(self._path), timeout=30.0)
        con.execute("PRAGMA journal_mode=WAL")
        return con

    def get_many(self, sequences: list[str]) -> dict[str, float]:
        if not sequences:
            return {}
        found: dict[str, float] = {}
        keys = {cache_key(s): s for s in sequences}
        with self._lock, self._connect() as con:
            for start in range(0, len(keys), 400):
                batch = list(keys)[start : start + 400]
                placeholders = ",".join("?" * len(batch))
                rows = con.execute(
                    f"SELECT key, score FROM scores WHERE key IN ({placeholders})",
                    batch,
                ).fetchall()
                for key, score in rows:
                    found[keys[key]] = float(score)
        return found

    def put_many(self, scores: dict[str, float]) -> None:
        if not scores:
            return
        now = time.time()
        rows = [(cache_key(s), float(v), now) for s, v in scores.items()]
        with self._lock, self._connect() as con:
            con.executemany(
                "INSERT OR REPLACE INTO scores (key, score, created_at) "
                "VALUES (?, ?, ?)",
                rows,
            )

    def count(self) -> int:
        with self._lock, self._connect() as con:
            return int(con.execute("SELECT COUNT(*) FROM scores").fetchone()[0])


CACHE = ScoreCache(CACHE_PATH)


class SoluProtError(RuntimeError):
    pass


def _run_chunk(sequences: list[str]) -> dict[str, float]:
    """고유 서열 묶음 하나를 SoluProt 으로 채점한다."""
    with tempfile.TemporaryDirectory(prefix="soluprot-") as tmp:
        tmpd = Path(tmp)
        work = tmpd / "work"
        work.mkdir()
        fasta = tmpd / "in.fasta"
        with fasta.open("w", encoding="utf-8") as fh:
            for i, seq in enumerate(sequences):
                fh.write(f">u{i}\n{seq}\n")
        out_csv = tmpd / "out.csv"
        cmd = [
            str(SOLUPROT_PYTHON),
            "soluprot.py",
            "--i_fa",
            str(fasta),
            "--o_csv",
            str(out_csv),
            "--tmp_dir",
            str(work),
            "--no_tmhmm",
            "--usearch",
            str(SOLUPROT_USEARCH),
            "--no_proc",
            str(PROCS),
        ]
        env = dict(os.environ)
        env.setdefault("OMP_NUM_THREADS", str(PROCS))
        env.setdefault("MKL_NUM_THREADS", str(PROCS))
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(SOLUPROT_DIR),
                env=env,
                capture_output=True,
                text=True,
                timeout=TIMEOUT_S,
            )
        except subprocess.TimeoutExpired as exc:
            raise SoluProtError(
                f"SoluProt timed out after {TIMEOUT_S:.0f}s "
                f"({len(sequences)} sequences)"
            ) from exc
        if not out_csv.is_file():
            tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-3:]
            raise SoluProtError(
                "SoluProt produced no output: " + " | ".join(tail)
            )
        by_uid: dict[str, float] = {}
        with out_csv.open(encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                by_uid[row["fa_id"]] = float(row["soluble"])
    out: dict[str, float] = {}
    for i, seq in enumerate(sequences):
        score = by_uid.get(f"u{i}")
        if score is not None:
            out[seq] = score
    missing = len(sequences) - len(out)
    if missing:
        raise SoluProtError(f"SoluProt returned no score for {missing} sequences")
    return out


def score_sequences(sequences: list[str]) -> dict[str, float]:
    """정리된 고유 서열 목록을 점수로 바꾼다. 캐시를 먼저 확인한다."""
    uniq = sorted({s for s in sequences if len(s) >= MIN_LENGTH})
    scores = CACHE.get_many(uniq)
    todo = [s for s in uniq if s not in scores]
    if not todo:
        return scores
    with _RUN_LOCK:
        # 대기하는 동안 다른 요청이 채점했을 수 있다.
        scores.update(CACHE.get_many(todo))
        todo = [s for s in todo if s not in scores]
        fresh: dict[str, float] = {}
        for start in range(0, len(todo), CHUNK):
            fresh.update(_run_chunk(todo[start : start + CHUNK]))
        CACHE.put_many(fresh)
    scores.update(fresh)
    return scores


def installation_problems() -> list[str]:
    problems: list[str] = []
    if not (SOLUPROT_DIR / "soluprot.py").is_file():
        problems.append(f"missing soluprot.py under {SOLUPROT_DIR}")
    if not os.access(str(SOLUPROT_PYTHON), os.X_OK):
        problems.append(f"interpreter not executable: {SOLUPROT_PYTHON}")
    if not os.access(str(SOLUPROT_USEARCH), os.X_OK):
        problems.append(f"usearch not executable: {SOLUPROT_USEARCH}")
    return problems


class Handler(BaseHTTPRequestHandler):
    server_version = "SoluProt/1.0.1.0"

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _json(self, code: int, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or "0")
        raw = self.rfile.read(length) if length > 0 else b"{}"
        data = json.loads(raw.decode("utf-8", errors="replace"))
        if not isinstance(data, dict):
            raise ValueError("JSON body must be an object")
        return data

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.rstrip("/")
        if path == "/healthz":
            problems = installation_problems()
            self._json(
                200 if not problems else 503,
                {
                    "ok": not problems,
                    "model": MODEL_ID,
                    "min_length": MIN_LENGTH,
                    "cached_sequences": CACHE.count(),
                    "problems": problems,
                },
            )
            return
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path.rstrip("/") != "/score":
            self._json(404, {"error": "not found"})
            return
        try:
            body = self._read_json()
            sequences = body.get("sequences")
            if not isinstance(sequences, list):
                raise ValueError("Expected {sequences: [{id, sequence}, ...]}")
            items: list[tuple[str, str]] = []
            for item in sequences:
                if not isinstance(item, dict):
                    continue
                sid = str(item.get("id") or "")
                if not sid:
                    continue
                items.append((sid, clean_sequence(str(item.get("sequence") or ""))))
        except Exception as exc:
            self._json(400, {"error": str(exc)})
            return

        started = time.time()
        try:
            scores = score_sequences([seq for _sid, seq in items])
        except SoluProtError as exc:
            self._json(503, {"error": str(exc), "model": MODEL_ID})
            return
        except Exception as exc:  # 예기치 못한 오류도 점수를 지어내지 않는다.
            self._json(503, {"error": f"{type(exc).__name__}: {exc}", "model": MODEL_ID})
            return

        results: list[dict[str, Any]] = []
        for sid, seq in items:
            if len(seq) < MIN_LENGTH:
                results.append(
                    {
                        "id": sid,
                        "score": None,
                        "error": (
                            f"sequence shorter than {MIN_LENGTH} residues "
                            "is outside the SoluProt domain"
                        ),
                    }
                )
                continue
            results.append({"id": sid, "score": scores[seq]})
        sys.stderr.write(
            "scored %d sequences in %.1fs\n" % (len(items), time.time() - started)
        )
        self._json(200, {"results": results, "model": MODEL_ID})


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18081)
    args = parser.parse_args(argv)

    problems = installation_problems()
    if problems:
        for p in problems:
            print(f"SoluProt installation problem: {p}", file=sys.stderr)
        raise SystemExit(2)
    if shutil.which("usearch") is None:
        pass  # usearch 는 전체 경로로 넘기므로 PATH 에 없어도 된다.

    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(
        f"listening: http://{args.host}:{args.port} · model {MODEL_ID} "
        f"· cache {CACHE_PATH}",
        flush=True,
    )
    httpd.serve_forever()


if __name__ == "__main__":
    main()
