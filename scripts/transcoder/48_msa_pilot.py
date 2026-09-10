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


def deployment_staging() -> dict:
    """배포가 MSA query 를 만들기 전에 적용하는 전처리. 하드코딩하지 않는다."""
    import dataclasses

    from pipeline_mcp.models import PipelineRequest

    def d(name):
        f = PipelineRequest.__dataclass_fields__[name]
        return f.default if f.default is not dataclasses.MISSING else f.default_factory()

    return {"strip_nonpositive_resseq": bool(d("pdb_strip_nonpositive_resseq")),
            "renumber_resseq_from_1": bool(d("pdb_renumber_resseq_from_1"))}


def ca_sequence(pdb_text: str) -> str:
    """첫 모델의 CA 서열. altLoc 은 첫 conformer 만 - **행이 아니라 잔기를 센다.**"""
    out, seen = [], set()
    for line in pdb_text.splitlines():
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


def raw_ca_sequence(pdb_path: str) -> str:
    """전처리 없는 원본 서열. 진단·대조용이고 MSA query 가 아니다."""
    return ca_sequence(Path(pdb_path).read_text(errors="replace"))


def query_sequence(pdb_path: str) -> str:
    """**배포가 MMseqs 에 보내는 것과 같은 서열.**

    `pipeline.py` 는 `msa_source_pdb_text` 를
    `_prepare_pdb_text_for_design_context(..., strip_nonpositive_resseq=
    effective_strip_nonpositive)` 로 전처리한 뒤 `target_record` 를 만들고,
    그 record 로 `target_query_fasta` 를 만든다. `effective_strip_nonpositive`
    는 `request.pdb_strip_nonpositive_resseq` (기본 True) 이고, False 로 떨어지는
    분기는 요청이 이미 strip=False·renumber=False 일 때만 탄다.

    즉 **배포의 MSA query 는 staged 서열이다.** 전처리를 빼면 resseq <= 0 잔기를
    가진 타겟에서 query 가 길어지고, 보존도의 quantile 컷 `floor(L*tier)` 과 그
    아래 인덱스가 전부 밀린다. 실행은 성공하고 마스크만 틀린다.

    실측: v2 24 타겟 중 3 개가 영향을 받았다 - 2jvfA00(-2) · 4yqiA01(-3) ·
    4q68A01(-1).
    """
    from pipeline_mcp.bio.pdb import preprocess_pdb

    text = Path(pdb_path).read_text(errors="replace")
    cfg = deployment_staging()
    if cfg["strip_nonpositive_resseq"] or cfg["renumber_resseq_from_1"]:
        text, _ = preprocess_pdb(
            text,
            strip_nonpositive_resseq=cfg["strip_nonpositive_resseq"],
            renumber_resseq_from_1=cfg["renumber_resseq_from_1"])
    return ca_sequence(text)


def quality_medians(q: dict | None) -> dict:
    """동결 8 절이 쓰는 네 값을 꺼낸다.

    `msa_quality()` 의 `coverage` 와 `depth` 는 스칼라가 아니라 백분위 dict
    (`p25/p50/p75`) 다. 동결 기준이 "median coverage < 0.2" · "median depth < 10"
    이므로 `p50` 을 읽어야 하고, 코드의 경고 로직도 같은 값을 쓴다. 스칼라로
    가정하면 값이 정상인데도 "계산 안 됨" 으로 보인다 - 재실행에서 실제로 그랬다.
    """
    q = q or {}
    cov = q.get("coverage") or {}
    dep = q.get("depth") or {}
    return {
        "usable_hits": q.get("usable_hits"),
        "median_coverage": cov.get("p50") if isinstance(cov, dict) else cov,
        "median_depth": dep.get("p50") if isinstance(dep, dict) else dep,
        "full_length_fraction": q.get("full_length_fraction"),
    }


def evaluate_acceptance(entry: dict) -> dict:
    """계측 acceptance 6 항목. **과학 PASS 가 아니다.**

    어떤 타겟이 실제로 `usable_hits < 10` 이면 pilot 실패가 아니라 진짜
    `MSA_INSUFFICIENT_DEPTH` 관측이다. 5 번은 "값이 계산됐는가" 만 본다.

    저장된 산출물에서도 다시 계산할 수 있어야 한다 - 실행 중이던 프로세스가 옛
    코드를 쓰고 있을 때 MSA 재실행 없이 판정을 고치려면 그 경로가 필요하다.
    """
    m = quality_medians(entry.get("msa_quality"))
    qc = entry.get("query_consistent") or {}
    checks = {
        "1_endpoint_ok": entry.get("endpoint_status") == "ok",
        "2_a3m_key_present_and_decoded": bool(entry.get("a3m_key_present"))
                                         and entry.get("decode_ok") is True,
        "3_decoded_non_empty": entry.get("a3m_bytes", 0) > 0
                               and not entry.get("a3m_empty", True),
        "4_query_consistent": bool(qc.get("id_match")) and bool(qc.get("length_match")),
        "5_quality_metrics_computed": all(
            isinstance(v, (int, float)) for v in m.values()),
        "6_frozen_rule_applied": entry.get("classification") in {
            "OK", "MSA_INSUFFICIENT_DEPTH", "MSA_INFEASIBLE"},
    }
    return {
        "quality_medians": m, "acceptance": checks,
        "acceptance_pass": all(checks.values()),
        "acceptance_note": ("계측 판정이다. scientific PASS 가 아니다. "
                            "usable_hits < 10 은 정상적인 feasibility 관측이며 "
                            "acceptance 실패가 아니다."),
    }


def print_table(rows: list[dict]) -> str:
    """3-target 결과표와 full-MSA 판정. 판정은 계측 기준이다."""
    def f(v, fmt="{:.3f}"):
        return fmt.format(v) if isinstance(v, (int, float)) else "-"

    print(f"{'타겟':10s}{'aa':>5}{'wall(s)':>9}{'hits':>7}{'a3m B':>10}"
          f"{'usable':>8}{'cover':>8}{'depth':>8}{'full_len':>9}  "
          f"{'판정':<24}계측")
    for e in rows:
        m = e.get("quality_medians") or quality_medians(e.get("msa_quality"))
        print(f"  {e['domain']:8s}{e.get('length', 0):>5}"
              f"{e.get('wall_seconds', 0):>9}{str(e.get('hit_count', '-')):>7}"
              f"{e.get('a3m_bytes', 0):>10}{f(m.get('usable_hits'), '{:.0f}'):>8}"
              f"{f(m.get('median_coverage')):>8}{f(m.get('median_depth'), '{:.1f}'):>8}"
              f"{f(m.get('full_length_fraction')):>9}  "
              f"{e.get('classification', '?'):<24}"
              f"{'PASS' if e.get('acceptance_pass') else 'FAIL'}")
        if not e.get("acceptance_pass"):
            bad = [k for k, v in (e.get("acceptance") or {}).items() if not v]
            print(f"      계측 실패 항목: {bad}")
        w = (e.get("msa_quality") or {}).get("warnings") or []
        if w:
            print(f"      warnings: {w}")
    n = sum(1 for e in rows if e.get("acceptance_pass"))
    verdict = "GO" if rows and n == len(rows) else "BLOCK"
    print(f"\n계측 acceptance {n}/{len(rows)} · full MSA 24 타겟 = {verdict}")
    print("  (계측 판정이다. usable_hits < 10 은 정상 feasibility 관측이며 "
          "acceptance 실패가 아니다.)")
    return verdict


def reevaluate(path: Path) -> int:
    """저장된 산출물에서 acceptance 와 표를 다시 낸다. MSA 를 다시 돌리지 않는다."""
    d = json.loads(path.read_text(encoding="utf-8"))
    rows = d.get("targets") or d.get("results") or []
    for e in rows:
        e.update(evaluate_acceptance(e))
    d["targets"] = rows
    d["instrumentation_pass"] = sum(1 for e in rows if e["acceptance_pass"])
    d["instrumentation_total"] = len(rows)
    d["full_msa_verdict"] = print_table(rows)
    d["reevaluated_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    d["reevaluated_why"] = ("coverage/depth 는 백분위 dict 이므로 p50 을 읽어야 "
                            "한다. 실행 중 프로세스가 스칼라로 검사해 5 번을 FAIL "
                            "로 적었다. MSA 는 다시 돌리지 않았다 - 저장된 "
                            "msa_quality 에서 재계산했다.")
    path.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nwrote {path}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=None)
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--reevaluate", default=None,
                    help="저장된 산출물에서 acceptance 를 다시 계산한다 (MSA 재실행 없음)")
    args = ap.parse_args()

    if args.reevaluate:
        return reevaluate(Path(args.reevaluate))

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
            entry["a3m_key_present"] = bool(a3m_b64)
            if a3m_b64:
                # decode 실패를 endpoint 실패와 섞지 않는다. 전자는 파싱 문제고
                # 후자는 전송 문제다. 하나로 합치면 다시 추적해야 한다.
                try:
                    a3m = decode_a3m_gz_b64(str(a3m_b64))
                    entry["decode_ok"] = True
                except Exception as exc:
                    a3m = ""
                    entry["decode_ok"] = False
                    entry["decode_error"] = f"{type(exc).__name__}: {exc}"[:200]
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
            # 서버가 우리가 보낸 질의를 그대로 다뤘는지. 길이나 id 가 어긋나면
            # 이후 보존도 마스크가 다른 서열에 붙는다 - 조용히 넘어가면 안 된다.
            entry["query_consistent"] = {
                "sent_id": domain, "sent_length": len(seq),
                "returned_id": out.get("query_id"),
                "returned_length": out.get("query_length"),
                "id_match": str(out.get("query_id") or "").strip() in ("", domain),
                "length_match": (out.get("query_length") is None
                                 or int(out["query_length"]) == len(seq)),
            }
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
        # 계측 acceptance. 공용 함수를 쓴다 - reevaluate 와 같은 판정이어야 한다.
        entry.update(evaluate_acceptance(entry))
        checks = entry["acceptance"]
        print(f"    {entry['wall_seconds']}s · {entry['endpoint_status']} · "
              f"{entry['classification']} · 계측 "
              f"{'PASS' if entry['acceptance_pass'] else 'FAIL ' + str([k for k, v in checks.items() if not v])}",
              flush=True)
        rows.append(entry)

    print()
    verdict = print_table(rows)

    report = {
        "purpose": "MSA operational pilot. 운영 가능성만 본다.",
        "acceptance_scope": ("corrected transport/parser path 의 end-to-end 검증과 "
                             "MSA quality 4 값의 실제 계측. scientific threshold "
                             "재평가가 아니다."),
        "acceptance_criteria": [
            "1 endpoint_status = ok",
            "2 a3m_gz_b64 존재 + decode 성공",
            "3 decoded A3M non-empty",
            "4 query_id / query_length 일치",
            "5 usable_hits · coverage · depth · full_length_fraction 이 실제 숫자로 계산됨",
            "6 frozen §8 규칙이 그대로 적용됨",
        ],
        "acceptance_is_not": ("세 타겟이 모두 scientific PASS 일 필요는 없다. "
                              "usable_hits < 10 은 frozen protocol 에 따른 정상 "
                              "feasibility 결과다."),
        "forbidden_after_this_run": ["threshold 변경", "target selection rule 변경",
                                     "tier 변경", "candidate count 변경"],
        "instrumentation_pass": sum(1 for e in rows if e["acceptance_pass"]),
        "instrumentation_total": len(rows),
        "full_msa_verdict": verdict,
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
