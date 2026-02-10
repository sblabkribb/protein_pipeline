from __future__ import annotations

import re

from .models import PipelineRequest


_STOP_WORDS = ("까지만", "stop", "중단", "까지만 실행")


def route_prompt(prompt: str) -> dict[str, object]:
    p = (prompt or "").strip().lower()
    stop_after: str | None = None
    if any(w in p for w in _STOP_WORDS):
        if "msa" in p or "mmseqs" in p:
            stop_after = "msa"
        elif "design" in p or "proteinmpnn" in p:
            stop_after = "design"
        elif "soluprot" in p:
            stop_after = "soluprot"
        elif "af2" in p or "alphafold" in p:
            stop_after = "af2"
        elif "novel" in p or "search" in p or "검색" in p:
            stop_after = "novelty"

    tiers = None
    if "30" in p and "50" in p and "70" in p:
        tiers = [0.3, 0.5, 0.7]

    num = None
    m = re.search(r"(\d+)\s*(개|seq|sequences?)", p)
    if m:
        try:
            num = int(m.group(1))
        except Exception:
            num = None

    partial_t = None
    m = re.search(r"(?:diffuser\.partial[_\s-]*t|partial[_\s-]*t)\s*[:=]?\s*(\d+)", p)
    if m:
        try:
            partial_t = int(m.group(1))
        except Exception:
            partial_t = None

    out: dict[str, object] = {}
    if partial_t is not None:
        out["rfd3_partial_t"] = partial_t
    if stop_after:
        out["stop_after"] = stop_after
    if tiers:
        out["conservation_tiers"] = tiers
    if num is not None:
        out["num_seq_per_tier"] = num
    return out


def request_from_prompt(*, prompt: str, target_fasta: str, target_pdb: str) -> PipelineRequest:
    routed = route_prompt(prompt)
    kwargs = dict(routed)
    return PipelineRequest(target_fasta=target_fasta or "", target_pdb=target_pdb or "", **kwargs)  # type: ignore[arg-type]
