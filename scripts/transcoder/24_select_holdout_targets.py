#!/usr/bin/env python3
"""전향적 할당 검증을 위한 홀드아웃 타겟을 뽑고 freeze 한다.

왜 새로 뽑는가
--------------
기존 62 타겟 중 온도 패널이 쓰지 않은 42 개는 백본이 하나뿐인 것이 40 개다.
백본이 하나면 할당할 대상이 없어서 정책을 평가할 수 없다. 다중 백본 타겟은
개발이 모두 소진했다. 그래서 홀드아웃은 백본을 새로 생성해야 한다.

왜 이 풀이 누출 안전인가
------------------------
1. superfamily 겹침 0. 디스크의 CATH 코퍼스는 superfamily 당 도메인 하나로
   만들어져 있고, 후보는 게이트 0 의 62 타겟과 superfamily 가 겹치지 않는다.
2. 인코더 누출 없음. 게이트 0 대리모형의 특징은 저자 배포 가중치
   (ProteinMPNN v_48_020.pt) 로 뽑은 것이고 이 저장소가 학습시키지 않았다.
   cath_train/val/test 라는 이름은 앞선 연구의 split 이고 게이트 0 의 62 타겟은
   이미 세 split 에 걸쳐 있어서 지금은 기능하지 않는다. 그래서 셋을 합쳐 뽑는다.
3. 라벨을 볼 수 없음. 이 234 개는 게이트 0 을 한 번도 통과하지 않았다. 실측
   yield 가 존재하지 않으므로 그것을 보고 고를 방법 자체가 없다.

선정에 쓰는 정보
----------------
적격성(단일 사슬, 50-400 잔기)과 길이뿐이다. 게이트 0 사전분포 점수는 쓰지
않는다 - 그것은 정책이 런타임에 쓰는 입력이고, 그것으로 고르면 정책에 유리한
타겟만 고르게 된다.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import subprocess
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CATH_ROOT = Path("/opt/protein_pipeline")
SPLITS = ("cath_test", "cath_val", "cath_train")
DOMAIN_LIST = Path("/opt/ditto_scale/cache/cath-domain-list.txt")

#: 동결된 적격 기준. 온도 패널과 같은 값을 쓴다.
ELIGIBILITY = {"chains": 1, "min_length": 50, "max_length": 400}

#: 길이 층. AF2 비용이 길이의 거듭제곱으로 늘어나므로 층마다 같은 수를 뽑아
#: 비용과 난이도가 한쪽으로 쏠리지 않게 한다.
STRATA = (("50-150", 50, 150), ("150-250", 150, 250), ("250-400", 250, 401))


def superfamilies() -> dict[str, str]:
    out = {}
    for line in DOMAIN_LIST.read_text(errors="replace").splitlines():
        if line.startswith("#"):
            continue
        f = line.split()
        if len(f) >= 5:
            out[f[0]] = ".".join(f[1:5])
    return out


def chain_and_length(pdb_path: Path) -> tuple[int, int]:
    chains, residues = set(), set()
    for line in pdb_path.read_text(errors="replace").splitlines():
        if line.startswith("ATOM") and line[12:16].strip() == "CA":
            chains.add(line[21])
            residues.add((line[21], line[22:27]))
    return len(chains), len(residues)


def eligible(used_superfamilies: set[str], sf: dict[str, str],
             used_targets: set[str]) -> list[dict]:
    rows = []
    for split in SPLITS:
        for path in sorted((CATH_ROOT / split).glob("*.pdb")):
            name = path.stem
            if name in used_targets:
                continue
            if sf.get(name) in used_superfamilies:
                continue
            n_chains, length = chain_and_length(path)
            if n_chains != ELIGIBILITY["chains"]:
                continue
            if not ELIGIBILITY["min_length"] <= length <= ELIGIBILITY["max_length"]:
                continue
            rows.append({"domain": name, "split": split, "length": length,
                         "superfamily": sf.get(name, "unknown"), "pdb": str(path)})
    return rows


def stratum_of(length: int) -> str | None:
    for label, low, high in STRATA:
        if low <= length < high:
            return label
    return None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    base = PROJECT_ROOT / "public_data" / "benchmark" / "gate0"
    parser.add_argument("--labels", default=str(base / "backbones" / "backbone_labels.csv"))
    parser.add_argument("--per-stratum", type=int, default=4)
    parser.add_argument("--reserve", type=int, default=2,
                        help="층마다 예비를 함께 뽑는다. 백본 생성이 실패해도 "
                             "목록을 다시 뽑지 않고 예비를 순서대로 쓴다.")
    parser.add_argument("--seed", type=int, default=20260907)
    parser.add_argument("--out", default=str(base / "holdout_targets.json"))
    args = parser.parse_args(argv)

    used_targets = {r["target_id"] for r in
                    csv.DictReader(Path(args.labels).open(encoding="utf-8"))}
    sf = superfamilies()
    used_sf = {sf[t] for t in used_targets if t in sf}
    pool = eligible(used_sf, sf, used_targets)

    by_stratum: dict[str, list[dict]] = {label: [] for label, _, _ in STRATA}
    for row in pool:
        label = stratum_of(row["length"])
        if label:
            by_stratum[label].append(row)

    rng = random.Random(args.seed)
    selected, reserve = [], []
    for label, _, _ in STRATA:
        items = sorted(by_stratum[label], key=lambda r: r["domain"])
        need = args.per_stratum + args.reserve
        if len(items) < need:
            raise SystemExit(f"{label} 층 후보 {len(items)} < 필요 {need}")
        drawn = rng.sample(items, need)
        for row in drawn[:args.per_stratum]:
            selected.append({**row, "stratum": label, "role": "selected"})
        for rank, row in enumerate(drawn[args.per_stratum:], start=1):
            reserve.append({**row, "stratum": label, "role": "reserve",
                            "reserve_rank": rank})

    report = {
        "purpose": "적응적 할당 정책의 전향적 검증용 홀드아웃 타겟",
        "frozen_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "seed": args.seed,
        "code_sha": subprocess.run(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT,
                                   capture_output=True, text=True).stdout.strip(),
        "eligibility": dict(ELIGIBILITY),
        "strata": [{"label": a, "low": b, "high": c} for a, b, c in STRATA],
        "selection_inputs": ["적격성", "길이"],
        "selection_excluded_inputs": [
            "게이트 0 사전분포 점수 (정책의 런타임 입력이므로 선정에 쓰지 않는다)",
            "실측 yield (이 후보들은 게이트 0 을 통과한 적이 없어 존재하지 않는다)",
        ],
        "leakage_argument": {
            "superfamily_overlap_with_gate0": 0,
            "encoder": ("게이트 0 특징은 저자 배포 ProteinMPNN v_48_020.pt 로 "
                        "뽑았고 이 저장소가 학습시키지 않았다"),
            "readout_head": ("판독 헤드는 62 타겟에 적합되어 있다. 홀드아웃 타겟의 "
                             "라벨은 보지 않으므로 배포 조건과 같다."),
            "caveat": ("ProteinMPNN 자체는 저자가 PDB 로 사전학습했다. 이 CATH "
                       "도메인들도 그 안에 있을 것이다. 기존 62 타겟도 같은 조건이라 "
                       "홀드아웃에만 유리하게 작용하지 않지만, 논문에 적어야 한다."),
        },
        "pool": {
            "n_eligible": len(pool),
            "by_split": {s: sum(1 for r in pool if r["split"] == s) for s in SPLITS},
            "by_stratum": {k: len(v) for k, v in by_stratum.items()},
            "split_note": ("cath_train/val/test 는 앞선 연구의 split 이다. 게이트 0 의 "
                           "62 타겟이 이미 세 split 에 19/19/24 로 걸쳐 있어 지금은 "
                           "기능하지 않고, 인코더가 이 저장소에서 학습되지 않았으므로 "
                           "셋을 합쳐 뽑는다."),
        },
        "selected": selected,
        "reserve": reserve,
    }
    Path(args.out).write_text(json.dumps(report, indent=2, ensure_ascii=False),
                              encoding="utf-8")

    print(f"적격 풀 {len(pool)} · 층별 {report['pool']['by_stratum']}")
    print(f"\n선정 {len(selected)} (층당 {args.per_stratum}) · 예비 {len(reserve)}")
    for row in selected:
        print(f"  [{row['stratum']:>8s}] {row['domain']:10s} {row['length']:4d} 잔기 "
              f"· {row['split']:10s} · sf {row['superfamily']}")
    print("\n예비 (순서대로 사용)")
    for row in reserve:
        print(f"  [{row['stratum']:>8s}] #{row['reserve_rank']} {row['domain']:10s} "
              f"{row['length']:4d} 잔기")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
