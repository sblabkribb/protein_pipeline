import base64
import json
import os
import re
import time
from pathlib import Path
from typing import Any

import requests


def _env_true(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "y", "on"}:
        return True
    if value in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _maybe_inject_truststore() -> None:
    if not _env_true("RUNPOD_USE_TRUSTSTORE"):
        return
    try:
        import truststore  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:
        raise RuntimeError("RUNPOD_USE_TRUSTSTORE=1 set, but 'truststore' is not installed (pip install truststore)") from exc
    truststore.inject_into_ssl()


def _requests_verify_arg() -> bool | str:
    if _env_true("RUNPOD_INSECURE") or os.environ.get("RUNPOD_SSL_VERIFY", "").strip().lower() in {"0", "false", "no", "off"}:
        return False

    ca_bundle = os.environ.get("RUNPOD_CA_BUNDLE", "").strip()
    if ca_bundle:
        if not os.path.isfile(ca_bundle):
            raise OSError(f"RUNPOD_CA_BUNDLE is set but file does not exist: {ca_bundle}")
        return ca_bundle
    return True


def _sanitize_filename_component(value: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_.-]+", "_", value).strip("._-")
    return safe[:128] or "runpod"


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_fasta(path: Path, result: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    if result.get("status") != "COMPLETED":
        raise RuntimeError(f"Job is not COMPLETED (status={result.get('status')}); not writing FASTA")

    output = result.get("output") or {}
    native = output.get("native") or {}
    samples = output.get("samples") or []

    lines: list[str] = []
    native_header = str(native.get("header") or "native").replace("\n", " ").strip()
    native_seq = str(native.get("sequence") or "").strip()
    if native_seq:
        lines.append(f">{native_header}")
        lines.append(native_seq)

    for sample in samples:
        header = str(sample.get("header") or f"sample={sample.get('sample', '')}").replace("\n", " ").strip()
        seq = str(sample.get("sequence") or "").strip()
        if not seq:
            continue
        lines.append(f">{header}")
        lines.append(seq)

    if not lines:
        raise RuntimeError("No sequences found in result.output; not writing FASTA")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_job(endpoint_id: str, api_key: str, input_payload: dict[str, Any]) -> str:
    url = f"https://api.runpod.ai/v2/{endpoint_id}/run"
    r = requests.post(
        url,
        headers={"Authorization": f"Bearer {api_key}"},
        json={"input": input_payload},
        timeout=60,
        verify=_requests_verify_arg(),
    )
    r.raise_for_status()
    data = r.json()
    return data["id"]


def poll(endpoint_id: str, api_key: str, job_id: str, interval_s: float = 2.0) -> dict[str, Any]:
    url = f"https://api.runpod.ai/v2/{endpoint_id}/status/{job_id}"
    while True:
        r = requests.get(
            url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=60,
            verify=_requests_verify_arg(),
        )
        r.raise_for_status()
        data = r.json()
        status = data.get("status")
        if status in {"COMPLETED", "FAILED", "CANCELLED"}:
            return data
        time.sleep(interval_s)


def main() -> None:
    endpoint_id = os.environ["ENDPOINT_ID"]
    api_key = os.environ["RUNPOD_API_KEY"]
    _maybe_inject_truststore()

    pdb_path = os.environ.get("PDB_PATH", "example.pdb")
    with open(pdb_path, "rb") as f:
        pdb_b64 = base64.b64encode(f.read()).decode()

    save_json = _env_bool("SAVE_JSON", default=True)
    save_fasta = _env_bool("SAVE_FASTA", default=True)
    output_dir = Path(os.environ.get("OUTPUT_DIR", "outputs")).resolve()

    job_id = run_job(
        endpoint_id,
        api_key,
        {
            "pdb_base64": pdb_b64,
            "pdb_name": os.environ.get("PDB_NAME", "input"),
            "use_soluble_model": True,
            "model_name": "v_48_020",
            "num_seq_per_target": 8,
            "batch_size": 1,
            "sampling_temp": 0.1,
            "seed": 1,
            "pdb_path_chains": "A",
        },
    )
    print("job_id:", job_id)

    result = poll(endpoint_id, api_key, job_id)
    print(result)

    prefix = _sanitize_filename_component(os.environ.get("OUTPUT_PREFIX", "").strip() or job_id)
    if save_json:
        json_path = output_dir / f"{prefix}.json"
        _write_json(json_path, result)
        print("saved_json:", str(json_path))
    if save_fasta:
        fasta_path = output_dir / f"{prefix}.fasta"
        try:
            _write_fasta(fasta_path, result)
        except Exception as exc:
            print("fasta_not_saved:", str(exc))
        else:
            print("saved_fasta:", str(fasta_path))


if __name__ == "__main__":
    main()
