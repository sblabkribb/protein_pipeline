#!/usr/bin/env python3
"""query → original → staged → RFD3 backbone → ProteinMPNN fixed position 매핑.

폴딩하지 않는다. MSA 를 돌리지 않는다. 이 단계의 목적은 **매핑이 성립하는지**를
확인하는 것뿐이다.

왜 이것을 먼저 하는가
---------------------
보존도 마스크는 원본 타겟의 query 번호로 계산되고, ProteinMPNN 은 backbone 의
잔기 번호로 fixed position 을 받는다. 그 사이에 번호가 세 번 바뀐다.

  1. 원본 CATH 파일의 resseq 는 1 부터 시작하지 않는다
     (실측: 4..187 · 513..657 · -2..310 · 492..865 · 25..249)
  2. 전처리가 음수/0 resseq 를 버리고 1 부터 재번호한다
     (실측: 1j0tA00 앞 1 잔기, 1y8aA02 앞 3 잔기 소실)
  3. altLoc 이 있으면 CA **행 수**와 **잔기 수**가 다르다
     (실측: 1y8aA02 321 행 / 310 잔기, 7o1zA01 236 / 225)

셋 중 하나만 틀려도 엉뚱한 잔기가 고정되는데, 실행은 성공하고 서열도 그럴듯하게
나온다. 그래서 조용한 실패를 금지하고 전부 hard fail 로 만든다.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import time

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[2]
BASE = PROJECT_ROOT / "public_data" / "benchmark" / "gate0"
STAGED = BASE / "holdout_targets_pdb"
OUTPUTS = pathlib.Path("/opt/protein_pipeline/outputs")

AA3 = {"ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C", "GLN": "Q",
       "GLU": "E", "GLY": "G", "HIS": "H", "ILE": "I", "LEU": "L", "LYS": "K",
       "MET": "M", "PHE": "F", "PRO": "P", "SER": "S", "THR": "T", "TRP": "W",
       "TYR": "Y", "VAL": "V"}


class MappingError(RuntimeError):
    """조용히 넘어가지 않는다. 매핑이 성립하지 않으면 실행을 멈춘다."""


def residues(path: pathlib.Path, *, first_model: bool = True) -> list[dict]:
    """CA 잔기 목록. altLoc 은 첫 conformer 만 - **행이 아니라 잔기를 센다.**"""
    out, seen = [], set()
    for line in path.read_text(errors="replace").splitlines():
        if first_model and line.startswith("ENDMDL"):
            break
        if not line.startswith("ATOM") or line[12:16].strip() != "CA":
            continue
        alt = line[16]
        if alt not in (" ", "A"):
            continue
        key = (line[21], line[22:26], line[26])
        if key in seen:          # 같은 잔기가 두 번 나오면 첫 것만
            continue
        seen.add(key)
        out.append({"chain": line[21], "resseq": int(line[22:26]),
                    "icode": line[26].strip(), "aa": AA3.get(line[17:20].strip(), "X")})
    return out


def map_target(domain: str, original_pdb: str) -> dict:
    orig = residues(pathlib.Path(original_pdb))
    staged_path = STAGED / f"{domain}.pdb"
    if not staged_path.exists():
        raise MappingError(f"{domain}: staged PDB 가 없다")
    staged = residues(staged_path)
    design_dir = OUTPUTS / f"calib_{domain}_rfd3" / "rfd3" / "designs"
    backbones = sorted(design_dir.glob("*.pdb")) if design_dir.exists() else []
    if not backbones:
        raise MappingError(f"{domain}: backbone 이 없다")
    bb = residues(backbones[0])

    oseq = "".join(r["aa"] for r in orig)
    sseq = "".join(r["aa"] for r in staged)
    bseq = "".join(r["aa"] for r in bb)

    # --- hard fail 1: staged 가 원본의 연속 부분열이 아니다 -------------------
    if sseq not in oseq:
        raise MappingError(
            f"{domain}: staged 서열이 원본의 연속 부분열이 아니다 - 중간 결손이 "
            f"있으면 위치 대응을 정의할 수 없다")
    offset = oseq.index(sseq)
    if oseq.count(sseq) > 1:
        raise MappingError(
            f"{domain}: staged 서열이 원본에 {oseq.count(sseq)} 번 나온다 - "
            f"대응이 모호하다")

    # --- hard fail 2: backbone 이 staged 와 다르다 ---------------------------
    if bseq != sseq:
        raise MappingError(f"{domain}: backbone 서열이 staged 와 다르다")
    if [r["resseq"] for r in bb] != [r["resseq"] for r in staged]:
        raise MappingError(f"{domain}: backbone 잔기 번호가 staged 와 다르다")

    # --- hard fail 3: 사슬 불일치 -------------------------------------------
    chains = {r["chain"] for r in staged} | {r["chain"] for r in bb}
    if len(chains) != 1:
        raise MappingError(f"{domain}: 사슬이 하나가 아니다 {sorted(chains)}")

    # --- 매핑 표 -------------------------------------------------------------
    # query 는 원본 첫 모델 서열이라고 본다. 실제 MSA query 가 다르면 §identity
    # 검사에서 걸린다.
    rows = []
    for i, s in enumerate(staged):
        o = orig[offset + i]
        b = bb[i]
        if o["aa"] != s["aa"] or s["aa"] != b["aa"]:
            raise MappingError(
                f"{domain}: 위치 {i+1} 아미노산 불일치 "
                f"orig={o['aa']} staged={s['aa']} backbone={b['aa']}")
        rows.append({
            "query_pos": offset + i + 1,          # 1-based, 원본 서열 기준
            "original_chain": o["chain"], "original_resseq": o["resseq"],
            "original_icode": o["icode"],
            "backbone_chain": b["chain"], "backbone_resseq": b["resseq"],
            "aa": s["aa"],
            "mapping_source": "contiguous_subsequence_offset",
            "identity_ok": True,
        })
    return {
        "domain": domain,
        "n_original_residues": len(orig),
        "n_staged_residues": len(staged),
        "n_backbone_residues": len(bb),
        "leading_residues_dropped": offset,
        "original_resseq_range": [orig[0]["resseq"], orig[-1]["resseq"]],
        "backbone_resseq_range": [bb[0]["resseq"], bb[-1]["resseq"]],
        "resseq_is_preserved": [r["original_resseq"] for r in rows]
                               == [r["backbone_resseq"] for r in rows],
        "n_mapped": len(rows),
        "mapping_sample": rows[:3] + rows[-2:],
        "backbone_file": backbones[0].name,
    }


def fixed_positions_for(mapping: dict, query_positions: list[int]) -> dict:
    """query 위치 → ProteinMPNN fixed position (backbone resseq)."""
    by_query = {r["query_pos"]: r for r in mapping["_rows"]}
    out, missing = [], []
    lo, hi = mapping["backbone_resseq_range"]
    for q in query_positions:
        r = by_query.get(q)
        if r is None:
            missing.append(q)          # 전처리에서 사라진 위치
            continue
        if not lo <= r["backbone_resseq"] <= hi:
            raise MappingError(f"fixed position {r['backbone_resseq']} 가 backbone "
                               f"범위 {lo}..{hi} 밖이다")
        out.append(r["backbone_resseq"])
    if missing:
        # 조용히 버리지 않는다.
        raise MappingError(
            f"query 위치 {missing} 가 backbone 에 대응되지 않는다 "
            f"(전처리에서 제거된 잔기). 마스크를 조용히 줄이지 않는다.")
    return {"fixed_positions": sorted(out), "n": len(out)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(BASE / "position_mapping_spike.json"))
    args = ap.parse_args()

    spec = json.loads((BASE / "calibration_targets.json").read_text(encoding="utf-8"))
    results, failures = {}, {}
    for row in sorted(spec["selected"], key=lambda r: r["domain"]):
        t = row["domain"]
        try:
            m = map_target(t, row["pdb"])
            rows_full = None
            results[t] = m
        except MappingError as exc:
            failures[t] = str(exc)
    print(f"{'타겟':10s}{'원본':>6}{'staged':>7}{'backbone':>9}{'앞소실':>7}"
          f"{'resseq 보존':>11}")
    for t, m in results.items():
        print(f"  {t:8s}{m['n_original_residues']:>6}{m['n_staged_residues']:>7}"
              f"{m['n_backbone_residues']:>9}{m['leading_residues_dropped']:>7}"
              f"{str(m['resseq_is_preserved']):>11}")
    for t, why in failures.items():
        print(f"  {t:8s} 실패: {why[:70]}")
    n_preserved = sum(1 for m in results.values() if m["resseq_is_preserved"])
    print(f"\n매핑 성립 {len(results)}/{len(spec['selected'])} · "
          f"원본 resseq 를 그대로 써도 되는 타겟 {n_preserved}/{len(results)}")

    report = {
        "purpose": "query → original → staged → backbone → fixed position 매핑 검증. "
                   "폴딩·MSA 없음.",
        "hard_fail_conditions": [
            "staged 가 원본의 연속 부분열이 아님 (중간 결손)",
            "부분열이 원본에 여러 번 나타남 (모호한 대응)",
            "backbone 서열/번호가 staged 와 다름",
            "사슬이 둘 이상",
            "위치별 아미노산 불일치",
            "query 위치가 backbone 에 대응되지 않음 (조용한 마스크 축소 금지)",
            "fixed position 이 backbone 잔기 번호 범위 밖",
        ],
        "why_resseq_cannot_be_used": "원본 resseq 범위가 1 부터 시작하지 않는다 "
                                     "(실측 4..187 · 513..657 · -2..310 · 492..865). "
                                     "전처리가 1 부터 재번호하므로 원본 resseq 를 "
                                     "그대로 쓰면 대부분의 타겟에서 어긋난다.",
        "why_ca_lines_cannot_be_counted": "altLoc 이 있으면 CA 행 수 != 잔기 수 "
                                          "(실측 1y8aA02 321/310 · 7o1zA01 236/225).",
        "n_targets_mapped": len(results),
        "n_targets_failed": len(failures),
        "targets": results,
        "failures": failures,
        "code_sha": subprocess.run(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT,
                                   capture_output=True, text=True).stdout.strip(),
        "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    pathlib.Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                      encoding="utf-8")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
