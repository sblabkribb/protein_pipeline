#!/usr/bin/env python3
"""ThermoMPNN ddG HTTP worker (bop, port 18114).

ProteinMPNN 워커와 같은 골격: 시스템 python3 가 HTTP/잡 관리를 담당하고, 모델
추론은 THERMOMP_PYTHON venv 의 thermomp_predict.py 를 subprocess 로 돌린다.

Env:
  THERMOMP_ROOT      Kuhlman-Lab/ThermoMPNN 클론 경로 (기본
                     /home/pipeline/models/src/ThermoMPNN)
  THERMOMP_PYTHON    torch/pytorch-lightning venv python (필수)
  THERMOMP_WORKER_TOKEN  선택 bearer token
  THERMOMP_TIMEOUT_S 기본 3600

Payload: {"input": {"pdb_content" | "pdb_base64", "chain"?, "mutations"?,
                    "wt_sequence"?, "top_n"?, "target_id"?}}
Output:  {"mutations": [...], "additive_ddg_kcal_mol": float, ...}
"""

from __future__ import annotations

import argparse
import base64
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import traceback
from typing import Any

try:
    from http_worker_jobs import worker_gpu_pool, ConcurrencyLimiter, JobManager, job_id_from_query, job_id_from_request
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from http_worker_jobs import worker_gpu_pool, ConcurrencyLimiter, JobManager, job_id_from_query, job_id_from_request


JOBS = JobManager()

#: 추론 한 번에 구조 인코딩 1회 + 소형 MLP 다. 동시 실행은 소수로 충분하다.
_LIMITER = ConcurrencyLimiter(
    "THERMOMP",
    4,
    gpu_pool=worker_gpu_pool("THERMOMP"),
    gpu_cost=1,
)


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _root() -> Path:
    return Path(
        os.getenv("THERMOMP_ROOT", "/home/pipeline/models/src/ThermoMPNN")
    ).expanduser()


def _python() -> str:
    return os.getenv("THERMOMP_PYTHON", "").strip() or (shutil.which("python3") or "python3")


def _required_token() -> str | None:
    return os.getenv("THERMOMP_WORKER_TOKEN", "").strip() or None


def _safe_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(name or "input")).strip("._")
    return cleaned or "input"


def _decode_pdb(payload: dict[str, Any]) -> str:
    if isinstance(payload.get("pdb_base64"), str) and payload["pdb_base64"].strip():
        return base64.b64decode(payload["pdb_base64"]).decode("utf-8", errors="replace")
    text = payload.get("pdb_text") or payload.get("pdb_content")
    if isinstance(text, str) and text.strip():
        return text
    raise ValueError("'pdb_base64' or 'pdb_content' is required")


def _health_payload() -> dict[str, Any]:
    root = _root()
    model_path = root / "models" / "thermoMPNN_default.pt"
    vanilla = root / "vanilla_model_weights" / "v_48_020.pt"
    ready = root.is_dir() and model_path.is_file() and vanilla.is_file() and bool(_python())
    return {
        "ok": True,
        "ready": ready,
        "model": "ThermoMPNN",
        "source": "Kuhlman-Lab/ThermoMPNN (MIT)",
        "thermomp_root": str(root),
        "model_path": str(model_path),
        "checkpoint_present": model_path.is_file(),
        "vanilla_weights_present": vanilla.is_file(),
        "python": _python(),
        "token_required": _required_token() is not None,
    }


@_LIMITER.guard
def _run_predict(payload: dict[str, Any], *, job_id: str = "manual") -> dict[str, Any]:
    health = _health_payload()
    if not health["ready"]:
        raise RuntimeError(f"ThermoMPNN is not ready: {health}")
    pdb_text = _decode_pdb(payload)
    target_id = _safe_name(str(payload.get("target_id") or "design"))
    timeout_s = int(payload.get("timeout_s") or os.getenv("THERMOMP_TIMEOUT_S", "3600"))

    with tempfile.TemporaryDirectory(prefix="thermomp-") as tmp_raw:
        tmp = Path(tmp_raw)
        pdb_path = tmp / f"{target_id}.pdb"
        pdb_path.write_text(pdb_text, encoding="utf-8")
        out_path = tmp / "predictions.json"

        cmd = [
            _python(),
            str(Path(__file__).resolve().parent / "thermomp_predict.py"),
            "--pdb", str(pdb_path),
            "--out", str(out_path),
        ]
        chain = str(payload.get("chain") or "").strip()
        if chain:
            cmd.extend(["--chain", chain])
        mutations = payload.get("mutations")
        if isinstance(mutations, list) and mutations:
            cmd.extend(["--mutations", ",".join(str(m) for m in mutations)])
        elif isinstance(mutations, str) and mutations.strip():
            cmd.extend(["--mutations", mutations.strip()])
        top_n = payload.get("top_n")
        if isinstance(top_n, (int, float)) and int(top_n) > 0:
            cmd.extend(["--top-n", str(int(top_n))])

        proc = JOBS.run_command(job_id, cmd, cwd=str(tmp), timeout_s=timeout_s)
        if proc.returncode != 0:
            raise RuntimeError(
                f"ThermoMPNN driver failed exit={proc.returncode}: stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
            )
        if not out_path.exists():
            raise RuntimeError(f"driver produced no predictions.json: stdout:\n{proc.stdout}")
        payload_out = json.loads(out_path.read_text(encoding="utf-8"))
        if payload_out_error := payload_out.get("error"):
            raise RuntimeError(f"ThermoMPNN driver error: {payload_out_error}")
        return payload_out


class ThermoMPNNWorkerHandler(BaseHTTPRequestHandler):
    server_version = "ThermoMPNNHTTPWorker/1.0"

    def do_GET(self) -> None:
        route = self.path.split("?", 1)[0].rstrip("/")
        if route == "/healthz":
            _json_response(self, HTTPStatus.OK, _health_payload())
            return
        if route == "/status":
            job_id = job_id_from_query(self.path)
            _json_response(self, HTTPStatus.OK, JOBS.status_response(job_id))
            return
        _json_response(self, HTTPStatus.NOT_FOUND, {"error": f"unknown route: {route}"})

    def do_POST(self) -> None:
        route = self.path.split("?", 1)[0].rstrip("/")
        if route != "/run":
            _json_response(self, HTTPStatus.NOT_FOUND, {"error": f"unknown route: {route}"})
            return
        token = _required_token()
        if token:
            auth = self.headers.get("Authorization", "")
            if auth != f"Bearer {token}":
                _json_response(self, HTTPStatus.UNAUTHORIZED, {"error": "invalid token"})
                return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            request = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        except Exception as exc:
            _json_response(self, HTTPStatus.BAD_REQUEST, {"error": f"invalid request body: {exc}"})
            return
        payload = request.get("input") if isinstance(request.get("input"), dict) else request
        job_id = job_id_from_request(request)

        def _work() -> dict[str, Any]:
            return _run_predict(payload, job_id=job_id)

        try:
            JOBS.submit(job_id, _work)
        except Exception as exc:
            traceback.print_exc()
            _json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})
            return
        # async 규약: PENDING + job id. 결과는 GET /status?id= 로.
        _json_response(self, HTTPStatus.OK, {"id": job_id, "status": "PENDING"})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=18114)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), ThermoMPNNWorkerHandler)
    print(f"ThermoMPNN ddG worker listening on {args.host}:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
