from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException

from embedder import embed_payload
from embedder import idle_unload_s
from embedder import start_idle_reaper


app = FastAPI(title="RAPID ESM Embedding Worker")

# 카드를 다른 워커와 공유하므로 유휴 시 GPU 를 물고 있지 않는다.
if idle_unload_s() > 0:
    start_idle_reaper()


@app.get("/healthz")
def healthz() -> dict[str, Any]:
    return embed_payload({"health": True})


@app.post("/embed")
def embed(payload: dict[str, Any]) -> dict[str, Any]:
    result = embed_payload(payload)
    if not result.get("ok", False):
        raise HTTPException(status_code=500, detail=result)
    return result
