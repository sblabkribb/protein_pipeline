#!/usr/bin/env python3
"""측정된 게이트 0 yield 위에서 예산 배분 정책을 비교한다.

RAPID 가 주장하려는 것은 "같은 AF2 예산에서 더 많은 통과 후보" 다. 이 스크립트는
그 주장을 **합성 데이터가 아니라 실제로 측정한 백본별 yield 위에서** 시뮬레이션
한다.

읽는 것
-------
`backbones/backbone_labels.csv` 의 백본별 통과율. 157 개 백본, 타겟/소스/서열 수가
함께 들어 있다. 이 값이 시뮬레이션의 `truth` 가 된다.

이 설계가 인정하는 한계
-----------------------
1. 관측된 yield 를 truth 로 쓰면 추정 오차가 사라진다. 모든 정책이 같은 truth 를
   보므로 **정책 간 비교** 로는 공정하지만, 절대 수치를 실제 실행의 기대값으로
   읽으면 안 된다.
2. 백본당 서열 수가 다르다(대부분 40, 일부 그 이하). yield 의 정밀도가 백본마다
   다르다는 뜻이고, 이 시뮬레이션은 그 차이를 무시한다.
3. 대리모형은 게이트 0 의 실측 타겟 수준 AUC 로 **합성** 한다. 실제 인코더 점수를
   쓰면 같은 데이터로 대리모형을 학습하고 평가하게 되어 누출이 생긴다. 합성
   대리모형은 그 누출을 원천적으로 피하는 대신, 그 AUC 가 이 데이터에서 실제로
   달성 가능하다는 가정을 진다.
4. 온도 축은 아직 없다. 이 라벨은 전부 T=0.1 에서 생성되었다. 온도별 arm 은
   AF2 온도 실험 결과가 나온 뒤에 붙인다.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "transcoder"))
sys.path.insert(0, str(PROJECT_ROOT / "pipeline-mcp" / "src"))

from rapid_sr.allocation import Arm, clustered_policy_bootstrap, simulate  # noqa: E402

LABELS = PROJECT_ROOT / "public_data" / "benchmark" / "gate0" / "backbones" / "backbone_labels.csv"
PDB_DIR = PROJECT_ROOT / "public_data" / "benchmark" / "gate0" / "backbones" / "pdb"
DEFAULT_OUT = PROJECT_ROOT / "public_data" / "benchmark" / "gate0" / "allocation_simulation.json"

#: 게이트 0 타겟 수준 AUC. gate0_target_level.json 의 C_raw_mpnn_encoder.
MEASURED_GATE0_AUC = 0.7247


def _pdb_length(path: Path) -> int | None:
    if not path.exists():
        return None
    seen = set()
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.startswith("ATOM") and line[12:16].strip() == "CA":
            seen.add(line[21:27])
    return len(seen) or None


def _af2_seconds(length_aa: int | None) -> float | None:
    """레지스트리의 길이 적합으로 이 백본 1 폴드 비용을 낸다."""
    from pipeline_mcp.model_routing import load_registry

    cost = load_registry().models["colabfold"].cost
    return cost.seconds_for(length_aa=length_aa)


def build_arms(rows, *, yield_field: str) -> tuple[list[Arm], dict[str, float]]:
    arms: list[Arm] = []
    truth: dict[str, float] = {}
    skipped: list[str] = []
    for row in rows:
        raw = row.get(yield_field)
        if raw in (None, "", "None"):
            # 라벨이 없는 백본을 0 으로 채우면 "나쁘다" 는 정보를 지어내는 것이다.
            skipped.append(row["backbone_key"])
            continue
        pdb = PDB_DIR / row["pdb_file"]
        arm = Arm(
            target_id=row["target_id"],
            backbone_id=f"{row['backbone_source']}:{row['backbone_id']}",
            condition="T0.1",
            cost_seconds=_af2_seconds(_pdb_length(pdb)),
        )
        arms.append(arm)
        truth[arm.key] = float(raw)
    if skipped:
        print(f"라벨 없는 백본 {len(skipped)} 개 제외 (0 으로 채우지 않는다)", file=sys.stderr)
    return arms, truth


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--labels", type=Path, default=LABELS)
    parser.add_argument("--yield-field", default="joint_pass_yield",
                        choices=["joint_pass_yield", "af2_structural_pass_yield",
                                 "soluprot_pass_yield"])
    parser.add_argument("--budgets", default="50,120,240,480")
    parser.add_argument("--batch-size", type=int, default=0,
                        help="0 이면 예산의 1/10 을 쓴다. 배치가 없으면 적응할 기회도 없다.")
    parser.add_argument("--repeats", type=int, default=200)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--surrogate-auc", type=float, default=MEASURED_GATE0_AUC)
    parser.add_argument("--surrogate-oof", type=Path, default=None,
                        help="13_gate0_target_level.py --export-oof 가 만든 파일. 주면 합성 "
                             "대리모형 대신 실제 out-of-fold 인코더 예측을 쓴다.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--clustered-boot", type=int, default=200,
                        help="타겟 클러스터 부트스트랩 횟수. 0 이면 건너뛴다.")
    args = parser.parse_args(argv)

    rows = list(csv.DictReader(args.labels.open(encoding="utf-8")))
    arms, truth = build_arms(rows, yield_field=args.yield_field)
    if not arms:
        print("사용할 수 있는 백본이 없다", file=sys.stderr)
        return 1

    values = list(truth.values())
    print(f"백본 {len(arms)} 개 · 타겟 {len({a.target_id for a in arms})} 개")
    print(f"{args.yield_field}: 평균 {statistics.fmean(values):.3f} "
          f"중앙값 {statistics.median(values):.3f} "
          f"0 인 백본 {sum(1 for v in values if v == 0)} 개 "
          f"1 인 백본 {sum(1 for v in values if v == 1)} 개")
    known_cost = [a.cost_seconds for a in arms if a.cost_seconds is not None]
    print(f"AF2 비용 추정 가능 {len(known_cost)}/{len(arms)} · "
          f"중앙값 {statistics.median(known_cost):.0f}s" if known_cost else "AF2 비용 미상")

    surrogate_scores = None
    surrogate_source = f"synthetic at AUC {args.surrogate_auc}"
    if args.surrogate_oof:
        payload = json.loads(args.surrogate_oof.read_text(encoding="utf-8"))
        by_target = payload["scores"]
        missing = sorted({a.target_id for a in arms} - set(by_target))
        if missing:
            # 점수가 없는 타겟을 중앙값으로 채우면 없는 정보를 지어내는 것이다.
            print(f"OOF 점수 없는 타겟 {len(missing)} 개의 arm 을 제외한다", file=sys.stderr)
            arms = [a for a in arms if a.target_id in by_target]
            truth = {a.key: truth[a.key] for a in arms}
        surrogate_scores = {a.key: float(by_target[a.target_id]) for a in arms}
        surrogate_source = (
            f"{args.surrogate_oof.name} · out-of-fold 인코더 예측 "
            f"(보고된 AUC {payload.get('auc')}, {payload.get('n_repeats')} 반복 평균)"
        )
        print(f"대리모형: {surrogate_source}")

    out = {
        "labels": str(args.labels.relative_to(PROJECT_ROOT)),
        "surrogate_source": surrogate_source,
        "yield_field": args.yield_field,
        "n_arms": len(arms),
        "n_targets": len({a.target_id for a in arms}),
        "surrogate_auc": args.surrogate_auc,
        "surrogate_note": (
            "대리모형은 게이트 0 실측 타겟 수준 AUC 로 합성한 것이다. 실제 인코더 "
            "점수를 쓰면 같은 데이터로 학습·평가하게 되어 누출이 생긴다."
        ),
        "variance_note": (
            "yield 분포가 양극단이다 (0 인 백본 58 개, 1 인 백본 55 개). yield 가 정확히 "
            "1.0 인 백본을 한 번 잡으면 이후 모든 뽑기가 결정적으로 성공하므로, 반복 간 "
            "분산이 거의 0 이 되고 CI 가 실제보다 좁아진다. 절대 수치가 아니라 정책 간 "
            "순서를 읽어야 한다."
        ),
        "aggregation_baseline_note": (
            "--surrogate-oof 를 쓰면 대리모형이 이미 타겟 하나당 점수 하나이므로 타겟 집계가 "
            "항등이 되고, static_topk_target_agg 는 static_topk_measured_auc 와 같아진다. "
            "그 둘이 같은 값으로 나오는 것은 버그가 아니라 이 대리모형이 이미 타겟 수준이라는 뜻이다. "
            "합성 대리모형(--surrogate-auc)은 arm 수준 잡음을 갖고 있어 두 대조군이 갈린다."
        ),
        "baseline_note": (
            "static 대조군은 두 가지를 함께 돌린다. arm 수준 원점수를 쓰는 것과, 적응 "
            "정책의 사전분포와 같은 타겟 수준 집계를 쓰는 것이다. 후자와의 차이가 순수한 "
            "온라인 갱신의 이득이고, 두 차이의 간격이 타겟 집계 전처리의 몫이다. "
            "두 대조군 모두 k 를 사후적으로 가장 좋았던 값으로 고른다 - 대조군에 주는 이점이다."
        ),
        "truth_note": (
            "관측된 yield 를 truth 로 쓴다. 정책 간 비교에는 공정하지만 절대 수치를 "
            "실제 실행의 기대값으로 읽으면 안 된다."
        ),
        "repeats": args.repeats,
        "seed": args.seed,
        "budgets": {},
    }

    for budget in [int(b) for b in args.budgets.split(",") if b.strip()]:
        batch = args.batch_size or max(1, budget // 10)
        result = simulate(
            arms, truth=truth, budget=budget, batch_size=batch,
            seed=args.seed, repeats=args.repeats,
            surrogate_auc=args.surrogate_auc,
            measured_surrogate_scores=surrogate_scores,
        )
        out["budgets"][str(budget)] = {"batch_size": batch, "policies": result}

        print(f"\n예산 {budget} (배치 {batch})")
        headline = result["rapid_adaptive"]
        for name in sorted(result, key=lambda n: -result[n]["successes"]):
            entry = result[name]
            bits = [f"{entry['successes']:8.2f}"]
            if "vs_uniform" in entry:
                low, high = entry["vs_uniform_ci95"]
                bits.append(f"vs uniform {entry['vs_uniform']:+8.2f} [{low:+.2f}, {high:+.2f}]")
            if "chosen_k" in entry:
                bits.append(f"k={entry['chosen_k']} (사후 선택)")
            print(f"  {name:34s} " + "  ".join(bits))
        for label, caption in (("vs_static_best", "적응 vs static(arm 수준 점수)"),
                               ("vs_static_target_agg", "적응 vs static(같은 타겟 집계)")):
            if label not in headline:
                continue
            low, high = headline[f"{label}_ci95"]
            verdict = "우세" if low > 0 else ("열세" if high < 0 else "구별 안 됨")
            print(f"  → {caption}: {headline[label]:+.2f} "
                  f"[{low:+.2f}, {high:+.2f}] — {verdict}")

    if args.clustered_boot:
        # 반복 재실행 CI 는 이 데이터에서 거의 0 폭이다 (yield 가 0/1 에 몰려 있어
        # 라벨 뽑기에 무작위성이 없다). 실제로 물어야 할 것은 "다른 타겟에서도
        # 성립하는가" 이므로 타겟을 클러스터로 재표집한다.
        print(f"\n타겟 클러스터 부트스트랩 ({args.clustered_boot} 회)")
        out["clustered_bootstrap"] = {}
        for budget in [int(b) for b in args.budgets.split(",") if b.strip()]:
            batch = args.batch_size or max(1, budget // 10)
            block = clustered_policy_bootstrap(
                arms, truth=truth, budget=budget, batch_size=batch,
                n_boot=args.clustered_boot, seed=args.seed,
                surrogate_auc=args.surrogate_auc,
                measured_surrogate_scores=surrogate_scores,
            )
            # 재표집 내역은 크고 재현 가능하므로 아티팩트에 넣지 않는다.
            block.pop("resampled_target_counts", None)
            out["clustered_bootstrap"][str(budget)] = block
            low, high = block["vs_static_best_ci95"]
            verdict = "우세" if low > 0 else ("열세" if high < 0 else "구별 안 됨")
            print(f"  예산 {budget:4d}: 적응 {block['rapid_adaptive']:7.2f} "
                  f"vs static {block['reference_successes']:7.2f} → "
                  f"{block['vs_static_best']:+7.2f} [{low:+.2f}, {high:+.2f}] — {verdict}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
