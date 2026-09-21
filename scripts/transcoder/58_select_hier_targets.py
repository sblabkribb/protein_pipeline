#!/usr/bin/env python3
"""계층형 배분 confirmatory 코호트의 표적 36 개를 결정적으로 고른다.

규칙은 `docs/specs/hierarchical-confirmatory-prespec.md` 에 동결한다. 이 파일은
그 규칙을 그대로 실행할 뿐이고 여기서 새 선택을 하지 않는다.

선정 규칙 (실행 전 고정)
------------------------
    후보     CATH pilot 77 표적 중 v2 다중생성원 캠페인과 **코호트 B**
             (11 표적 RFD3 예산 격자) 어느 쪽에도 쓰이지 않은 것
    길이     80 <= L <= 400  (v2 실측 범위 50-386 에 맞춘다. 2,360 aa 는 뺀다)
    비중복   같은 PDB 엔트리(앞 4 자)에서 두 도메인을 쓰지 않고, 쌍대 서열
             동일성 30% 이상인 쌍도 쓰지 않는다. 표적 클러스터 부트스트랩이
             표적을 독립 단위로 다루므로 이 조건이 없으면 클러스터 수가
             실제보다 부풀려진다. 충돌하면 도메인 ID 사전순 앞을 남긴다.
    층화     길이 사분위로 4 층, 각 층에서 9 개씩
    seed     20260921 (다른 동결 산출물과 같은 값)

코호트 A(67 표적 pLDDT 순위화) 와 겹치는 표적은 **허용한다.** 종점이 다르고
(joint-pass) 백본을 새로 생성하므로 같은 자료의 재분석이 아니다. 다만 ESM-2
표현이 같으므로 이 사실을 결과에 명시한다.

코호트 B 는 **허용하지 않는다.** 같은 종점(같은 예산에서의 joint-pass 확보량)
을 이미 그 표적에서 측정했으므로 unseen 이 아니다.
"""

from __future__ import annotations

import collections
import csv
import hashlib
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
CATH = ROOT / "data" / "benchmark" / "cath_pilot_dataset.csv"
V2 = ROOT / "public_data" / "benchmark" / "gate0" / "v2_multisource" / "candidates.json"
COHORT_B = ROOT / "public_data" / "benchmark" / "gate0" / "fewshot_jointpass_transfer.json"
OUT = ROOT / "public_data" / "benchmark" / "gate0" / "hier_confirmatory_targets.json"

N_TARGETS, N_STRATA, LEN_MIN, LEN_MAX, SEED = 36, 4, 80, 400, 20260921
MAX_IDENTITY = 0.30
#: MSA 러너가 요구하는 stratum 라벨. v2 동결 계획과 같은 경계를 쓴다.
STRATA_BOUNDS = ((150, "50-150"), (250, "150-250"), (10**9, "250-400"))
CATH_DIRS = ("cath_train", "cath_test", "cath_val")


def _pdb_path(domain: str) -> str:
    for d in CATH_DIRS:
        p = Path("/opt/protein_pipeline") / d / f"{domain}.pdb"
        if p.exists():
            return str(p)
    raise SystemExit(f"{domain} 의 PDB 를 cath_train/test/val 에서 못 찾았다")


def _stratum(n: int) -> str:
    for hi, label in STRATA_BOUNDS:
        if n <= hi:
            return label
    raise AssertionError


def _identity(a: str, b: str) -> float:
    n = min(len(a), len(b))
    if n == 0:
        return 0.0
    return sum(x == y for x, y in zip(a[:n], b[:n])) / max(len(a), len(b))


def _non_redundant(names: list[str], seq: dict[str, str]) -> list[str]:
    """같은 PDB 엔트리와 동일성 30% 이상 쌍을 거른다. 사전순 앞을 남긴다."""
    kept: list[str] = []
    for t in sorted(names):
        if any(t[:4] == k[:4] for k in kept):
            continue
        if any(_identity(seq[t], seq[k]) >= MAX_IDENTITY for k in kept
               if t in seq and k in seq):
            continue
        kept.append(t)
    return kept


def _cohort_b() -> set[str]:
    """코호트 B 표적을 산출물에서 직접 읽는다 - 목록을 손으로 적지 않는다."""
    out: set[str] = set()

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k == "per_target" and isinstance(v, dict):
                    out.update(v)
                walk(v)
        elif isinstance(o, list):
            for x in o:
                walk(x)

    walk(json.loads(COHORT_B.read_text(encoding="utf-8")))
    return out


def main() -> int:
    by = collections.defaultdict(list)
    for r in csv.DictReader(CATH.open(encoding="utf-8")):
        by[r["target"]].append(r)
    used = {c["target_id"] for c in json.loads(V2.read_text(encoding="utf-8"))}
    used |= _cohort_b()
    seq = {t: v[0]["sequence"] for t, v in by.items()}
    pool = {t: len(v[0]["sequence"]) for t, v in by.items()
            if t not in used and LEN_MIN <= len(v[0]["sequence"]) <= LEN_MAX}
    names = _non_redundant(sorted(pool), seq)
    print(f"  비중복 필터: {len(pool)} -> {len(names)}")
    print(f"CATH {len(by)} · v2 사용 {len(used)} · 길이필터 통과 {len(names)}")
    if len(names) < N_TARGETS:
        raise SystemExit(f"후보 {len(names)} < {N_TARGETS}")

    order = sorted(names, key=lambda t: (pool[t], t))
    strata = [order[i::N_STRATA] for i in range(N_STRATA)]   # 길이 사분위 근사
    rng = np.random.default_rng(SEED)
    per = N_TARGETS // N_STRATA
    picked = []
    for s in strata:
        picked += list(rng.choice(sorted(s), size=min(per, len(s)), replace=False))
    picked = sorted(set(picked))
    #: 층이 모자라 부족하면 남은 후보에서 결정적으로 채운다.
    if len(picked) < N_TARGETS:
        rest = [t for t in names if t not in picked]
        picked += list(rng.choice(sorted(rest), size=N_TARGETS - len(picked),
                                  replace=False))
    picked = sorted(picked)

    doc = {"purpose": "계층형 배분 confirmatory 코호트의 표적 목록. 실행 전 동결.",
           "prespec": "docs/specs/hierarchical-confirmatory-prespec.md",
           "rule": {"source_pool": "CATH pilot, v2 및 코호트 B 미사용", "len_min": LEN_MIN,
                    "len_max": LEN_MAX, "n_strata": N_STRATA, "seed": SEED,
                    "cohort_a_reuse": "허용. 종점과 백본이 다르다."},
           "n_candidates": len(names), "n_targets": len(picked),
           "max_identity": MAX_IDENTITY,
           #: MSA 러너(`50_full_msa.py`)가 읽는 항목 형식과 같게 낸다.
           #: superfamily 는 이 표적들에 대한 CATH 분류가 로컬에 없어 null 이다.
           #: 러너는 이 필드를 기록만 하고 판단에 쓰지 않는다. 비중복은
           #: superfamily 가 아니라 PDB 엔트리와 서열 동일성으로 보장한다.
           "targets": [{"domain": t, "length": pool[t], "pdb": _pdb_path(t),
                        "stratum": _stratum(pool[t]), "superfamily": None,
                        "role": "selected"} for t in picked]}
    text = json.dumps(doc, ensure_ascii=False, indent=1)
    OUT.write_text(text, encoding="utf-8")
    ls = sorted(pool[t] for t in picked)
    print(f"선정 {len(picked)} · 길이 {ls[0]}-{ls[-1]} (중앙 {ls[len(ls)//2]})")
    for i in range(0, len(picked), 6):
        print("   " + " ".join(f"{t}({pool[t]})" for t in picked[i:i + 6]))
    print(f"\n{OUT}\nsha256 {hashlib.sha256(text.encode()).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
