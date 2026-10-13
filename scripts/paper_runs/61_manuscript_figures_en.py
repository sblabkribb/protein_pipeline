#!/usr/bin/env python3
"""원고 그림을 영어로 통일하고 지적된 결함을 고쳐 다시 그린다.

왜 새로 쓰는가
--------------
연구노트 그림 2·3 은 **저장소에 생성 스크립트가 없었다.** 축 레이블·제목
문자열로 전체를 grep 해도 나오지 않는다. 그래서 원본에서 고칠 수 없었고,
`RF-MPNN` 의 마이너스가 두부(□)로 깨진 것도 그대로 남아 있었다. 여기서
자료로부터 다시 만들어 그 구멍을 닫는다.

고치는 결함
-----------
    fig3   주장과 그림이 어긋났다. 패널 제목은 single -> ensemble+surrogate
           만 말했는데 그림에서 가장 눈에 띄는 것은 **ensemble+random 이 더
           높다**는 것이었다. 두 대비를 모두 CI 와 함께 낸다.
    fig4   CI 가 없는 막대로 null 을 보여줘 "배분이 낫다" 로 읽혔다. 실제는
           +0.25 [-0.58, +1.25] 다. 대비 forest 를 따로 둔다.
    fig5   빨강·초록으로 방향을 인코딩해 색각이상자가 구분할 수 없었다.
    noteA  "주 결론은 A 와 C 를 중심으로" - 그림에 A·C 가 없다. 이전 판 잔재.
    noteB  패널 A 의 90% 가 공백이고 A 는 가로, B 는 세로였다.
    noteC  마이너스 글리프 깨짐.

색은 Okabe-Ito 팔레트를 쓴다. 색각이상에서도 구분된다.
"""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

ROOT = Path(__file__).resolve().parents[2]
#: 결과 디렉터리를 바꿔 끼울 수 있게 한다. 기본값은 저장소의 동결 경로다.
G = Path(os.environ.get("RAPID_GATE0", "")) if os.environ.get("RAPID_GATE0") \
    else ROOT / "public_data" / "benchmark" / "gate0"
RES = ROOT / "public_data" / "benchmark" / "results"
FIG = ROOT / "figures" / "submission"
FIG.mkdir(parents=True, exist_ok=True)

#: Okabe-Ito. 색각이상에서도 구분된다.
BLUE, ORANGE, GREEN, VERM = "#0072B2", "#E69F00", "#009E73", "#D55E00"
SKY, GREY, PURPLE = "#56B4E9", "#999999", "#CC79A7"
BOOT, SEED = 2000, 20260921

#: 인쇄 폭에 맞춰 만든다. 본문폭은 15.92 cm (6.27 in) 과 17.93 cm (7.06 in) 다.
#: 그림이 그보다 넓으면 Word 가 줄여 넣으면서 글자도 같이 줄어든다 - 13.2 in
#: 짜리를 15.92 cm 에 넣으면 9 pt 가 실효 4.9 pt 가 되어 읽을 수 없다.
#: 실효 7 pt 이상을 지키려면 폭을 8 in 안쪽으로 둔다.
plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 9,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.titlesize": 10, "axes.labelsize": 9,
    "xtick.labelsize": 8.5, "ytick.labelsize": 8.5,
    "figure.dpi": 200, "savefig.dpi": 300,
    "axes.unicode_minus": False,          # 마이너스 글리프 깨짐을 막는다
})


def save(fig, name):
    for ext in ("png", "pdf"):
        fig.savefig(FIG / f"{name}.{ext}", bbox_inches="tight")
    plt.close(fig)
    print(f"  {name}")


def boot_ci(x, n=BOOT, seed=SEED):
    """표적 클러스터 부트스트랩. 본문 분석과 같은 규격."""
    x = np.asarray(x, dtype=float)
    rng = np.random.default_rng(seed)
    d = np.sort([x[rng.integers(len(x), size=len(x))].mean() for _ in range(n)])
    return float(x.mean()), float(d[int(.025 * n)]), float(d[int(.975 * n)])


def box(ax, xy, wh, title, sub, face, edge, fs=9):
    x, y = xy
    w, h = wh
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.012,rounding_size=0.02",
                                fc=face, ec=edge, lw=1.1))
    ax.text(x + w / 2, y + h * (0.62 if sub else 0.5), title, ha="center", va="center",
            fontsize=fs, fontweight="bold", color="#1b2a38")
    if sub:
        ax.text(x + w / 2, y + h * 0.28, sub, ha="center", va="center",
                fontsize=fs - 1.3, color="#40566b")


def arrow(ax, a, b, color="#6b7c8c"):
    ax.add_patch(FancyArrowPatch(a, b, arrowstyle="-|>", mutation_scale=11,
                                 lw=1.1, color=color, shrinkA=0, shrinkB=0))


# ------------------------------------------------------------------ fig 1

def fig1_workflow():
    fig, ax = plt.subplots(figsize=(8.0, 3.14))
    ax.set_xlim(0, 10.2); ax.set_ylim(-0.42, 4.0); ax.axis("off")
    top = [("1. Constraints", "MSA conservation\nmotif / fixed sites"),
           ("2. Backbone", "native + RFD3 / BioEmu"),
           ("3. Sequences", "ProteinMPNN\nbulk generation"),
           ("4. Solubility score", "SoluProt\npre-filter optional")]
    bot = [("7. Portfolio", "joint-pass + diversity\n-> wet-lab"),
           ("6. Verification", "AF2 / ColabFold\npLDDT + RMSD"),
           ("5. Triage", "MPNN NLL or\ntarget-specific surrogate")]
    w, h = 2.30, 1.02
    for i, (t, s) in enumerate(top):
        x = 0.15 + i * 2.52
        box(ax, (x, 2.60), (w, h), t, s, "#EAF1F8" if i < 3 else "#E4F3EC",
            BLUE if i < 3 else GREEN)
        if i:
            arrow(ax, (x - 0.20, 3.11), (x - 0.01, 3.11))
    for i, (t, s) in enumerate(bot):
        x = 0.15 + (2 - i) * 2.52 + 1.26
        box(ax, (x, 0.75), (w, h), t, s, "#F6EFE3" if i == 0 else "#EAF1F8",
            ORANGE if i == 0 else BLUE)
    arrow(ax, (8.20, 2.58), (8.20, 1.79))
    for i in range(2):
        x = 0.15 + (2 - i) * 2.52 + 1.26
        arrow(ax, (x - 0.20, 1.26), (x - 0.01, 1.26))
    ax.text(0.15, 3.82, "RAPID is a workflow, not a single model: it links the design "
            "stages and allocates a fixed structure-prediction budget.",
            fontsize=9.5, fontweight="bold", color="#1b2a38")
    ax.text(0.15, 0.56, va="top", s="The computational endpoint is not solubility itself but the "
            "efficient recovery of candidates that pass both the\n"
            "solubility-oriented and the structure-preservation conditions. In the "
            "benchmark comparisons SoluProt was not applied as a\n"
            "pre-filter: every selection rule ranked the same candidate pool, and "
            "SoluProt entered only in the joint-pass decision (step 7).",
            fontsize=8.2, color="#5a6b7a")
    save(fig, "fig1_workflow")


# ------------------------------------------------------------------ fig 2

def fig2_exp2_forest():
    j = json.loads((G / "v2_mpnn_baseline.json").read_text())["groups"]
    rows = []
    for src, lbl, col in (("bioemu", "BioEmu", GREEN), ("rfd3", "RFD3", BLUE)):
        for B in (100, 80, 60, 40):
            e = j[f"{src}_pooled_cohorts"]["by_budget"][str(B)]["paired_vs"]["rf_probe-mpnn_score"]
            rows.append((f"{lbl}  B={B}", e["delta"], e["ci95"], e["ci99375_bonf8"], col))
    fig, ax = plt.subplots(figsize=(8.0, 4.0))
    for i, (lbl, d, ci, cb, col) in enumerate(rows):
        ax.plot(cb, [i, i], color=col, lw=1.2, alpha=.45, solid_capstyle="round")
        ax.plot(ci, [i, i], color=col, lw=4.2, alpha=.95, solid_capstyle="round")
        ax.plot([d], [i], "o", color=col, ms=6.5, mec="white", mew=1.0, zorder=3)
        keep = cb[0] > 0
        ax.text(cb[1] + .35, i, "survives correction" if keep else "includes 0",
                va="center", fontsize=7.6, color=col if keep else "#8a8a8a")
    ax.axvline(0, color="black", lw=1.0, ls="--")
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([r[0] for r in rows])
    ax.set_xlabel("Difference in joint-pass candidates per target  (RF - ProteinMPNN score)")
    ax.set_title("Experiment 2: same-budget difference\n(29 target x source units)\n"
                 "thick = nominal 95% CI · thin = corrected (8 tests, 99.375%)",
                 fontsize=9.4, fontweight="bold")
    ax.grid(axis="x", alpha=.25, lw=.6)
    ax.set_xlim(-6.5, 19)
    fig.tight_layout()
    save(fig, "fig2_experiment2_forest")


# ------------------------------------------------------------------ fig 3

def fig3_structural_context():
    rows = list(csv.DictReader((RES / "structural_context_threeway_N9.csv").open()))
    g = lambda k: np.array([float(r[k]) for r in rows])
    arms = ["Single\nbackbone\n+ surrogate", "Ensemble\n(random)", "Ensemble\n+ surrogate"]
    cols = [BLUE, SKY, GREEN]
    div = [g("single_div"), g("ensRandom_div"), g("ensSurr_div")]

    fig = plt.figure(figsize=(8.0, 5.9))
    gs = fig.add_gridspec(2, 2, width_ratios=[1.0, 1.32], height_ratios=[1.0, .52],
                          wspace=.46, hspace=.62)

    # A. 세 arm 의 다양성 - 짝지은 선
    ax = fig.add_subplot(gs[0, 0])
    for t in range(len(rows)):
        ax.plot([0, 1, 2], [div[0][t], div[1][t], div[2][t]], color="#c9d2da", lw=.8, zorder=1)
    for i in range(3):
        ax.scatter([i] * len(rows), div[i], s=34, color=cols[i], ec="white", lw=.6, zorder=3)
        m = div[i].mean()
        ax.plot([i - .26, i + .26], [m, m], color="black", lw=2.6, zorder=4)
        ax.text(i, m + .026, f"{m:.3f}", ha="center", fontsize=8.6, fontweight="bold",
                bbox=dict(fc="white", ec="none", pad=1.2))
    ax.set_xticks(range(3)); ax.set_xticklabels(arms, fontsize=8.0)
    ax.set_xlim(-.55, 2.55)
    ax.set_ylabel("Top-20 sequence diversity\n(1 - mean pairwise identity)")
    ax.set_title("A  Diversity by arm\n", fontsize=10, fontweight="bold", loc="left")
    ax.grid(axis="y", alpha=.22, lw=.6)

    # B. 두 대비를 CI 와 함께 - 이것이 주장이다
    ax = fig.add_subplot(gs[0, 1])
    contrasts = [("vs Single\nbackbone", div[2] - div[0], GREEN),
                 ("vs Ensemble\n(random)", div[2] - div[1], VERM)]
    for i, (lbl, d, col) in enumerate(contrasts):
        m, lo, hi = boot_ci(d)
        ax.scatter(d, [i] * len(d), s=28, color=col, alpha=.45, ec="white", lw=.5, zorder=2)
        ax.plot([lo, hi], [i, i], color=col, lw=4.0, solid_capstyle="round", zorder=3)
        ax.plot([m], [i], "o", color=col, ms=8, mec="white", mew=1.2, zorder=4)
        up = int((d > 0).sum())
        ax.annotate(f"{m:+.3f} [{lo:+.3f}, {hi:+.3f}]   {up}/{len(d)} up",
                    xy=(m, i), xytext=(0, 17), textcoords="offset points",
                    ha="center", fontsize=8.0, color=col, fontweight="bold")
    ax.axvline(0, color="black", lw=1.0, ls="--")
    ax.set_yticks([0, 1]); ax.set_yticklabels([c[0] for c in contrasts], fontsize=8.2)
    ax.set_ylim(-.6, 1.6)
    ax.set_xlabel("Paired difference in Top-20 diversity")
    ax.set_title("B  Paired contrasts, Ensemble + surrogate\n     (n=9, target bootstrap 95% CI)",
                 fontsize=10, fontweight="bold", loc="left")
    ax.grid(axis="x", alpha=.22, lw=.6)
    ax.set_xlim(-.17, .33)

    # C. 부수 지표는 작게 - 차이가 없다는 것이 요점이다
    ax = fig.add_subplot(gs[1, :])
    sec = [("pLDDT", (g("ensSurr_plddt") - g("single_plddt")) / 10.0, ORANGE, "/10"),
           ("SoluProt", g("ensSurr_soluprot") - g("single_soluprot"), PURPLE, "")]
    for i, (lbl, d, col, _) in enumerate(sec):
        m, lo, hi = boot_ci(d)
        ax.scatter(d, [i] * len(d), s=26, color=col, alpha=.45, ec="white", lw=.5, zorder=2)
        ax.plot([lo, hi], [i, i], color=col, lw=3.6, solid_capstyle="round", zorder=3)
        ax.plot([m], [i], "o", color=col, ms=7, mec="white", mew=1.1, zorder=4)
    ax.axvline(0, color="black", lw=1.0, ls="--")
    ax.set_yticks([0, 1])
    ax.set_yticklabels(["mean pLDDT\n(/10 units)", "mean SoluProt"], fontsize=8.2)
    ax.set_ylim(-.6, 1.6)
    ax.set_xlabel("vs Single backbone")
    ax.set_title("C  Secondary metrics\n     (same contrast)", fontsize=10,
                 fontweight="bold", loc="left")
    ax.grid(axis="x", alpha=.22, lw=.6)

    fig.suptitle("Structural context, three arms, 9 CATH targets\n"
                 "Diversity rises over a single backbone, but the surrogate\n"
                 "does not beat random selection within the ensemble",
                 fontsize=9.6, fontweight="bold", y=1.03)
    save(fig, "fig3_structural_context")


# ------------------------------------------------------------------ fig 4

def fig4_allocation():
    h = json.loads((G / "hierarchical_replay.json").read_text())
    e = h["sources"]["rfd3"]["by_budget"]["80"]
    p, con = e["point"], e["contrasts"]
    head = p["oracle_paid"] - p["equal_random"]
    lv = [("ProteinMPNN score", "mpnn_only_paid", GREY), ("Equal / random", "equal_random", GREY),
          ("Backbone allocation only", "backbone_only", SKY),
          ("RF ranking only", "rf_only", BLUE), ("RF + backbone allocation", "warmup_informed", GREEN)]
    vals = [(l, (p[k] - p["equal_random"]) / head * 100, c) for l, k, c in lv]

    fig = plt.figure(figsize=(8.0, 5.7))
    gs = fig.add_gridspec(2, 2, width_ratios=[1.0, .46], height_ratios=[1.0, .78],
                          wspace=.52, hspace=.78)

    ax = fig.add_subplot(gs[0, 0])
    ax.barh([v[0] for v in vals], [v[1] for v in vals], color=[v[2] for v in vals], height=.6)
    for i, (l, v, _) in enumerate(vals):
        #: 음수 막대의 값이 왼쪽 축 레이블을 덮지 않게 막대 오른쪽에 붙인다
        ax.text(v + 1.2 if v >= 0 else 1.2, i, f"{v:.1f}%", va="center",
                ha="left", fontsize=8.3)
    ax.axvline(0, color="black", lw=.9)
    ax.set_xlim(-12, 74)
    ax.set_xlabel("Headroom recovery\n(equal/random 0% -> oracle 100%)")
    ax.set_title("A  Levels (descriptive)", fontsize=10, fontweight="bold", loc="left")
    ax.grid(axis="x", alpha=.22, lw=.6)

    # B. 대비와 CI - 주 판정이 여기 있다
    ax = fig.add_subplot(gs[1, :])
    show = [("vs RF ranking only", "warmup_informed-rf_only", True),
            ("vs backbone allocation only", "warmup_informed-backbone_only", False),
            ("vs equal / random", "warmup_informed-equal_random", False),
            ("vs ProteinMPNN score", "warmup_informed-mpnn_only_paid", False)]
    for i, (lbl, key, primary) in enumerate(show):
        c = con[key]
        col = VERM if primary else GREY
        ax.plot(c["ci95"], [i, i], color=col, lw=4.2, solid_capstyle="round", zorder=3)
        ax.plot([c["delta"]], [i], "o", color=col, ms=7.5, mec="white", mew=1.1, zorder=4)
        ax.text(c["ci95"][1] + .4, i,
                f"{c['delta']:+.2f} [{c['ci95'][0]:+.2f}, {c['ci95'][1]:+.2f}]"
                + ("  primary — includes 0" if primary else ""),
                va="center", fontsize=7.8, color=col,
                fontweight="bold" if primary else "normal")
    ax.axvline(0, color="black", lw=1.0, ls="--")
    ax.set_yticks(range(len(show))); ax.set_yticklabels([s[0] for s in show], fontsize=8.3)
    ax.invert_yaxis()
    ax.set_xlim(-3, 26)
    ax.set_xlabel("Difference in joint-pass candidates per target\n(RF + backbone allocation - comparator)")
    ax.set_title("B  Contrasts with 95% CI", fontsize=10, fontweight="bold", loc="left")
    ax.grid(axis="x", alpha=.22, lw=.6)

    ax = fig.add_subplot(gs[0, 1])
    s = json.loads((G / "backbone_spread.json").read_text())["policies"]
    nm = [("rf_only", "RF ranking\nonly", BLUE), ("greedy_fill", "RF + backbone\nallocation", GREEN)]
    nb = [s[k]["mean_backbones_touched"] for k, _, _ in nm]
    ax.bar([n[1] for n in nm], nb, color=[n[2] for n in nm], width=.52)
    for i, (k, _, _) in enumerate(nm):
        ax.text(i, nb[i] + .25, f"{nb[i]:.1f}\nmax share {s[k]['mean_max_share']*100:.0f}%",
                ha="center", fontsize=8.0)
    ax.axhline(10, color="#888", ls=":", lw=1.0)
    ax.text(1.45, 10.2, "available 10", fontsize=7.4, color="#666", ha="right")
    ax.set_ylim(0, 12.6)
    ax.set_ylabel("Distinct backbones touched")
    ax.set_title("C  Spread", fontsize=10, fontweight="bold", loc="left")
    ax.grid(axis="y", alpha=.22, lw=.6)

    fig.suptitle("Experiment 3 · RFD3 confirmatory · B=80\n"
                 "Adding backbone allocation on top of sequence ranking does not\n"
                 "increase yield, and narrows the spread",
                 fontsize=9.6, fontweight="bold", y=1.00)
    save(fig, "fig4_allocation")


# ------------------------------------------------------------------ fig 5

def fig5_depth():
    d = json.loads((G / "depth_scaling.json").read_text())
    per, con = d["per_unit"], d["contrasts"]
    fig, axes = plt.subplots(1, 2, figsize=(8.0, 3.5), sharey=True)
    for ax, (arm, role) in zip(axes, (("greedy_fill", "primary"),
                                      ("greedy_thompson", "secondary"))):
        key = f"{arm}|B80"
        c = con[key]
        pts = []
        for t, u in per.items():
            try:
                b = {dep: u["by_depth"][dep]["by_budget"]["80"] for dep in ("18", "42")}
            except KeyError:
                continue
            f = {dep: ((b[dep][arm] - b[dep]["equal_random"])
                       / (b[dep]["oracle"] - b[dep]["equal_random"])) for dep in b}
            g = {dep: ((b[dep]["rf_only"] - b[dep]["equal_random"])
                       / (b[dep]["oracle"] - b[dep]["equal_random"])) for dep in b}
            D = {dep: f[dep] - g[dep] for dep in b}
            pts.append((D["18"], D["42"]))
        for a, bb in pts:
            up = bb > a
            ax.plot([0, 1], [a, bb], color=BLUE if up else ORANGE, lw=1.3, alpha=.8, zorder=2)
            ax.plot([0, 1], [a, bb], "o", color=BLUE if up else ORANGE, ms=5.5,
                    mec="white", mew=.8, zorder=3)
        for i, dep in enumerate(("18", "42")):
            m = np.mean([p[i] for p in pts])
            ax.plot([i - .16, i + .16], [m, m], color="black", lw=2.8, zorder=4)
        ax.axhline(0, color="#888", ls="--", lw=1.0)
        ax.set_xticks([0, 1])
        ax.set_xticklabels(["depth 18\n(concentration cap 35%)", "depth 42\n(cap 95%)"],
                           fontsize=8.4)
        ax.set_xlim(-.35, 1.55)
        ax.set_title(f"{arm} ({role})\n"
                     f"$\\Delta$ {c['delta']:+.3f} [{c['ci95'][0]:+.3f}, {c['ci95'][1]:+.3f}]"
                     f" · {sum(1 for a,b in pts if b>a)}/{len(pts)} up",
                     fontsize=9.6, fontweight="bold")
        ax.grid(axis="y", alpha=.22, lw=.6)
    axes[0].set_ylabel("D = headroom-recovery difference\n(greedy - RF-only)")
    h = [plt.Line2D([], [], color=BLUE, lw=1.6, marker="o", ms=5, label="D increases with depth"),
         plt.Line2D([], [], color=ORANGE, lw=1.6, marker="o", ms=5, label="D decreases with depth")]
    axes[1].legend(handles=h, loc="upper right", fontsize=8, frameon=False)
    fig.suptitle("Depth-extension pilot · RFD3 confirmatory\n"
            f"B=80 · {len(c['per_unit_delta'])} eligible units",
                 fontsize=9.6, fontweight="bold", y=1.04)
    fig.tight_layout()
    save(fig, "fig5_depth_scaling")


# --------------------------------------------------------------- note 그림

def note1_design():
    """흐름을 위에서 아래로만 흐르게 둔다. 앞선 판은 화살표가 서로 교차했다."""
    fig, ax = plt.subplots(figsize=(8.6, 4.79))
    ax.set_xlim(0, 10.6); ax.set_ylim(0, 5.9); ax.axis("off")
    ax.text(.1, 5.70, "Candidate selection in RAPID and the two primary analyses",
            fontsize=12, fontweight="bold", color="#14304a")
    ax.text(.1, 5.44, "RAPID = Resource-Aware, Artifact-Preserving Orchestration for "
            "Solubility-Oriented Protein Redesign", fontsize=8.0, color="#6b7c8c")

    chain = [("Target", "sequence + structure"), ("Constraints", "MSA / fixed positions"),
             ("Backbone context", "native / RFD3 / BioEmu"), ("ProteinMPNN", "candidates + NLL")]
    bw, bh, ytop = 2.32, .74, 4.42
    for i, (t, sub) in enumerate(chain):
        x = .25 + i * 2.55
        box(ax, (x, ytop), (bw, bh), t, sub, "#EAF1F8", BLUE, fs=8.6)
        if i:
            arrow(ax, (x - .22, ytop + bh / 2), (x - .02, ytop + bh / 2))
    mx = .25 + 3 * 2.55 + bw / 2                    # ProteinMPNN 중앙

    #: 경로 둘을 나란히, 종점을 그 아래 가운데. 화살표가 위에서 아래로만 간다.
    pw, ph, ypath = 3.30, .72, 3.02
    lx, rx = .70, 5.60
    box(ax, (lx, ypath), (pw, ph), "Learned path", "target-specific RF on 30 labels",
        "#E4F3EC", GREEN, fs=8.6)
    box(ax, (rx, ypath), (pw, ph), "Baseline path", "MPNN NLL, no label budget",
        "#F2F2F2", GREY, fs=8.6)
    ow, oh, yout = 2.60, .72, 1.88
    ox = 4.00
    box(ax, (ox, yout), (ow, oh), "Outcome", "joint-pass yield", "#E7EFF7", "#14304a", fs=8.6)

    arrow(ax, (mx, ytop), (lx + pw / 2, ypath + ph))
    arrow(ax, (mx, ytop), (rx + pw / 2, ypath + ph))
    arrow(ax, (lx + pw / 2, ypath), (ox + ow * .30, yout + oh))
    arrow(ax, (rx + pw / 2, ypath), (ox + ow * .70, yout + oh))
    ax.text(.70, 4.12, "both paths spend the same total folding budget B",
            fontsize=8.0, color="#6b7c8c")

    #: 이전 판은 "주 결론은 A 와 C 를 중심으로" 라고 적었는데 그림에 A·C 라는
    #: 이름이 없었다. 분석을 A/B/C 로 부르던 판의 잔재다. 실제 이름을 쓴다.
    for i, (t, q, ep, col) in enumerate([
            ("Primary analysis 1 · 67 CATH targets",
             "Does local calibration carry a real ranking signal?",
             "endpoint: unique-sequence pLDDT Top-20 recall", BLUE),
            ("Primary analysis 2 · v2 multi-source triage",
             "Does it beat MPNN NLL at the same folding budget?",
             "endpoint: joint-pass yield · 29 target x source units", GREEN)]):
        x = .25 + i * 5.20
        ax.add_patch(FancyBboxPatch((x, .40), 4.90, 1.12,
                                    boxstyle="round,pad=0.02,rounding_size=0.03",
                                    fc="white", ec=col, lw=1.2))
        ax.text(x + .18, 1.22, t, fontsize=9.2, fontweight="bold", color=col)
        ax.text(x + .18, .90, q, fontsize=8.4, color="#33475a")
        ax.text(x + .18, .60, ep, fontsize=8.0, color="#6b7c8c")
    ax.text(.25, .16, "A preliminary 11-target RFD3 pilot is reported separately in the "
            "Supplement; the primary conclusions rest on analyses 1 and 2.",
            fontsize=7.8, color=VERM)
    save(fig, "note_fig1_design")


def note2_headline():
    d = json.loads((ROOT / "data" / "benchmark" / "results"
                    / "exp1_unique_sequence.json").read_text()
                   )["units"]["unique"]["paired_vs"]
    j = json.loads((G / "v2_mpnn_baseline.json").read_text())["groups"]
    #: 패널을 여백으로 채우지 않고 실제로 있는 대비를 모두 싣는다.
    #: RF - XGBoost 는 앞선 판에서 빠져 있었다.
    left = [("RF - random", d["RF-Random"], BLUE),
            ("RF - Ridge", d["RF-Ridge"], ORANGE),
            ("RF - XGBoost", d["RF-XGBoost"], PURPLE)]
    fig, axes = plt.subplots(1, 2, figsize=(8.6, 2.5),
                             gridspec_kw={"width_ratios": [1, 1.18], "wspace": .42})

    ax = axes[0]
    for i, (lbl, e, col) in enumerate(left):
        ax.plot(e["ci95"], [i, i], color=col, lw=4.4, solid_capstyle="round", zorder=3)
        ax.plot([e["delta"]], [i], "o", color=col, ms=8, mec="white", mew=1.2, zorder=4)
        ax.text(e["ci95"][1] + .012, i,
                f"{e['delta']:+.4f} [{e['ci95'][0]:.3f}, {e['ci95'][1]:.3f}]",
                va="center", fontsize=7.8, color=col)
    ax.axvline(0, color="black", lw=1.0, ls="--")
    ax.set_yticks(range(len(left))); ax.set_yticklabels([l[0] for l in left])
    ax.set_ylim(-.55, len(left) - .45)           # 여백을 남기지 않는다
    ax.set_xlim(-.02, .40)
    ax.set_xlabel("Difference in Top-20 recall")
    ax.set_title("A  67-target unique-sequence pLDDT ranking",
                 fontsize=9.8, fontweight="bold", loc="left")
    ax.grid(axis="x", alpha=.22, lw=.6)

    ax = axes[1]                                  # A 와 같은 가로 방향으로 통일
    rows = []
    for src, lbl in (("rfd3", "RFD3"), ("bioemu", "BioEmu")):
        e = j[f"{src}_pooled_cohorts"]["by_budget"]["80"]["paired_vs"]
        rows.append((f"{lbl} · RF - random", e["rf_probe-random"], VERM))
        rows.append((f"{lbl} · RF - MPNN", e["rf_probe-mpnn_score"], BLUE))
    for i, (lbl, e, col) in enumerate(rows):
        ax.plot(e["ci95"], [i, i], color=col, lw=4.4, solid_capstyle="round", zorder=3)
        ax.plot([e["delta"]], [i], "o", color=col, ms=8, mec="white", mew=1.2, zorder=4)
        ax.text(e["ci95"][1] + .3, i, f"{e['delta']:+.2f}", va="center",
                fontsize=8.2, color=col)
    ax.axvline(0, color="black", lw=1.0, ls="--")
    ax.set_yticks(range(len(rows))); ax.set_yticklabels([r[0] for r in rows], fontsize=8.0)
    ax.set_ylim(-.55, len(rows) - .45)
    ax.set_xlim(-2, 14)
    ax.set_xlabel("Difference in joint-pass yield per target")
    ax.set_title("B  v2 multi-source comparison at B=80",
                 fontsize=9.8, fontweight="bold", loc="left")
    ax.grid(axis="x", alpha=.22, lw=.6)

    fig.suptitle("Target-specific surrogate:\nranking signal and same-budget incremental value",
                 fontsize=10.0, fontweight="bold", y=1.14, color="#14304a")
    save(fig, "note_fig2_headline")


def note3_source_stratified():
    j = json.loads((G / "v2_mpnn_baseline.json").read_text())["groups"]
    fig, axes = plt.subplots(1, 2, figsize=(8.6, 3.3), sharey=True)
    for ax, (src, lbl) in zip(axes, (("rfd3", "RFD3 (15 units)"),
                                     ("bioemu", "BioEmu (14 units)"))):
        by = j[f"{src}_pooled_cohorts"]["by_budget"]
        for off, key, col, mk, nm in ((-.13, "rf_probe-mpnn_score", BLUE, "o", "RF - MPNN score"),
                                      (+.13, "rf_probe-random", VERM, "s", "RF - random")):
            for i, B in enumerate((40, 60, 80, 100)):
                e = by[str(B)]["paired_vs"][key]
                ax.plot([i + off] * 2, e["ci95"], color=col, lw=1.6, solid_capstyle="round")
                ax.plot([i + off], [e["delta"]], mk, color=col, ms=7, mec="white", mew=.9,
                        label=nm if i == 0 else None)
                if e["ci99375_bonf8"][0] > 0:
                    ax.plot([i + off], [e["ci95"][1] + .55], "*", color=GREEN, ms=9,
                            mec="white", mew=.5)
        ax.axhline(0, color="#777", ls="--", lw=1.0)
        ax.set_xticks(range(4)); ax.set_xticklabels(["40", "60", "80", "100"])
        ax.set_xlabel("Total folding budget B")
        ax.set_title(lbl, fontsize=10, fontweight="bold")
        ax.grid(axis="y", alpha=.22, lw=.6)
        ax.tick_params(labelleft=True)            # 두 패널 모두 눈금값을 적는다
    axes[0].set_ylabel("Difference in joint-pass yield per target")
    axes[0].legend(loc="upper left", fontsize=8.2, frameon=False)
    fig.suptitle("v2 stored-candidate triage: source-stratified same-budget comparison",
                 fontsize=10.8, fontweight="bold", y=1.0, color="#14304a")
    #: 별표는 두 계열 모두에 찍힌다. 캡션이 한쪽만 말하면 안 된다.
    fig.text(.5, -.04, "Bars are nominal 95% CIs.  "
             "$\\star$ : that contrast also excludes 0 after the 8-test family "
             "correction (99.375% CI).", ha="center", fontsize=8.2, color="#6b7c8c")
    fig.tight_layout()
    save(fig, "note_fig3_source_stratified")


def noteS1_threeway_distribution():
    """보충: 세 arm 의 분포를 그대로 본다. 본문 fig3 은 대비를, 이것은 퍼짐을 낸다.

    앞선 판은 945x347 px 로 17 cm 에 들어가 141 dpi 였다. 인쇄 기준에 못 미친다.
    """
    rows = list(csv.DictReader((RES / "structural_context_threeway_N9.csv").open()))
    g = lambda k: np.array([float(r[k]) for r in rows])
    labs = ["Single\n+ surrogate", "RFD3+BioEmu\npool (random)", "RFD3+BioEmu\n+ surrogate"]
    cols = [BLUE, SKY, GREEN]
    panels = [("Top-20 sequence diversity", "mean pairwise diversity",
               [g("single_div"), g("ensRandom_div"), g("ensSurr_div")]),
              ("Selected-set pLDDT", "mean pLDDT",
               [g("single_plddt"), g("ensRandom_plddt"), g("ensSurr_plddt")]),
              ("Selected-set SoluProt", "mean SoluProt",
               [g("single_soluprot"), g("ensRandom_soluprot"), g("ensSurr_soluprot")])]
    fig, axes = plt.subplots(1, 3, figsize=(8.6, 3.1))
    rng = np.random.default_rng(SEED)
    for ax, (title, ylab, series) in zip(axes, panels):
        pos = np.arange(1, 4)
        bp = ax.boxplot(series, positions=pos, widths=.55, patch_artist=True,
                        showmeans=True,
                        meanprops=dict(marker="D", markerfacecolor="black",
                                       markeredgecolor="black", markersize=4),
                        medianprops=dict(color="#444444"),
                        flierprops=dict(marker="", alpha=0))
        for patch, c in zip(bp["boxes"], cols):
            patch.set_facecolor(c); patch.set_alpha(.30); patch.set_edgecolor(c)
        for i in range(3):
            ax.scatter(pos[i] + rng.uniform(-.10, .10, len(series[i])), series[i],
                       s=26, color=cols[i], ec="white", lw=.5, zorder=3, alpha=.9)
        ax.set_xticks(pos); ax.set_xticklabels(labs, fontsize=8.0)
        ax.set_title(title, fontsize=9.6, fontweight="bold")
        ax.set_ylabel(ylab, fontsize=8.6)
        ax.grid(axis="y", alpha=.22, lw=.6)
    fig.suptitle("Structural-context three-arm comparison, 9 CATH targets\n"
                 "Diamond = mean.  Diversity is highest in the random-selection\n"
                 "arm, not in the surrogate arm.",
                 fontsize=9.4, fontweight="bold", y=1.10)
    fig.tight_layout()
    save(fig, "note_figS1_threeway_distribution")


def main() -> int:
    print("원고 그림 (영어 통일) ->", FIG)
    for fn in (fig1_workflow, fig2_exp2_forest, fig3_structural_context, fig4_allocation,
               fig5_depth, note1_design, note2_headline, note3_source_stratified,
               noteS1_threeway_distribution):
        fn()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
