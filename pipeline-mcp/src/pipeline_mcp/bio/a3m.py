from __future__ import annotations

import base64
from dataclasses import dataclass
import gzip
import math

from .fasta import FastaRecord
from .fasta import parse_fasta


def decode_a3m_gz_b64(a3m_gz_b64: str) -> str:
    raw = base64.b64decode(a3m_gz_b64)
    return gzip.decompress(raw).decode("utf-8", errors="replace")


def strip_insertions(a3m_seq: str) -> str:
    return "".join(ch for ch in a3m_seq if not ("a" <= ch <= "z"))


@dataclass(frozen=True)
class Conservation:
    query_length: int
    scores: list[float]
    fixed_positions_by_tier: dict[float, list[int]]


def _normalize_records(a3m_text: str) -> list[FastaRecord]:
    records = parse_fasta(a3m_text)
    normalized: list[FastaRecord] = []
    for rec in records:
        normalized.append(FastaRecord(header=rec.header, sequence=strip_insertions(rec.sequence)))
    return normalized


def conservation_scores(a3m_text: str) -> list[float]:
    records = _normalize_records(a3m_text)
    query = records[0].sequence
    L = len(query)
    if L <= 0:
        raise ValueError("A3M query sequence is empty")

    counts: list[dict[str, int]] = [dict() for _ in range(L)]
    totals: list[int] = [0 for _ in range(L)]

    for rec in records[1:]:
        seq = rec.sequence
        if len(seq) != L:
            continue
        for i, ch in enumerate(seq):
            if ch in {"-", "."}:
                continue
            up = ch.upper()
            if not up.isalpha():
                continue
            totals[i] += 1
            counts[i][up] = counts[i].get(up, 0) + 1

    scores: list[float] = []
    for i in range(L):
        if totals[i] <= 0:
            scores.append(0.0)
            continue
        max_count = max(counts[i].values(), default=0)
        scores.append(max_count / totals[i])
    return scores


def fixed_positions(
    scores: list[float],
    tiers: list[float],
    *,
    mode: str = "quantile",
) -> dict[float, list[int]]:
    if mode not in {"quantile", "threshold"}:
        raise ValueError("mode must be 'quantile' or 'threshold'")

    L = len(scores)
    if L == 0:
        return {tier: [] for tier in tiers}

    pos_scores = [(idx + 1, float(score)) for idx, score in enumerate(scores)]
    pos_scores.sort(key=lambda t: (-t[1], t[0]))

    out: dict[float, list[int]] = {}
    for tier in tiers:
        t = float(tier)
        if mode == "threshold":
            fixed = [pos for pos, score in pos_scores if score >= t]
        else:
            k = int(math.floor(L * t))
            if k < 0:
                k = 0
            if k > L:
                k = L
            fixed = [pos for pos, _score in pos_scores[:k]]
        fixed.sort()
        out[tier] = fixed
    return out


def compute_conservation(
    a3m_text: str,
    *,
    tiers: list[float],
    mode: str = "quantile",
) -> Conservation:
    records = _normalize_records(a3m_text)
    query_len = len(records[0].sequence)
    scores = conservation_scores(a3m_text)
    fixed_by_tier = fixed_positions(scores, tiers, mode=mode)
    return Conservation(query_length=query_len, scores=scores, fixed_positions_by_tier=fixed_by_tier)

