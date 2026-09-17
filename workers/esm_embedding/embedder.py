from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import io
import os
import threading
import time
from typing import Any

import numpy as np
import torch
from transformers import AutoTokenizer, EsmModel


DEFAULT_MODEL_NAME = os.environ.get("ESM_MODEL_NAME", "facebook/esm2_t6_8M_UR50D")


_TOKENIZER: AutoTokenizer | None = None
_MODEL: EsmModel | None = None
_MODEL_NAME: str | None = None
_DEVICE: torch.device | None = None
#: 마지막으로 임베딩을 낸 시각. None 이면 아직 쓰인 적이 없다.
_LAST_USED: float | None = None
_LOAD_LOCK = threading.Lock()

#: 유휴 언로드 기본 대기(초). 0 이면 끄고 상주한다.
DEFAULT_IDLE_UNLOAD_S = 300.0


def idle_unload_s() -> float:
    """``ESM_IDLE_UNLOAD_S`` 로 조절. 0 이면 유휴 언로드를 하지 않는다."""
    raw = os.environ.get("ESM_IDLE_UNLOAD_S", "").strip()
    if not raw:
        return DEFAULT_IDLE_UNLOAD_S
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        return DEFAULT_IDLE_UNLOAD_S


def unload_model() -> bool:
    """올라간 모델을 내리고 GPU 캐시를 반납한다. 내린 게 있으면 True.

    가중치는 8M 이라 작지만, 반납해야 하는 것은 캐싱 할당자가 잡고 있는
    과거 배치 피크다. 그게 카드를 수십 GB 물고 있는 실제 원인이었다.
    """
    global _TOKENIZER, _MODEL, _MODEL_NAME, _DEVICE
    with _LOAD_LOCK:
        if _MODEL is None and _TOKENIZER is None:
            return False
        _TOKENIZER = None
        _MODEL = None
        _MODEL_NAME = None
        _DEVICE = None
    try:
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        # 캐시 반납 실패가 언로드 실패는 아니다.
        pass
    return True


def maybe_unload_idle(*, now: float | None = None) -> bool:
    """유휴가 임계를 넘었으면 모델을 내린다. 내렸으면 True."""
    window = idle_unload_s()
    if window <= 0:
        return False
    last = _LAST_USED
    if last is None:
        return False
    current = time.monotonic() if now is None else float(now)
    if current - last < window:
        return False
    return unload_model()


def start_idle_reaper(*, interval_s: float = 60.0) -> threading.Thread:
    """유휴 언로드를 주기적으로 점검하는 데몬 스레드를 띄운다.

    카드를 다른 워커와 공유하므로, 요청이 끊기면 GPU 를 물고 있지 않는다.
    """

    def _loop() -> None:
        while True:
            time.sleep(float(interval_s))
            try:
                maybe_unload_idle()
            except Exception:
                # 리퍼가 워커를 죽이지 않는다.
                pass

    thread = threading.Thread(target=_loop, name="esm-idle-reaper", daemon=True)
    thread.start()
    return thread


@dataclass(frozen=True)
class SequenceItem:
    id: str
    sequence: str


def normalize_sequence(value: object) -> str:
    return "".join(str(value or "").split()).upper()


def sequence_hash(sequence: str) -> str:
    return hashlib.sha256(normalize_sequence(sequence).encode("utf-8")).hexdigest()


def parse_sequences(value: object) -> list[SequenceItem]:
    if not isinstance(value, list):
        raise ValueError("sequences must be a list")
    items: list[SequenceItem] = []
    for index, entry in enumerate(value):
        if isinstance(entry, str):
            seq_id = f"seq_{index + 1}"
            sequence = normalize_sequence(entry)
        elif isinstance(entry, dict):
            seq_id = str(entry.get("id") or entry.get("sequence_id") or f"seq_{index + 1}").strip()
            sequence = normalize_sequence(entry.get("sequence"))
        else:
            raise ValueError(f"sequence item {index} must be a string or object")
        if not seq_id:
            seq_id = f"seq_{index + 1}"
        if not sequence:
            raise ValueError(f"sequence item {seq_id!r} is empty")
        items.append(SequenceItem(id=seq_id, sequence=sequence))
    return items


def _device() -> torch.device:
    requested = os.environ.get("ESM_DEVICE", "").strip().lower()
    if requested:
        return torch.device(requested)
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def _load_model(model_name: str) -> tuple[AutoTokenizer, EsmModel, torch.device]:
    global _TOKENIZER, _MODEL, _MODEL_NAME, _DEVICE
    if _TOKENIZER is not None and _MODEL is not None and _MODEL_NAME == model_name and _DEVICE is not None:
        return _TOKENIZER, _MODEL, _DEVICE
    device = _device()
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = EsmModel.from_pretrained(model_name).to(device)
    model.eval()
    _TOKENIZER = tokenizer
    _MODEL = model
    _MODEL_NAME = model_name
    _DEVICE = device
    return tokenizer, model, device


def _encode_npz(embeddings: np.ndarray) -> str:
    buffer = io.BytesIO()
    np.savez_compressed(buffer, embeddings=embeddings.astype(np.float32, copy=False))
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def embed_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if bool(payload.get("health")):
        return {
            "ok": True,
            "ready": True,
            "model_name": os.environ.get("ESM_MODEL_NAME", DEFAULT_MODEL_NAME),
            "cuda_available": bool(torch.cuda.is_available()),
            # 상주 중인지가 보여야 카드 점유를 추적할 수 있다.
            "loaded": _MODEL is not None,
            "idle_unload_s": idle_unload_s(),
        }

    start = time.monotonic()
    model_name = str(payload.get("model_name") or DEFAULT_MODEL_NAME).strip() or DEFAULT_MODEL_NAME
    batch_size = max(1, int(payload.get("batch_size") or os.environ.get("ESM_BATCH_SIZE", "64")))
    max_length = max(1, int(payload.get("max_length") or os.environ.get("ESM_MAX_LENGTH", "1024")))
    items = parse_sequences(payload.get("sequences"))
    tokenizer, model, device = _load_model(model_name)

    embeddings: list[np.ndarray] = []
    with torch.no_grad():
        for offset in range(0, len(items), batch_size):
            batch = items[offset : offset + batch_size]
            encoded = tokenizer(
                [item.sequence for item in batch],
                return_tensors="pt",
                padding=True,
                truncation=True,
                max_length=max_length,
            )
            encoded = {key: value.to(device) for key, value in encoded.items()}
            output = model(**encoded)
            mask = encoded["attention_mask"].unsqueeze(-1).expand(output.last_hidden_state.size()).float()
            summed = torch.sum(output.last_hidden_state * mask, dim=1)
            denom = torch.clamp(mask.sum(dim=1), min=1e-9)
            pooled = summed / denom
            embeddings.append(pooled.detach().cpu().numpy().astype(np.float32))

    matrix = np.vstack(embeddings).astype(np.float32, copy=False)
    global _LAST_USED
    _LAST_USED = time.monotonic()
    return {
        "ok": True,
        "model_name": model_name,
        "device": str(device),
        "count": len(items),
        "dimension": int(matrix.shape[1]),
        "dtype": "float32",
        "ids": [item.id for item in items],
        "sequence_hashes": [sequence_hash(item.sequence) for item in items],
        "embedding_key": "embeddings",
        "embeddings_npz_b64": _encode_npz(matrix),
        "elapsed_s": round(time.monotonic() - start, 3),
    }
