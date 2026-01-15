from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any
from typing import Optional

import runpod


PROTEINMPNN_DIR = Path(os.environ.get("PROTEINMPNN_DIR", "/opt/ProteinMPNN")).resolve()
PROTEINMPNN_RUN = PROTEINMPNN_DIR / "protein_mpnn_run.py"


class InputError(ValueError):
    pass


def _get_event_id(event: dict[str, Any]) -> str:
    event_id = event.get("id") or event.get("job", {}).get("id") or "job"
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", str(event_id))[:128] or "job"


def _sanitize_name(name: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_.-]+", "_", name).strip("._-")
    return (safe[:64] or "input")


def _normalize_sampling_temp(value: Any) -> str:
    if value is None:
        return "0.1"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return " ".join(str(item) for item in value)
    raise InputError("sampling_temp must be a number, string, or list of numbers")


def _decode_pdb_text(input_payload: dict[str, Any]) -> str:
    if "pdb" in input_payload and input_payload["pdb"] is not None:
        if not isinstance(input_payload["pdb"], str):
            raise InputError("pdb must be a string")
        return input_payload["pdb"]

    if "pdb_base64" in input_payload and input_payload["pdb_base64"] is not None:
        if not isinstance(input_payload["pdb_base64"], str):
            raise InputError("pdb_base64 must be a base64 string")
        try:
            raw = base64.b64decode(input_payload["pdb_base64"], validate=True)
        except Exception as exc:
            raise InputError("pdb_base64 is not valid base64") from exc
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise InputError("decoded pdb_base64 is not UTF-8 text") from exc

    raise InputError("Missing required input: provide either 'pdb' or 'pdb_base64'")


def _extract_chain_ids_from_pdb(pdb_text: str) -> list[str]:
    chains: list[str] = []
    seen: set[str] = set()
    for raw in pdb_text.splitlines():
        if not raw.startswith("ATOM"):
            continue
        chain_id = raw[21:22].strip() or "_"
        if chain_id not in seen:
            seen.add(chain_id)
            chains.append(chain_id)
    return chains


def _normalize_fixed_positions(value: Any) -> dict[str, list[int]] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise InputError("fixed_positions must be an object mapping chain->positions")
    out: dict[str, list[int]] = {}
    for k, v in value.items():
        chain = str(k).strip() or "_"
        if v is None:
            out[chain] = []
            continue
        if not isinstance(v, list):
            raise InputError("fixed_positions values must be lists of ints (1-based positions)")
        positions: list[int] = []
        for item in v:
            try:
                pos = int(item)
            except Exception as exc:
                raise InputError("fixed_positions positions must be ints") from exc
            if pos <= 0:
                raise InputError("fixed_positions positions must be positive (1-based)")
            positions.append(pos)
        out[chain] = sorted(set(positions))
    return out


def _normalize_chain_list(value: Any) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        tokens = [t.strip() for t in value.split() if t.strip()]
        return tokens or None
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            if item is None:
                continue
            for tok in str(item).split():
                tok = tok.strip()
                if tok:
                    out.append(tok)
        return out or None
    token = str(value).strip()
    return [token] if token else None


def _fixed_positions_mismatch_count(
    *,
    native_seq: str,
    sample_seq: str,
    chain_order: list[str],
    fixed_positions: dict[str, list[int]],
) -> int:
    native_parts = native_seq.split("/") if "/" in native_seq else [native_seq]
    sample_parts = sample_seq.split("/") if "/" in sample_seq else [sample_seq]
    if len(native_parts) != len(sample_parts) or len(sample_parts) != len(chain_order):
        return 0

    mismatches = 0
    for i, chain_id in enumerate(chain_order):
        fixed = fixed_positions.get(chain_id) or []
        if not fixed:
            continue
        n = native_parts[i]
        s = sample_parts[i]
        for pos in fixed:
            idx = int(pos) - 1
            if idx < 0 or idx >= len(n) or idx >= len(s):
                continue
            if n[idx] != s[idx]:
                mismatches += 1
    return mismatches


def _enforce_fixed_positions(
    *,
    native_seq: str,
    sample_seq: str,
    chain_order: list[str],
    fixed_positions: dict[str, list[int]],
) -> str:
    native_parts = native_seq.split("/") if "/" in native_seq else [native_seq]
    sample_parts = sample_seq.split("/") if "/" in sample_seq else [sample_seq]
    if len(native_parts) != len(sample_parts) or len(sample_parts) != len(chain_order):
        return sample_seq

    out_parts: list[str] = []
    for i, chain_id in enumerate(chain_order):
        fixed = fixed_positions.get(chain_id) or []
        if not fixed:
            out_parts.append(sample_parts[i])
            continue
        native = native_parts[i]
        sample_list = list(sample_parts[i])
        for pos in fixed:
            idx = int(pos) - 1
            if idx < 0 or idx >= len(native) or idx >= len(sample_list):
                continue
            sample_list[idx] = native[idx]
        out_parts.append("".join(sample_list))
    sep = "/" if ("/" in sample_seq or "/" in native_seq) else ""
    return sep.join(out_parts)


def _parse_fasta(path: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    header: Optional[str] = None
    seq_chunks: list[str] = []

    def flush() -> None:
        nonlocal header, seq_chunks
        if header is None:
            return
        sequence = "".join(seq_chunks).strip()
        rec: dict[str, Any] = {"header": header, "sequence": sequence}
        for token in header.split(","):
            token = token.strip()
            if "=" not in token:
                if token:
                    rec.setdefault("name", token)
                continue
            k, v = token.split("=", 1)
            k = k.strip()
            v = v.strip()
            if k == "T":
                try:
                    rec[k] = float(v)
                except ValueError:
                    rec[k] = v
            elif k in {"sample", "seed"}:
                try:
                    rec[k] = int(float(v))
                except ValueError:
                    rec[k] = v
            elif k in {"score", "global_score", "seq_recovery"}:
                try:
                    rec[k] = float(v)
                except ValueError:
                    rec[k] = v
            else:
                rec[k] = v
        entries.append(rec)
        header = None
        seq_chunks = []

    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line:
            continue
        if line.startswith(">"):
            flush()
            header = line[1:].strip()
            continue
        seq_chunks.append(line.strip())

    flush()
    return entries


def handler(event: dict[str, Any]) -> dict[str, Any]:
    input_payload = event.get("input", {}) or {}
    if not isinstance(input_payload, dict):
        raise InputError("event.input must be an object")

    pdb_name = _sanitize_name(str(input_payload.get("pdb_name") or "input"))
    job_id = _get_event_id(event)

    use_soluble_model = bool(input_payload.get("use_soluble_model", True))
    ca_only = bool(input_payload.get("ca_only", False))
    if use_soluble_model and ca_only:
        raise InputError("CA-SolubleMPNN is not available; set ca_only=false for soluble models")

    model_name = str(input_payload.get("model_name") or "v_48_020")
    num_seq_per_target = int(input_payload.get("num_seq_per_target") or 1)
    batch_size = int(input_payload.get("batch_size") or 1)
    seed = int(input_payload.get("seed") or 0)
    sampling_temp = _normalize_sampling_temp(input_payload.get("sampling_temp"))
    backbone_noise = float(input_payload.get("backbone_noise") or 0.0)

    designed_chain_list = _normalize_chain_list(input_payload.get("pdb_path_chains"))
    designed_chains = " ".join(designed_chain_list) if designed_chain_list else None

    if num_seq_per_target <= 0:
        raise InputError("num_seq_per_target must be > 0")
    if batch_size <= 0:
        raise InputError("batch_size must be > 0")
    if num_seq_per_target % batch_size != 0:
        raise InputError("num_seq_per_target must be divisible by batch_size (ProteinMPNN requirement)")

    if not PROTEINMPNN_RUN.is_file():
        raise RuntimeError(f"ProteinMPNN not found at {PROTEINMPNN_RUN}")

    job_dir = Path("/tmp") / f"proteinmpnn_{job_id}"
    out_dir = job_dir / "out"
    job_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    pdb_text = _decode_pdb_text(input_payload)
    pdb_path = job_dir / f"{pdb_name}.pdb"
    pdb_path.write_text(pdb_text, encoding="utf-8")

    fixed_positions = _normalize_fixed_positions(input_payload.get("fixed_positions"))
    fixed_positions_path: Path | None = None
    if fixed_positions is not None:
        pdb_chains = _extract_chain_ids_from_pdb(pdb_text)
        for chain_id in pdb_chains:
            fixed_positions.setdefault(chain_id, [])
        fixed_positions_dict = {pdb_name: fixed_positions}
        fixed_positions_path = job_dir / "fixed_positions.jsonl"
        fixed_positions_path.write_text(json.dumps(fixed_positions_dict) + "\n", encoding="utf-8")

    cmd: list[str] = [
        "python",
        str(PROTEINMPNN_RUN),
        "--pdb_path",
        str(pdb_path),
        "--out_folder",
        str(out_dir),
        "--num_seq_per_target",
        str(num_seq_per_target),
        "--batch_size",
        str(batch_size),
        "--sampling_temp",
        sampling_temp,
        "--seed",
        str(seed),
        "--model_name",
        model_name,
        "--backbone_noise",
        str(backbone_noise),
        "--suppress_print",
        "1",
    ]
    if use_soluble_model:
        cmd.append("--use_soluble_model")
    if ca_only:
        cmd.append("--ca_only")
    if designed_chains:
        cmd.extend(["--pdb_path_chains", designed_chains])
    if fixed_positions_path is not None:
        cmd.extend(["--fixed_positions_jsonl", str(fixed_positions_path)])

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            "ProteinMPNN failed\n"
            f"cmd: {' '.join(cmd)}\n"
            f"stdout:\n{proc.stdout[-8000:]}\n"
            f"stderr:\n{proc.stderr[-8000:]}\n"
        )

    fasta_files = sorted(out_dir.glob("**/*.fa"))
    if not fasta_files:
        raise RuntimeError(
            "ProteinMPNN did not produce a .fa output\n"
            f"stdout:\n{proc.stdout[-8000:]}\n"
            f"stderr:\n{proc.stderr[-8000:]}\n"
        )
    fasta_path = fasta_files[0]

    entries = _parse_fasta(fasta_path)
    if not entries:
        raise RuntimeError(f"Empty fasta output at {fasta_path}")

    native = entries[0]
    samples = entries[1:]

    fixed_positions_diagnostic: dict[str, Any] | None = None
    if fixed_positions is not None:
        chain_order = sorted(designed_chain_list) if designed_chain_list else sorted(_extract_chain_ids_from_pdb(pdb_text))
        native_seq = str(native.get("sequence") or "")
        mismatches_before = 0
        mismatches_after = 0
        patched = 0
        enforced_samples: list[dict[str, Any]] = []
        for s in samples:
            seq = str(s.get("sequence") or "")
            mism = _fixed_positions_mismatch_count(
                native_seq=native_seq,
                sample_seq=seq,
                chain_order=chain_order,
                fixed_positions=fixed_positions,
            )
            mismatches_before += mism
            if mism > 0:
                new_seq = _enforce_fixed_positions(
                    native_seq=native_seq,
                    sample_seq=seq,
                    chain_order=chain_order,
                    fixed_positions=fixed_positions,
                )
                if new_seq != seq:
                    s = dict(s)
                    s["sequence"] = new_seq
                    patched += 1
            enforced_samples.append(s)
            mismatches_after += _fixed_positions_mismatch_count(
                native_seq=native_seq,
                sample_seq=str(s.get("sequence") or ""),
                chain_order=chain_order,
                fixed_positions=fixed_positions,
            )
        samples = enforced_samples
        fixed_positions_diagnostic = {
            "chain_order": chain_order,
            "mismatches_before": mismatches_before,
            "mismatches_after": mismatches_after,
            "patched_samples": patched,
        }

    if bool(input_payload.get("cleanup", True)):
        shutil.rmtree(job_dir, ignore_errors=True)

    return {
        "pdb_name": pdb_name,
        "model_name": model_name,
        "use_soluble_model": use_soluble_model,
        "ca_only": ca_only,
        "pdb_path_chains": designed_chains,
        "num_seq_per_target": num_seq_per_target,
        "batch_size": batch_size,
        "sampling_temp": sampling_temp,
        "seed": seed,
        "backbone_noise": backbone_noise,
        "fixed_positions": fixed_positions,
        "fixed_positions_diagnostic": fixed_positions_diagnostic,
        "native": native,
        "samples": samples,
    }


runpod.serverless.start({"handler": handler})
