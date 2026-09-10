#!/usr/bin/env python3
"""Step 8 — target 쪽 매핑 검증. backbone 생성 전에 할 수 있는 전부를 한다.

동결 문서: `docs/specs/rapid-v2-multisource-validation-freeze.md` §9

동결 §9 의 사슬은 두 구간이다.

    query -> original -> staged        ← 이 스크립트 (backbone 불필요)
    staged -> backbone -> fixed pos    ← Step 9 이후, source 별

**MSA query 가 staged 서열이 된 뒤로 앞 구간이 짧아졌다.** 배포가
`normalize_structure_text` -> `strip_nonpositive_resseq` 를 거친 서열을 query 로
보내므로 (commit cb37ae2), query 위치와 staged 잔기는 1:1 이다. 그래서 "대응되지
않는 query 위치" 라는 실패 양식이 이 구간에서는 구조적으로 사라진다 - 그래도
검증한다. 사라졌다고 **가정**하는 것과 확인하는 것은 다르다.

남은 위험은 전부 뒤 구간에 있다. 그것은 backbone 이 생긴 뒤에만 볼 수 있다.

**하지 않는 것**: threshold 변경 · 타겟 선정 변경 · tier 변경 · 마스크 조용한
축소. 대응되지 않는 위치가 하나라도 있으면 그 타겟을 실패로 기록한다.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BASE = PROJECT_ROOT / "public_data" / "benchmark" / "gate0"
MSA_DIR = BASE / "msa"
STAGED_DIR = BASE / "staged_pdb"
OUT = BASE / "mapping_validation.json"
sys.path.insert(0, str(PROJECT_ROOT / "pipeline-mcp" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))


def _mod(name: str, filename: str):
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        name, Path(__file__).resolve().parent / filename)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def residues(pdb_text: str) -> list[dict]:
    """CA 잔기. altLoc 첫 conformer만 - **행이 아니라 잔기를 센다.**"""
    pilot = _mod("msa_pilot", "48_msa_pilot.py")
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
        out.append({"chain": line[21], "resseq": int(line[22:26]),
                    "icode": line[26].strip(),
                    "aa": pilot.AA3.get(line[17:20].strip(), "X")})
    return out


def a3m_query(path: Path) -> str:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or not lines[0].startswith(">"):
        raise ValueError(f"{path}: A3M 첫 줄이 헤더가 아니다")
    return lines[1]


def validate(row: dict, cons_cfg: dict) -> dict:
    from pipeline_mcp.bio.a3m import compute_conservation
    from pipeline_mcp.bio.pdb import normalize_structure_text, preprocess_pdb

    pilot = _mod("msa_pilot", "48_msa_pilot.py")
    domain = row["domain"]
    e: dict = {"cohort": row["cohort"], "domain": domain,
               "length_aa": row["length_aa"], "failures": []}

    def fail(msg: str) -> None:
        e["failures"].append(msg)

    raw_text = Path(row["pdb"]).read_text(errors="replace")
    # 배포와 같은 두 단계. ingest 정규화를 빼면 NMR 앙상블에서 서열이 배수가 된다.
    first_model = normalize_structure_text(raw_text)
    staged_text, _ = preprocess_pdb(
        first_model,
        strip_nonpositive_resseq=cons_cfg["strip_nonpositive_resseq"],
        renumber_resseq_from_1=cons_cfg["renumber_resseq_from_1"])
    STAGED_DIR.mkdir(parents=True, exist_ok=True)
    (STAGED_DIR / f"{domain}.pdb").write_text(staged_text, encoding="utf-8")

    raw_res, staged = residues(first_model), residues(staged_text)
    e["n_first_model_residues"] = len(raw_res)
    e["n_staged_residues"] = len(staged)
    e["residues_dropped_by_staging"] = len(raw_res) - len(staged)
    e["n_models_in_file"] = sum(1 for l in raw_text.splitlines()
                                if l.startswith("MODEL "))

    # --- 사슬 ---------------------------------------------------------------
    chains = sorted({r["chain"] for r in staged})
    e["chains"] = chains
    if len(chains) != 1:
        fail(f"사슬이 하나가 아니다 {chains}")

    # --- query 정체 ---------------------------------------------------------
    a3m_path = MSA_DIR / domain / "result.a3m"
    if not a3m_path.exists():
        fail("A3M 이 없다")
        return e
    q = a3m_query(a3m_path)
    sseq = "".join(r["aa"] for r in staged)
    e["a3m_query_length"] = len(q)
    e["query_equals_staged"] = (q == sseq)
    e["query_equals_query_sequence"] = (q == pilot.query_sequence(row["pdb"]))
    if not e["query_equals_staged"]:
        fail(f"A3M query 가 staged 서열과 다르다 ({len(q)} vs {len(sseq)})")
    if not e["query_equals_query_sequence"]:
        fail("A3M query 가 query_sequence() 와 다르다")

    # --- staged 가 원본의 유일한 연속 부분열인가 -----------------------------
    rseq = "".join(r["aa"] for r in raw_res)
    e["staged_is_contiguous_subsequence"] = sseq in rseq
    e["staged_occurrences_in_raw"] = rseq.count(sseq)
    if sseq not in rseq:
        fail("staged 가 첫 모델의 연속 부분열이 아니다 (중간 결손)")
    elif rseq.count(sseq) > 1:
        fail(f"staged 가 원본에 {rseq.count(sseq)} 번 나온다 - 대응이 모호하다")
    else:
        e["staging_offset"] = rseq.index(sseq)
        e["dropped_prefix"] = rseq[:e["staging_offset"]]

    # --- 위치별 아미노산 일치 -------------------------------------------------
    if e["query_equals_staged"]:
        mism = [i + 1 for i, (a, b) in enumerate(zip(q, sseq)) if a != b]
        e["n_aa_mismatch"] = len(mism)
        if mism:
            fail(f"위치별 아미노산 불일치 {len(mism)} 곳 (첫 {mism[:5]})")

    # --- 보존도 마스크 -> staged 잔기 번호 ------------------------------------
    c = compute_conservation(
        a3m_path.read_text(encoding="utf-8"),
        tiers=cons_cfg["conservation_tiers"],
        mode=cons_cfg["conservation_mode"], weights=None)
    e["conservation_query_length"] = c.query_length
    if c.query_length != len(staged):
        fail(f"보존도 query 길이 {c.query_length} != staged {len(staged)}")

    tiers, unmapped = {}, 0
    for tier, positions in c.fixed_positions_by_tier.items():
        mapped = []
        for pos in positions:
            if 1 <= pos <= len(staged):
                mapped.append(staged[pos - 1]["resseq"])
            else:
                unmapped += 1
        tiers[str(tier)] = {
            "n_query_positions": len(positions), "n_mapped": len(mapped),
            "staged_resseq_sha256": hashlib.sha256(
                json.dumps(mapped).encode()).hexdigest(),
            "staged_resseq_range": [min(mapped), max(mapped)] if mapped else None,
        }
    e["tiers"] = tiers
    # 조용한 축소 금지: 대응되지 않는 위치가 하나라도 있으면 실패다
    if unmapped:
        fail(f"보존도 위치 {unmapped} 개가 staged 로 대응되지 않는다 "
             f"- 마스크를 줄이면 성공처럼 보이는 실패가 된다")
    e["all_positions_mapped"] = unmapped == 0

    e["staged_pdb"] = str((STAGED_DIR / f"{domain}.pdb").relative_to(PROJECT_ROOT))
    e["staged_sha256"] = hashlib.sha256(
        (STAGED_DIR / f"{domain}.pdb").read_bytes()).hexdigest()
    e["passed"] = not e["failures"]
    return e


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()

    full = _mod("full_msa", "50_full_msa.py")
    pilot = _mod("msa_pilot", "48_msa_pilot.py")
    cfg = {**full.deployment_defaults(), **pilot.deployment_staging()}
    rows = full.targets()
    print(f"타겟 {len(rows)} · staging {pilot.deployment_staging()}")
    print(f"conservation {full.deployment_defaults()}\n")

    results = [validate(r, cfg) for r in rows]
    for e in results:
        mark = "PASS" if e["passed"] else "FAIL"
        drop = e.get("residues_dropped_by_staging", 0)
        print(f"  {e['cohort']:15s}{e['domain']:9s}{e['length_aa']:>5}aa "
              f"모델 {e.get('n_models_in_file', 0):>2} staged {e['n_staged_residues']:>4} "
              f"(-{drop}) tier "
              f"{[e['tiers'][t]['n_mapped'] for t in sorted(e.get('tiers', {}))]} "
              f"{mark}")
        for f in e["failures"]:
            print(f"      실패: {f}")

    n_pass = sum(1 for e in results if e["passed"])
    print(f"\n매핑 검증 {n_pass}/{len(results)} PASS")
    Path(args.out).write_text(json.dumps({
        "purpose": "Step 8 - target 쪽 매핑 검증. backbone 이전 구간만.",
        "chain_validated": "query -> first model -> staged",
        "chain_deferred": "staged -> backbone -> fixed positions (Step 9 이후, source 별)",
        "why_shorter": ("MSA query 가 staged 서열이 된 뒤로 query 위치와 staged "
                        "잔기가 1:1 이다 (commit cb37ae2). '대응되지 않는 query "
                        "위치' 실패 양식이 이 구간에서는 구조적으로 사라졌지만 "
                        "가정하지 않고 확인한다."),
        "staging": pilot.deployment_staging(),
        "conservation": full.deployment_defaults(),
        "not_done": ["threshold 변경", "타겟 선정 변경", "tier 변경",
                     "마스크 조용한 축소"],
        "n_pass": n_pass, "n_total": len(results),
        "targets": results,
        "code_sha": subprocess.run(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT,
                                   capture_output=True, text=True).stdout.strip(),
        "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {args.out}")
    return 0 if n_pass == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
