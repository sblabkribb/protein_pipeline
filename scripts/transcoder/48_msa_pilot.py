#!/usr/bin/env python3
"""Step 3a — MSA operational pilot. 동결된 3 타겟만.

이것은 **운영 시험**이다. 되는지, 얼마나 걸리는지, 산출물이 비어 있지는 않은지를
본다. 품질 임계값을 정하거나 타겟을 고르는 단계가 아니다.

허용 관측   runtime · endpoint 응답 · hang / empty A3M · usable_hits ·
            기존 동결 warning 상태
금지 행위   MSA threshold 변경 · 타겟 선정 규칙 변경 · tier 변경 ·
            filtering rule 변경

세 타겟이 다 좋게 나와도 임계값을 강화하지 않고, 나빠도 완화하지 않는다.
계속 진행 여부는 **성능이 아니라 운영 가능성**으로만 판단한다 - 품질이 좋은
타겟만 골라내는 것은 금지다.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "pipeline-mcp" / "src"))
BASE = PROJECT_ROOT / "public_data" / "benchmark" / "gate0"
OUT = BASE / "msa_pilot.json"

#: 프로덕션 경로가 읽는 키. `pipeline.py` 의 `out.get("a3m_gz_b64")` 와 같아야
#: 하고, 테스트가 두 값을 대조한다.
A3M_RESPONSE_KEY = "a3m_gz_b64"

#: 배포 기본값 그대로. 동결 문서 §1 과 같아야 한다.
TARGET_DB = "uniref90"
MAX_SEQS = 3000
THREADS = 4
USE_GPU = False

AA3 = {"ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C", "GLN": "Q",
       "GLU": "E", "GLY": "G", "HIS": "H", "ILE": "I", "LEU": "L", "LYS": "K",
       "MET": "M", "PHE": "F", "PRO": "P", "SER": "S", "THR": "T", "TRP": "W",
       "TYR": "Y", "VAL": "V"}


def query_sequence(pdb_path: str) -> str:
    """원본 첫 모델의 CA 서열. 매핑 계약이 이것을 query 로 본다."""
    out, seen = [], set()
    for line in Path(pdb_path).read_text(errors="replace").splitlines():
        if line.startswith("ENDMDL"):
            break
        if not line.startswith("ATOM") or line[12:16].strip() != "CA":
            continue
        if line[16] not in (" ", "A"):
            continue
        key = (line[21], line[22:26], line[26])
        if key in seen:
            continue
        seen.add(key)
        out.append(AA3.get(line[17:20].strip(), "X"))
    return "".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=None)
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()

    host = os.environ.get("RAPID_GPU_HOST", "")
    url = args.url or f"http://{host}:18106"
    from pipeline_mcp.bio.a3m import decode_a3m_gz_b64, msa_quality
    from pipeline_mcp.clients.local_http import LocalHTTPMMseqsClient

    spec = json.loads((BASE / "masked_holdout_targets.json").read_text(encoding="utf-8"))
    pilot = spec["msa_pilot"]["targets"]
    by_domain = {t["domain"]: t for t in spec["selected"]}
    print(f"동결된 pilot 타겟: {pilot}")
    print(f"설정 target_db={TARGET_DB} max_seqs={MAX_SEQS} threads={THREADS} "
          f"use_gpu={USE_GPU}\n")

    client = LocalHTTPMMseqsClient(base_url=url, token=None, timeout_s=7200.0)
    rows = []
    for stratum, domain in sorted(pilot.items()):
        row = by_domain[domain]
        seq = query_sequence(row["pdb"])
        fasta = f">{domain}\n{seq}\n"
        print(f"[{stratum}] {domain} · {len(seq)} aa · 시작", flush=True)
        started = time.time()
        entry = {"stratum": stratum, "domain": domain, "length": len(seq)}
        try:
            out = client.search(query_fasta=fasta, target_db=TARGET_DB,
                                threads=THREADS, use_gpu=USE_GPU,
                                return_a3m=True, max_seqs=MAX_SEQS)
            entry["endpoint_status"] = "ok"
            entry["response_keys"] = sorted(out)
            # 서버는 A3M 을 gzip+base64 로 준다. 프로덕션 경로
            # (pipeline.py -> bio.a3m.decode_a3m_gz_b64) 와 **같은 키**를 읽어야
            # 한다. 이 스크립트는 처음에 `a3m`/`a3m_text` 만 읽어서, 서버가
            # 정상 응답한 3 타겟을 모두 MSA_INFEASIBLE 로 기록했다.
            a3m_b64 = out.get(A3M_RESPONSE_KEY)
            if a3m_b64:
                a3m = decode_a3m_gz_b64(str(a3m_b64))
                entry["a3m_source_key"] = A3M_RESPONSE_KEY
            else:
                # 평문으로 주는 배포도 있을 수 있으므로 남겨 둔다. 없으면 빈 문자열.
                a3m = str(out.get("a3m") or out.get("a3m_text") or "")
                entry["a3m_source_key"] = ("a3m" if out.get("a3m") else
                                           "a3m_text" if out.get("a3m_text") else None)
            entry["a3m_bytes"] = len(a3m)
            entry["a3m_empty"] = not a3m.strip()
            # 서버가 실제로 찾은 hit 수. a3m 이 비었을 때 원인을 가른다 -
            # hit_count > 0 이면 파싱 문제, 0 이면 검색 문제다.
            for k in ("hit_count", "query_length", "query_id"):
                if k in out:
                    entry[k] = out[k]
            if a3m.strip():
                q = msa_quality(a3m)
                entry["msa_quality"] = {
                    k: q.get(k) for k in
                    ("usable_hits", "coverage", "depth", "full_length_fraction",
                     "warnings", "query_length")}
            else:
                entry["classification"] = "MSA_INFEASIBLE"
        except Exception as exc:
            entry["endpoint_status"] = "failed"
            entry["error"] = f"{type(exc).__name__}: {exc}"[:300]
            entry["classification"] = "MSA_INFEASIBLE"
        entry["wall_seconds"] = round(time.time() - started, 1)

        # 동결된 §3 규칙만 적용한다. 새 규칙을 만들지 않는다.
        if "classification" not in entry:
            q = entry.get("msa_quality") or {}
            hits = q.get("usable_hits")
            entry["classification"] = ("MSA_INSUFFICIENT_DEPTH"
                                       if isinstance(hits, int) and hits < 10
                                       else "OK")
        print(f"    {entry['wall_seconds']}s · {entry['endpoint_status']} · "
              f"{entry['classification']}", flush=True)
        rows.append(entry)

    print(f"\n{'타겟':10s}{'aa':>5}{'wall(s)':>9}{'a3m bytes':>11}"
          f"{'usable_hits':>12}  판정")
    for e in rows:
        q = e.get("msa_quality") or {}
        print(f"  {e['domain']:8s}{e['length']:>5}{e['wall_seconds']:>9}"
              f"{e.get('a3m_bytes', 0):>11}{str(q.get('usable_hits', '-')):>12}"
              f"  {e['classification']}")
    for e in rows:
        w = (e.get("msa_quality") or {}).get("warnings") or []
        if w:
            print(f"  {e['domain']} warnings: {w}")

    report = {
        "purpose": "MSA operational pilot. 운영 가능성만 본다.",
        "frozen_targets": pilot,
        "settings": {"target_db": TARGET_DB, "max_seqs": MAX_SEQS,
                     "threads": THREADS, "use_gpu": USE_GPU},
        "allowed_observations": spec["msa_pilot"]["allowed_observations"],
        "forbidden_actions": spec["msa_pilot"]["forbidden_actions"],
        "not_inspected": ["joint-pass", "SoluProt", "AF2", "EFBC", "kappa_pool",
                          "calibration 612"],
        "results": rows,
        "total_wall_seconds": round(sum(e["wall_seconds"] for e in rows), 1),
        "code_sha": subprocess.run(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT,
                                   capture_output=True, text=True).stdout.strip(),
        "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2),
                              encoding="utf-8")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
