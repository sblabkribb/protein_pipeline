#!/usr/bin/env python3
"""연구노트 그림 3 - 코호트 C(v2) 의 예산 일치 비교를 생성원별로 그린다.

그림 2 의 패널 B 는 코호트 B(11 표적 RFD3 격자) 만 보여주고, 그 결과는
`33_v2_mpnn_baseline.py` 가 뒤집었다. 패널 B 를 다시 그릴 수는 없으므로
(원 생성 코드가 없다) 코호트 C 를 별도 그림으로 낸다.

읽는 법: 점은 쌍대 평균 차이, 수염은 표적 클러스터 부트스트랩 95% 구간이다.
구간이 0 선을 넘지 않으면 그 예산점에서 두 정책이 구별되었다는 뜻이다.
**생성원을 합치지 않는다** - 두 패널을 나란히 두어 방향 일치를 눈으로 본다.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

#: Noto CJK 는 .ttc 컬렉션이고 matplotlib 은 첫 face 만 읽는다. 그 face 이름이
#: "Noto Sans CJK JP" 이지만 한글 글리프를 포함하므로 그대로 쓴다. 이름으로
#: 지정하면 찾지 못하므로 파일 경로로 등록한다.
_CJK = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
if Path(_CJK).exists():
    font_manager.fontManager.addfont(_CJK)
    KR = font_manager.FontProperties(fname=_CJK).get_name()
else:
    KR = "DejaVu Sans"

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "public_data" / "benchmark" / "gate0" / "v2_mpnn_baseline.json"
OUT = ROOT / "figures" / "benchmark" / "fig3_v2_budget_matched"

BUDGETS = ["40", "60", "80", "100"]
#: 노트 표 3 과 같은 두 대비만 그린다. 보조 대비는 보충자료에 있다.
CONTRASTS = [("rf_probe-mpnn_score", "RF − ProteinMPNN 점수", "#1f4e79", "o"),
             ("rf_probe-random", "RF − 무작위", "#a03030", "s")]
PANELS = [("rfd3_pooled_cohorts", "RFD3 (15 unit)"),
          ("bioemu_pooled_cohorts", "BioEmu (14 unit)")]


def main() -> int:
    data = json.loads(SRC.read_text())["groups"]
    plt.rcParams.update({"font.family": KR, "font.size": 9,
                         "axes.linewidth": 0.8})
    fig, axes = plt.subplots(1, 2, figsize=(8.4, 3.5), sharey=True)

    for ax, (key, title) in zip(axes, PANELS):
        by_budget = data[key]["by_budget"]
        for ci, (contrast, label, colour, marker) in enumerate(CONTRASTS):
            offset = (ci - 0.5) * 0.30
            xs, ys, lo, hi = [], [], [], []
            for bi, B in enumerate(BUDGETS):
                d = by_budget[B]["paired_vs"][contrast]
                xs.append(bi + offset)
                ys.append(d["delta"])
                lo.append(d["delta"] - d["ci95"][0])
                hi.append(d["ci95"][1] - d["delta"])
            ax.errorbar(xs, ys, yerr=[lo, hi], fmt=marker, color=colour,
                        markersize=5, capsize=3, linewidth=1.2,
                        label=label if ax is axes[0] else None)
        ax.axhline(0, color="black", linewidth=0.9, linestyle="--", alpha=0.7)
        ax.set_xticks(range(len(BUDGETS)))
        ax.set_xticklabels([f"B={b}" for b in BUDGETS])
        ax.set_xlim(-0.6, len(BUDGETS) - 0.4)
        ax.set_title(title, fontsize=10)
        ax.set_xlabel("총 구조예측 예산")
        ax.grid(axis="y", alpha=0.25, linewidth=0.6)

    axes[0].set_ylabel("표적당 joint-pass 확보량 차이 (개)")
    axes[0].legend(loc="upper left", frameon=False, fontsize=8.5)
    fig.suptitle("코호트 C (v2, 29 target×source) · 생성원 미합산",
                 fontsize=10.5, y=0.99)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "pdf"):
        fig.savefig(f"{OUT}.{ext}", dpi=200 if ext == "png" else None,
                    bbox_inches="tight")
    print(f"{OUT}.png / .pdf")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
