#!/usr/bin/env python3
"""확증 코호트 다섯 분석의 그림. 영어, `61_` 과 같은 체재.

폴딩이 끝나기 전에 써 둔다. 스키마는 `42_`·`39_`·`40_`·`41_`·`45_` 가 내는
JSON 이고 내가 쓴 것이라 이미 정해져 있다. 산출물이 없는 그림은 건너뛴다.

    fig6   수확 확증   hierarchical_confirmatory.json    주 종점 G 차이
    fig7   선택 분해   selection_gain_decomposition.json Between - Within
    fig8   coverage    coverage_preserving.json          EFBC + 가드레일
    fig9   구조        structural_dispersion.json        CA-RMSD dispersion
    fig10  STOP 진단   stop_rule_diagnosis.json          판정 아님

미리 정해 둔 표시 규칙
----------------------
    주 종점에는 언제나 CI 를 붙이고, 0 을 포함하면 그렇게 적는다.
    수확 그림에는 **자격 unit 수와 그때의 검정력을 함께 적는다** - 사전지정
    §7.1 이 음성일 때 요구하는 것이다. 그림에서 빠뜨리면 캡션에서도 빠진다.
    STOP 진단은 제목에 "diagnostic, not a judgement" 를 적는다.
"""

from __future__ import annotations

import json
import os
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import argparse

ROOT = Path(__file__).resolve().parents[2]
#: 결과 디렉터리를 바꿔 끼울 수 있게 한다. 기본값은 저장소의 동결 경로다.
G = Path(os.environ.get("RAPID_GATE0", "")) if os.environ.get("RAPID_GATE0") \
    else ROOT / "public_data" / "benchmark" / "gate0"
FIG = ROOT / "figures" / "submission"

BLUE, ORANGE, GREEN, VERM = "#0072B2", "#E69F00", "#009E73", "#D55E00"
SKY, GREY, PURPLE = "#56B4E9", "#999999", "#CC79A7"

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 9,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.titlesize": 10, "axes.labelsize": 9,
    "xtick.labelsize": 8.5, "ytick.labelsize": 8.5,
    "figure.dpi": 200, "savefig.dpi": 300, "axes.unicode_minus": False,
})


def save(fig, name):
    for ext in ("png", "pdf"):
        fig.savefig(FIG / f"{name}.{ext}", bbox_inches="tight")
    plt.close(fig)
    print(f"  {name}")


def load(name):
    p = G / name
    if not p.exists():
        print(f"  (건너뜀) {name} 없음")
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def forest(ax, rows, xlabel, title, zero=True):
    """rows: (label, delta, ci95, color, note)."""
    for i, (lbl, d, ci, col, note) in enumerate(rows):
        if ci is None or any(x is None or math.isnan(x) for x in ci):
            continue
        ax.plot(ci, [i, i], color=col, lw=4.2, solid_capstyle="round", zorder=3)
        ax.plot([d], [i], "o", color=col, ms=7, mec="white", mew=1.1, zorder=4)
        if note:
            ax.annotate(note, xy=(d, i), xytext=(0, 14), textcoords="offset points",
                        ha="center", fontsize=7.6, color=col, fontweight="bold")
    if zero:
        ax.axvline(0, color="black", lw=1.0, ls="--")
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([r[0] for r in rows], fontsize=8.2)
    ax.set_ylim(-.6, len(rows) - .25)
    ax.invert_yaxis()
    ax.set_xlabel(xlabel)
    ax.set_title(title, fontsize=9.8, fontweight="bold", loc="left")
    ax.grid(axis="x", alpha=.22, lw=.6)


def power_at(n, effect=0.118, sd=0.184):
    """실현된 n 에서의 **설계** 검정력. 양측 0.05.

    관측된 효과로 계산하는 "observed power" 가 아니다 - 그것은 p 값의 단조
    변환일 뿐이라 음성 결과를 설명하는 데 쓸 수 없다. 여기 쓰는 효과와 SD 는
    사전지정 §7.1 이 파일럿에서 **미리** 고정한 값(0.118, 0.184)이다.
    """
    if n < 2:
        return float("nan")
    from math import erf, sqrt
    se = sd / sqrt(n)
    z = effect / se - 1.959964
    return 0.5 * (1 + erf(z / sqrt(2)))


# ------------------------------------------------------------------ fig 6

def fig6_confirmatory_harvest():
    d = load("hierarchical_confirmatory.json")
    if not d:
        return
    r = d["result"]
    PB = str(d["primary_budget"])
    budgets = sorted(r["by_budget"], key=int)

    fig = plt.figure(figsize=(8.0, 5.6))
    gs = fig.add_gridspec(2, 2, height_ratios=[1.0, .95], width_ratios=[1.0, .85],
                          wspace=.52, hspace=.70)

    # A. 주 예산점의 arm 별 G
    ax = fig.add_subplot(gs[0, 0])
    e = r["by_budget"][PB]
    order = [a for a in ("equal_random", "mpnn_only", "backbone_only", "rf_only",
                         "greedy_frozen", "adaptive_sentinel", "oracle")
             if a in e["G_point"]]
    cols = {"greedy_frozen": GREEN, "rf_only": BLUE, "oracle": GREY,
            "equal_random": GREY, "backbone_only": SKY, "mpnn_only": GREY,
            "adaptive_sentinel": PURPLE}
    vals = [e["G_point"][a] * 100 for a in order]
    ax.barh(range(len(order)), vals, color=[cols.get(a, GREY) for a in order], height=.6)
    for i, v in enumerate(vals):
        ax.text(v + 1.5, i, f"{v:.1f}%", va="center", fontsize=8.0)
    ax.set_yticks(range(len(order)))
    ax.set_yticklabels([a.replace("_", " ") for a in order], fontsize=8.0)
    ax.invert_yaxis()
    ax.axvline(0, color="black", lw=.9)
    ax.set_xlabel("Headroom recovery G  (%)")
    ax.set_title(f"A  Levels at B={PB} (descriptive)", fontsize=9.8,
                 fontweight="bold", loc="left")
    ax.grid(axis="x", alpha=.22, lw=.6)

    # B. 예산별 주 종점 - 여기에 판정이 있다
    ax = fig.add_subplot(gs[0, 1])
    rows = []
    for B in budgets:
        s = r["by_budget"][B].get("primary")
        if not s:
            continue
        star = " *" if B == PB else ""
        rows.append((f"B={B}{star}  n={s['n']}", s["delta"], s["ci95"],
                     VERM if B == PB else GREY,
                     ("includes 0" if not s["excludes_zero"] else "excludes 0")
                     if B == PB else None))
    forest(ax, rows, "G(greedy_frozen) - G(rf_only)",
           "B  Primary endpoint, 95% CI")

    # C. 자격과 검정력 - 사전지정 §7.1 이 요구한다
    ax = fig.add_subplot(gs[1, 0])
    nall = [r["by_budget"][B]["n_targets_all"] for B in budgets]
    nel = [r["by_budget"][B]["n_targets_eligible"] for B in budgets]
    x = np.arange(len(budgets))
    ax.bar(x - .18, nall, width=.34, color=GREY, label="all targets")
    ax.bar(x + .18, nel, width=.34, color=BLUE, label="eligible (denominator >= 5)")
    ax.axhline(16, color=VERM, ls="--", lw=1.2)
    ax.text(-.45, 16.8, "n=16: power 73%", fontsize=7.2, color=VERM, ha="left")
    for i, v in enumerate(nel):
        ax.text(i + .18, v + .5, f"{v}\n{power_at(v):.0%}", ha="center", fontsize=7.4)
    ax.set_xticks(x); ax.set_xticklabels([f"B={B}" for B in budgets])
    ax.set_ylabel("targets")
    ax.set_ylim(0, max(nall) * 1.32)
    ax.legend(fontsize=7.4, frameon=False, loc="upper left")
    ax.set_title("C  Eligibility and design power\n"
                 "     (prespecified effect 0.118, SD 0.184)",
                 fontsize=9.2, fontweight="bold", loc="left")
    ax.grid(axis="y", alpha=.22, lw=.6)

    # D. 표적 이질성 - 평균 하나로 덮이지 않게
    ax = fig.add_subplot(gs[1, 1])
    per = r["per_target"]
    xs, ys = [], []
    for t, u in per.items():
        b = u["by_budget"].get(PB)
        if not b or not b["eligible"] or b["G"].get("greedy_frozen") is None:
            continue
        xs.append(u["joint_rate"])
        ys.append(b["G"]["greedy_frozen"] - b["G"]["rf_only"])
    if xs:
        ax.scatter(xs, ys, s=34, color=GREEN, ec="white", lw=.6, zorder=3)
        ax.axhline(0, color="black", lw=1.0, ls="--")
        ax.set_xlabel("target joint-pass rate")
        ax.set_ylabel("G(greedy) - G(rf_only)")
    ax.set_title("D  Per-target spread (eligible)", fontsize=9.8,
                 fontweight="bold", loc="left")
    ax.grid(alpha=.22, lw=.6)

    s = r["by_budget"][PB].get("primary")
    verdict = ("does not support" if (s and not s["excludes_zero"])
               else ("supports" if (s and s["delta"] > 0) else "contradicts"))
    fig.suptitle(f"Confirmatory cohort · RFD3 · 34 targets\n"
                 f"Backbone allocation on top of sequence ranking: the primary "
                 f"endpoint {verdict} the hypothesis",
                 fontsize=9.8, fontweight="bold", y=1.03)
    save(fig, "fig6_confirmatory_harvest")


# ------------------------------------------------------------------ fig 7

def fig7_selection_decomposition():
    d = load("selection_gain_decomposition.json")
    if not d:
        return
    r = d["result"]
    PB = str(d["primary_budget"])
    budgets = sorted(r["by_budget"], key=int)
    fig, axes = plt.subplots(1, 2, figsize=(8.4, 3.4),
                             gridspec_kw={"width_ratios": [1.15, 1.0], "wspace": .52})

    ax = axes[0]
    e = r["by_budget"][PB]["components"]
    names = [("Total", GREY), ("Between", BLUE), ("Within", ORANGE), ("Inter", GREY)]
    rows = [(n, e[n]["delta"], e[n]["ci95"], c, None) for n, c in names if n in e]
    forest(ax, rows, "Difference in joint-pass candidates",
           f"A  Decomposition at B={PB}")

    ax = axes[1]
    rows = []
    for B in budgets:
        c = r["by_budget"][B]["components"].get("Between-Within")
        if not c:
            continue
        star = " *" if B == PB else ""
        rows.append((f"B={B}{star}", c["delta"], c["ci95"],
                     VERM if B == PB else GREY,
                     ("includes 0" if not c["excludes_zero"] else "excludes 0")
                     if B == PB else None))
    forest(ax, rows, "Between - Within", "B  Primary endpoint, 95% CI")

    w = r["by_budget"][PB]["components"].get("Within", {})
    note = ("Within is not 0 — the RF gain is not carried by between-backbone "
            "discrimination alone" if w and w.get("excludes_zero")
            else "Within is not distinguishable from 0")
    fig.suptitle("Where does the sequence-selection gain come from?\n" + note,
                 fontsize=9.8, fontweight="bold", y=1.10)
    save(fig, "fig7_selection_decomposition")


# ------------------------------------------------------------------ fig 8

def fig8_coverage_efbc():
    d = load("coverage_preserving.json")
    if not d:
        return
    r = d["result"]
    PB = str(d["primary_budget"])
    budgets = sorted(r["by_budget"], key=int)
    fig = plt.figure(figsize=(8.2, 5.4))
    gs = fig.add_gridspec(2, 2, wspace=.50, hspace=.72)

    pol = ["coverage_v2", "static_equal", "greedy_fill", "static_equal_matched"]
    cols = {"coverage_v2": GREEN, "static_equal": BLUE,
            "greedy_fill": ORANGE, "static_equal_matched": SKY}

    ax = fig.add_subplot(gs[0, 0])
    for p in pol:
        ys = [r["by_budget"][B]["point"][p]["efbc"] for B in budgets]
        ax.plot([int(b) for b in budgets], ys, "o-", color=cols[p], ms=5,
                label=p.replace("_", " "), lw=1.6)
    ax.set_xlabel("budget cap B"); ax.set_ylabel("terminal EFBC")
    ax.legend(fontsize=7.2, frameon=False)
    ax.set_title("A  Primary endpoint (EFBC)", fontsize=9.8, fontweight="bold", loc="left")
    ax.grid(alpha=.22, lw=.6)

    ax = fig.add_subplot(gs[0, 1])
    rows = []
    for B in budgets:
        c = r["by_budget"][B]["contrasts"].get("coverage_v2 - static_equal")
        if not c:
            continue
        star = " *" if B == PB else ""
        rows.append((f"B={B}{star}", c["delta"], c["ci95"],
                     VERM if B == PB else GREY, None))
    forest(ax, rows, "EFBC  (coverage_v2 - static/equal)",
           "B  Primary contrast, 95% CI")

    ax = fig.add_subplot(gs[1, 0])
    for p in ("coverage_v2", "static_equal"):
        ys = [r["by_budget"][B]["point"][p]["calls"] for B in budgets]
        ax.plot([int(b) for b in budgets], ys, "o-", color=cols[p], ms=5, lw=1.6,
                label=p.replace("_", " "))
    ax.plot([int(b) for b in budgets], [int(b) for b in budgets], ":", color=GREY,
            lw=1.2, label="cap")
    ax.set_xlabel("budget cap B"); ax.set_ylabel("calls actually spent")
    ax.legend(fontsize=7.2, frameon=False)
    ax.set_title("C  Realized spend (v2 STOPs early)", fontsize=9.8,
                 fontweight="bold", loc="left")
    ax.grid(alpha=.22, lw=.6)

    ax = fig.add_subplot(gs[1, 1])
    xs = [int(b) for b in budgets]
    for key, col, lbl in (("structural_yield_ratio_vs_static_equal", VERM, "vs same-cap"),
                          ("structural_yield_ratio_vs_static_equal_matched", SKY,
                           "vs call-matched")):
        gr = [r["by_budget"][B]["guardrail"].get(key) for B in budgets]
        if not any(gr):
            continue
        ax.plot(xs, [g["ratio"] for g in gr], "o-", color=col, ms=5, lw=1.6, label=lbl)
        ax.plot(xs, [g["lcb95_onesided"] for g in gr], "v--", color=col, ms=5,
                lw=1.1, alpha=.7)
    thr = r["by_budget"][PB]["guardrail"].get(
        "structural_yield_ratio_vs_static_equal", {}).get("threshold", 0.90)
    ax.axhline(thr, color="black", ls="--", lw=1.2)
    ax.text(xs[-1], thr + .02, f"acceptance {thr:.2f}", fontsize=7.4, ha="right")
    ax.set_xlabel("budget cap B"); ax.set_ylabel("structural-yield ratio")
    ax.legend(fontsize=7.2, frameon=False, loc="lower right")
    ax.set_title("D  Guardrail (circle = ratio, triangle = one-sided 95% LCB)",
                 fontsize=9.0, fontweight="bold", loc="left")
    ax.grid(alpha=.22, lw=.6)

    g = r["by_budget"][PB]["guardrail"].get("structural_yield_ratio_vs_static_equal", {})
    tail = ("meets" if g.get("pass") else "does not meet")
    fig.suptitle("Coverage-preserving allocation on its own endpoint\n"
                 f"EFBC is the objective; the yield guardrail {tail} the acceptance "
                 "criterion at the primary budget", fontsize=9.6,
                 fontweight="bold", y=1.03)
    save(fig, "fig8_coverage_efbc")


# ------------------------------------------------------------------ fig 9

def fig9_structural_dispersion():
    d = load("structural_dispersion.json")
    if not d:
        return
    PB = str(json.loads((G / "coverage_preserving.json").read_text(
        encoding="utf-8"))["primary_budget"]) if (G / "coverage_preserving.json").exists() else None
    budgets = sorted(d["by_budget"], key=int)
    PB = PB if PB in d["by_budget"] else budgets[len(budgets) // 2]
    fig, axes = plt.subplots(1, 2, figsize=(8.4, 3.3),
                             gridspec_kw={"width_ratios": [1.0, 1.2], "wspace": .50})

    ax = axes[0]
    q = d["pooled_backbone_distance"]
    if q and q.get("quantiles"):
        ks = sorted(q["quantiles"], key=float)
        ax.plot([float(k) * 100 for k in ks], [q["quantiles"][k] for k in ks],
                "o-", color=BLUE, ms=5, lw=1.6)
        ax.axhline(q["mean"], color=GREY, ls="--", lw=1.1)
        ax.text(5, q["mean"] + .04, f"mean {q['mean']:.2f} A", fontsize=7.6, color=GREY)
    ax.set_xlabel("percentile"); ax.set_ylabel("within-target backbone CA-RMSD (A)")
    ax.set_title(f"A  Distance distribution (n={q['n_pairs'] if q else 0} pairs)",
                 fontsize=9.8, fontweight="bold", loc="left")
    ax.grid(alpha=.22, lw=.6)

    ax = axes[1]
    e = d["by_budget"][PB]["contrasts"]
    rows = []
    for k, c in e.items():
        metric, pair = k.split(" | ")
        lbl = ("mass-weighted" if "mass" in metric else "unweighted") + "\n" + \
              pair.replace("coverage_v2 - ", "vs ")
        rows.append((lbl, c["delta"], c["ci95"],
                     GREEN if "mass" in metric else SKY, None))
    forest(ax, rows, "difference in mean pairwise CA-RMSD (A)",
           f"B  Dispersion contrasts at B={PB}, 95% CI")

    any_sig = any(c["excludes_zero"] for c in e.values())
    fig.suptitle("Does higher EFBC come with more structural dispersion?\n" +
                 ("Some contrasts exclude 0 — read the effect size against the "
                  "2 A scale of the distribution" if any_sig else
                  "Operational coverage rose without measurable structural "
                  "diversification"), fontsize=9.6, fontweight="bold", y=1.10)
    save(fig, "fig9_structural_dispersion")


# ----------------------------------------------------------------- fig 10

def fig10_stop_diagnosis():
    d = load("stop_rule_diagnosis.json")
    if not d:
        return
    cf, re_ = d["counterfactual"], d["reached"]
    budgets = sorted(cf, key=int)
    PB = str(re_["budget"]) if str(re_["budget"]) in cf else budgets[len(budgets) // 2]
    fig, axes = plt.subplots(1, 3, figsize=(8.6, 3.1),
                             gridspec_kw={"width_ratios": [1.0, .85, 1.25], "wspace": .58})

    # A. 해석적 - 자료를 쓰지 않는다
    ax = axes[0]
    ks = sorted({s["k"] for s in d["analytic"]["samples"]})
    for n, col in ((1, SKY), (4, BLUE), (40, "#04395e")):
        ys = [s["gain"] for k in ks for s in d["analytic"]["samples"]
              if s["k"] == k and s["n"] == n]
        if len(ys) == len(ks):
            ax.plot(ks, ys, "o-", color=col, ms=4, lw=1.4, label=f"n={n}")
    ax.axhline(0, color="black", lw=1.0, ls="--")
    ax.set_xlabel("backbones k with uniform mass")
    ax.set_ylabel("one-step EFBC gain")
    ax.legend(fontsize=7.2, frameon=False)
    #: n 이 커지면 이득이 0 에 붙어 보이지만 부호는 끝까지 음수다. 그 사실이
    #: 주장의 전부이므로 격자 최대값을 숫자로 적는다.
    ax.text(.97, .06, f"max over k=2..12, n=1..40:\n"
            f"{d['analytic']['max_gain_over_grid']:.1e}  (always < 0)",
            transform=ax.transAxes, ha="right", va="bottom", fontsize=7.0,
            color="#444")
    ax.set_title("A  Analytic: gain < 0\nat the optimum", fontsize=9.4,
                 fontweight="bold", loc="left")
    ax.grid(alpha=.22, lw=.6)

    # B. 그 상태에 얼마나 닿는가
    ax = axes[1]
    sh = re_["max_over_min_f_at_stop"]
    ax.bar([0, 1], [re_["stop_rate"] * 100, (sh["share_exactly_uniform"] or 0) * 100],
           color=[VERM, GREEN], width=.55)
    for i, v in enumerate([re_["stop_rate"] * 100,
                           (sh["share_exactly_uniform"] or 0) * 100]):
        ax.text(i, v + 2, f"{v:.0f}%", ha="center", fontsize=8.4, fontweight="bold")
    ax.set_xticks([0, 1])
    ax.set_xticklabels(["runs that\nSTOP", "of those, f\nexactly uniform"],
                       fontsize=8.0)
    ax.set_ylim(0, 112); ax.set_ylabel("%")
    ax.set_title(f"B  Observed at B={re_['budget']}", fontsize=9.4,
                 fontweight="bold", loc="left")
    ax.grid(axis="y", alpha=.22, lw=.6)

    # C. 탐색적 반사실
    ax = axes[2]
    e = cf[PB]
    labs = ["EFBC", "structural\nyield", "calls\nspent"]
    v2 = [e["point"]["efbc"]["v2"], e["point"]["struct"]["v2"], e["point"]["calls"]["v2"]]
    ns = [e["point"]["efbc"]["nostop"], e["point"]["struct"]["nostop"],
          e["point"]["calls"]["nostop"]]
    rel = [n / v if v else float("nan") for n, v in zip(ns, v2)]
    x = np.arange(3)
    ax.bar(x, rel, color=[GREY, VERM, SKY], width=.55)
    ax.axhline(1.0, color="black", lw=1.0, ls="--")
    for i, (r_, n, v) in enumerate(zip(rel, ns, v2)):
        ax.text(i, r_ + .12, f"x{r_:.2f}\n{v:.1f}->{n:.1f}", ha="center", fontsize=7.4)
    ax.set_xticks(x); ax.set_xticklabels(labs, fontsize=8.0)
    ax.set_ylabel("STOP removed / STOP kept")
    ax.set_ylim(0, max(rel) * 1.45)
    ax.set_title(f"C  Counterfactual at B={PB}\n(exploratory)", fontsize=9.4,
                 fontweight="bold", loc="left")
    ax.grid(axis="y", alpha=.22, lw=.6)

    lcb = e.get("guardrail_nostop_lcb95", float("nan"))
    thr = e.get("threshold", .90)
    fig.suptitle("The STOP rule fires when the policy reaches its own optimum "
                 "— diagnostic, not a judgement\n"
                 f"Removing it leaves EFBC unchanged; the guardrail LCB moves to "
                 f"{lcb:.3f} against a {thr:.2f} threshold",
                 fontsize=9.4, fontweight="bold", y=1.14)
    save(fig, "fig10_stop_rule_diagnosis")


def main(argv=None) -> int:
    global G, FIG
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", default=str(G), help="산출물 JSON 디렉터리")
    ap.add_argument("--out", default=str(FIG))
    a = ap.parse_args(argv)
    G, FIG = Path(a.dir), Path(a.out)
    FIG.mkdir(parents=True, exist_ok=True)
    print("확증 결과 그림 ->", FIG)
    for fn in (fig6_confirmatory_harvest, fig7_selection_decomposition,
               fig8_coverage_efbc, fig9_structural_dispersion, fig10_stop_diagnosis):
        try:
            fn()
        except Exception as exc:                 # 산출물이 반쪽이어도 나머지는 낸다
            print(f"  !! {fn.__name__}: {type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
