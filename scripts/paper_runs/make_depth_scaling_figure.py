#!/usr/bin/env python3
"""깊이 확장 파일럿 결과를 그린다 (§4.4(c) 용).

`37_depth_scaling.py` 가 낸 `depth_scaling.json` 을 읽어 unit 별 D(18) → D(42)
를 잇는다. 주 비교가 unit 8 개짜리 쌍대 대비이므로 평균 막대보다 **표적별
쌍 선**이 정직하다 - 평균이 한 표적에 끌려가는지가 바로 보인다.

    D(d) = G(greedy_fill, d) − G(rf_only, d)
    G    = (Y_policy − Y_equal) / (Y_oracle − Y_equal)

greedy_thompson 은 `36_` 과 같은 정책이라 연속성 확인용으로 함께 그린다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import font_manager

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "public_data" / "benchmark" / "gate0" / "depth_scaling.json"
OUT = ROOT / "figures" / "benchmark" / "fig_depth_scaling"

_CJK = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
if Path(_CJK).exists():
    font_manager.fontManager.addfont(_CJK)
    KR = font_manager.FontProperties(fname=_CJK).get_name()
else:
    KR = "DejaVu Sans"

POLICIES = [("greedy_fill", "greedy_fill (주 비교)"),
            ("greedy_thompson", "greedy_thompson (보조)")]
BUDGET = "B80"


def main(path: str | None = None) -> int:
    src = Path(path) if path else SRC
    if not src.exists():
        raise SystemExit(f"{src} 가 없다. 37_ 를 먼저 돌린다.")
    doc = json.loads(src.read_text(encoding="utf-8"))
    per_unit = doc["per_unit"]

    plt.rcParams.update({"font.family": KR, "font.size": 9})
    fig, axes = plt.subplots(1, 2, figsize=(9.6, 4.3), sharey=True)

    for ax, (pol, title) in zip(axes, POLICIES):
        c = doc["contrasts"].get(f"{pol}|{BUDGET}")
        if not c or "per_unit_delta" not in c:
            ax.text(.5, .5, "자격 unit 부족", ha="center", transform=ax.transAxes)
            ax.set_title(title)
            continue
        units = c["units"]
        d18, d42 = [], []
        for t in units:
            bb = per_unit[t]["by_depth"]
            f = lambda dep, arm: bb[dep]["by_budget"][BUDGET[1:]][arm]
            for dep, box in (("18", d18), ("42", d42)):
                e = bb[dep]["by_budget"][BUDGET[1:]]
                den = e["oracle"] - e["equal_random"]
                box.append((e[pol] - e["equal_random"]) / den
                           - (e["rf_only"] - e["equal_random"]) / den)
        d18, d42 = np.array(d18), np.array(d42)
        for k, t in enumerate(units):                       # 표적별 선
            up = d42[k] > d18[k]
            ax.plot([0, 1], [d18[k], d42[k]], lw=1.0, alpha=.7, zorder=2,
                    color="#2F8F5B" if up else "#C0504D")
        ax.scatter(np.zeros(len(d18)), d18, s=30, color="#2D70B8", zorder=3,
                   edgecolor="white", linewidth=.6)
        ax.scatter(np.ones(len(d42)), d42, s=30, color="#2F8F5B", zorder=3,
                   edgecolor="white", linewidth=.6)
        for x, v in ((0, d18), (1, d42)):
            ax.hlines(v.mean(), x - .12, x + .12, color="black", lw=2.2, zorder=4)
        ax.axhline(0, color="#888", ls="--", lw=.9, zorder=1)
        ax.set_xticks([0, 1])
        ax.set_xticklabels(["깊이 18\n(집중 상한 35%)", "깊이 42\n(집중 상한 95%)"])
        ax.set_xlim(-.35, 1.35)
        ax.set_title(f"{title}\nΔ {c['delta']:+.3f} "
                     f"[{c['ci95'][0]:+.3f}, {c['ci95'][1]:+.3f}] · "
                     f"{int((d42 > d18).sum())}/{len(units)} 상승", fontsize=9.5)
        ax.grid(axis="y", alpha=.25, lw=.6)
    axes[0].set_ylabel("D = 여지 회수율 차이 (greedy − RF-only)")

    n = doc["contrasts"].get(f"greedy_fill|{BUDGET}", {}).get("n_units", 0)
    fig.suptitle(f"깊이 확장 파일럿 · RFD3 confirmatory · B=80 · 자격 unit {n}\n"
                 "초록 선은 깊이가 늘어 D 가 커진 표적, 붉은 선은 줄어든 표적",
                 fontsize=10, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.90))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "pdf"):
        fig.savefig(f"{OUT}.{ext}", dpi=200, bbox_inches="tight")
    print(f"{OUT}.png / .pdf")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else None))
