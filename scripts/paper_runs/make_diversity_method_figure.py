#!/usr/bin/env python3
"""서열 다양성 3-arm 결과를 측정 방법이 읽히도록 다시 그린다.

원본 그림(`fig13_...`)은 상자그림 3 개에 "p=0.0039" 만 적혀 있어 두 가지가
보이지 않았다.

1. **p=0.0039 는 n=9 짝지은 Wilcoxon 의 수학적 하한**(2/2^9)이다. "9/9 가
   같은 방향" 이라는 것 외에 아무 정보가 없는데 정밀한 유의수준처럼 읽힌다.
2. **ensRandom(0.346) 이 ensSurr(0.310) 보다 높다.** 다양성 증가는 앙상블이
   만들고 대리모델 선별이 일부 되돌린다. single -> ensSurr 만 보면 두 변화가
   겹쳐 보인다.
3. pLDDT 가 **9/9 감소**했다(-1.42). 크기는 작지만 무작위가 아니다.

그래서 표적별 쌍 선을 전면에 놓고, 세 지표를 같은 그림에 둔다.
"""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import font_manager
from scipy.stats import wilcoxon

ROOT = Path(__file__).resolve().parents[2]
CSV = ROOT / "public_data" / "benchmark" / "results" / "structural_context_threeway_N9.csv"
OUT = ROOT / "figures" / "benchmark" / "fig_diversity_method_N9"

#: Noto CJK 는 .ttc 라 matplotlib 이 첫 face 만 읽는다. 그 이름이
#: "Noto Sans CJK JP" 이지만 한글 글리프를 포함한다. 경로로 등록한다.
_CJK = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
if Path(_CJK).exists():
    font_manager.fontManager.addfont(_CJK)
    KR = font_manager.FontProperties(fname=_CJK).get_name()
else:
    KR = "DejaVu Sans"

ARMS = [("single", "단일 backbone"), ("ensRandom", "앙상블·무작위"),
        ("ensSurr", "앙상블·대리모델")]
PANELS = [("div", "Top-20 서열 다양성", "1 − 평균 쌍대 동일성"),
          ("plddt", "선택 집합 pLDDT", "평균 pLDDT"),
          ("soluprot", "선택 집합 SoluProt", "평균 SoluProt")]
COL = ["#2D70B8", "#9CB3C9", "#2F8F5B"]


def main() -> int:
    rows = list(csv.DictReader(CSV.open(encoding="utf-8")))
    plt.rcParams.update({"font.family": KR, "font.size": 9})
    fig, axes = plt.subplots(1, 3, figsize=(11.5, 4.2))

    for ax, (base, title, ylab) in zip(axes, PANELS):
        vals = [np.array([float(r[f"{a}_{base}"]) for r in rows]) for a, _ in ARMS]
        for i, v in enumerate(vals):                      # 표적별 점
            ax.scatter(np.full(len(v), i) + np.random.default_rng(i).uniform(
                -.07, .07, len(v)), v, s=26, color=COL[i], zorder=3, alpha=.85,
                edgecolor="white", linewidth=.6)
        for k in range(len(rows)):                        # 표적별 쌍 선
            ax.plot(range(3), [v[k] for v in vals], color="#999", lw=.7,
                    alpha=.55, zorder=2)
        for i, v in enumerate(vals):                      # 평균
            ax.hlines(v.mean(), i - .26, i + .26, color="black", lw=2, zorder=4)
        d = vals[2] - vals[0]
        up = int((d > 0).sum())
        ax.set_title(f"{title}\nsingle→앙상블·대리모델 {d.mean():+.3f} · "
                     f"{up}/9 상승 · p={wilcoxon(d).pvalue:.4f}", fontsize=9.5)
        ax.set_xticks(range(3))
        ax.set_xticklabels([l for _, l in ARMS], fontsize=8.5)
        ax.set_ylabel(ylab)
        ax.grid(axis="y", alpha=.25, lw=.6)

    fig.suptitle("구조 컨텍스트 3-arm · 9 CATH 표적 · 표적당 pool 약 10,000 에서 "
                 "Top-20 선택\n"
                 "p=0.0039 는 n=9 짝지은 Wilcoxon 의 하한(2/2^9)이며 "
                 "\"9/9 동일 방향\" 이상을 뜻하지 않는다",
                 fontsize=10, fontweight="bold", y=1.0)
    fig.tight_layout(rect=(0, 0, 1, 0.90))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "pdf"):
        fig.savefig(f"{OUT}.{ext}", dpi=200, bbox_inches="tight")
    print(f"{OUT}.png / .pdf")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
