#!/usr/bin/env python3
"""Compute single-pass ESM-2 8M pseudo-log-likelihood (naturalness) per sequence.

Cheap zero-shot baseline for the surrogate-triage comparison (Table 2): feed the
full (unmasked) sequence through esm2_t6_8M_UR50D and average the log-probability
the model assigns to each true residue. Higher = more "natural". Cached to npy,
row-aligned to the benchmark CSV.
"""
from __future__ import annotations
import os, sys, time
from pathlib import Path
import numpy as np
import pandas as pd
import torch
from transformers import AutoTokenizer, AutoModelForMaskedLM

ROOT = Path(os.environ.get("PROTEIN_PIPELINE_ROOT") or Path(__file__).resolve().parents[2])
CSV = ROOT / "public_data" / "benchmark" / "refresh" / "cath_pilot_dataset.csv"
OUT = ROOT / "data" / "benchmark" / "results" / "baseline_esm_pll.npy"
MODEL = "facebook/esm2_t6_8M_UR50D"

def main() -> int:
    df = pd.read_csv(CSV)
    seqs = df["sequence"].tolist()
    uniq = sorted(set(seqs))
    print(f"{len(seqs)} rows / {len(uniq)} unique sequences", flush=True)

    tok = AutoTokenizer.from_pretrained(MODEL)
    model = AutoModelForMaskedLM.from_pretrained(MODEL)
    model.eval()
    torch.set_num_threads(max(1, os.cpu_count() or 1))

    # bucket unique sequences by length for efficient batching
    order = sorted(range(len(uniq)), key=lambda i: len(uniq[i]))
    pll = {}
    started = time.time()
    B = 16
    done = 0
    with torch.no_grad():
        for s in range(0, len(order), B):
            idx = order[s:s + B]
            batch = [uniq[i] for i in idx]
            enc = tok(batch, return_tensors="pt", padding=True)
            out = model(**enc)
            logp = torch.log_softmax(out.logits, dim=-1)  # (B,L,V)
            ids = enc["input_ids"]
            attn = enc["attention_mask"].bool()
            # special tokens (cls/eos/pad) -> exclude
            special = torch.zeros_like(ids, dtype=torch.bool)
            for tid in (tok.cls_token_id, tok.eos_token_id, tok.pad_token_id):
                if tid is not None:
                    special |= ids == tid
            keep = attn & ~special
            tok_logp = logp.gather(-1, ids.unsqueeze(-1)).squeeze(-1)  # (B,L)
            for r, i in enumerate(idx):
                m = keep[r]
                pll[uniq[i]] = float(tok_logp[r][m].mean().item())
            done += len(idx)
            if s % (B * 25) == 0:
                el = time.time() - started
                rate = done / max(el, 1e-9)
                eta = (len(uniq) - done) / max(rate, 1e-9)
                print(f"  {done}/{len(uniq)}  {rate:.1f} seq/s  eta {eta/60:.1f} min", flush=True)

    arr = np.array([pll[s] for s in seqs], dtype=np.float64)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    np.save(OUT, arr)
    print(f"saved {OUT}  (mean {arr.mean():.4f}, std {arr.std():.4f})", flush=True)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
