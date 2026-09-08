#!/usr/bin/env python3
"""ThermoMPNN 을 RAPID 설계에 돌리고 Rosetta·pLDDT·RMSD 와 비교한다.

무엇을 확인할 수 있고 없는가
----------------------------
de novo 다중 변이 설계의 wet-lab 안정성 라벨이 없다. 그래서 세 모형을 비교해도
**누가 맞는지는 확인할 수 없다.** 확인할 수 있는 것은 네 가지다.

    중복성      두 신호가 같은 것을 재는가
    적용 가능성  우리 변이 규모에서 값이 의미를 갖는가
    불일치      어디서 갈리는가
    이상 동작    분포가 무너지는 구간이 있는가

'비슷하면 SPURS 불필요, 다르면 SPURS 필요' 로 결정하지 않는다. 비슷하다는 것은
중복 가능성을 보여줄 뿐 둘 다 틀릴 수 있고, 다르다고 해서 SPURS 가 판정자가
되지도 않는다.

적용 범위
---------
ThermoMPNN 은 단일 점변이로 학습됐고 다중 변이는 가법 합이다. RAPID 설계는
설계당 중앙값 77 치환이다(run/tier 279 개 측정). 그래서 **native 백본 설계만**
대상으로 한다 - RFD3·BioEmu 백본은 새로 생성된 구조라 native 대비 변이가
정의되지 않는다.

입력은 native 구조다. ThermoMPNN 은 준 구조에서 출발해 변이했을 때의 ΔΔG 를
내므로, 설계의 relaxed PDB 를 넘기면 그 위치가 이미 변이돼 있어 wildtype
불일치로 거부한다.

상관은 within-target·within-backbone 으로 본다
-----------------------------------------------
pooled 상관은 타겟 간 차이와 타겟 내 차이를 섞는다. 응집 검정에서 그 둘이 반대
방향이라 pooled 만 보면 결론이 뒤집혔다(Simpson). 같은 실수를 반복하지 않는다.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "pipeline-mcp" / "src"))

BASE = PROJECT_ROOT / "public_data" / "benchmark" / "gate0"
OUTPUTS = Path("/opt/protein_pipeline/outputs")


def _worker_url(port: int) -> str:
    host = os.environ.get("RAPID_GPU_HOST", "").strip()
    return f"http://{host}:{port}" if host else ""


def spearman(xs, ys):
    if len(xs) < 4:
        return None

    def rank(values):
        order = sorted(range(len(values)), key=lambda i: values[i])
        out = [0.0] * len(values)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
                j += 1
            mid = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                out[order[k]] = mid
            i = j + 1
        return out

    rx, ry = rank(xs), rank(ys)
    n = len(xs)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    dx = sum((a - mx) ** 2 for a in rx) ** 0.5
    dy = sum((b - my) ** 2 for b in ry) ** 0.5
    return None if dx == 0 or dy == 0 else num / (dx * dy)


def collect_native_designs() -> list[dict]:
    """relax + AF2 를 함께 가진 native-백본 설계를 모은다."""
    rows = []
    for relax_path in sorted(OUTPUTS.glob("*/tiers/*/relax_scores.json")):
        tier = relax_path.parent
        af2_path = tier / "af2_scores.json"
        if not af2_path.exists():
            continue
        try:
            relax = json.loads(relax_path.read_text()).get("score_per_residue") or {}
            af2 = json.loads(af2_path.read_text())
        except Exception:
            continue
        plddt = af2.get("scores") or {}
        rmsd = af2.get("rmsd_scores") or {}
        mut = {}
        report = tier / "mutation_report.json"
        if report.exists():
            try:
                mut = (json.loads(report.read_text()).get("mutation_counts") or {}).get(
                    "per_sample") or {}
            except Exception:
                mut = {}
        run = tier.parts[-3]
        for key in sorted(set(relax) & set(plddt)):
            # native 백본만: 설계 id 가 target: 로 시작하는 것
            if not key.startswith("target:"):
                continue
            rows.append({
                "run": run, "tier": tier.name, "design": key,
                "relax": float(relax[key]), "plddt": float(plddt[key]),
                "rmsd": float(rmsd[key]) if key in rmsd else None,
                "mutation_median": mut.get("p50"), "pdb_dir": str(tier),
            })
    return rows



def read_fasta(path: Path) -> list[tuple[str, str]]:
    if not path.exists():
        return []
    out, header, buf = [], None, []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith(">"):
            if header is not None:
                out.append((header, "".join(buf)))
            header, buf = line[1:].strip(), []
        elif header is not None:
            buf.append(line.strip())
    if header is not None:
        out.append((header, "".join(buf)))
    return out


def mutation_list(native: str, design: str, chain: str, resseq: list[int]) -> list[str] | None:
    """ThermoMPNN 형식의 변이 목록. 실패하면 None - 추측해서 만들지 않는다.

    형식은 **wildtype AA + resseq + mutant AA** 다 (예: "N9E"). 표준 ΔΔG 표기이고
    chain 은 토큰이 아니라 별도 인자로 넘긴다.

    clients/thermomp.py 의 docstring 은 "chain + 1-based resseq + mutant AA" 라고
    적혀 있는데 그것이 틀렸다. chain 을 앞에 붙이면 워커가 그 문자를 wildtype 으로
    읽고 "wildtype mismatch at A9: PDB says N, token says A" 로 거부한다.

    resseq 는 구조의 실제 잔기번호여야 한다. 길이가 안 맞으면 대응을 짐작할 수
    없으므로 포기한다.
    """
    if len(native) != len(design) or len(native) != len(resseq):
        return None
    out = []
    for i, (a, b) in enumerate(zip(native, design)):
        if a != b and a.isalpha() and b.isalpha():
            out.append(f"{a}{resseq[i]}{b}")
    return out


def ca_resseq(pdb_text: str, chain: str) -> list[int]:
    seen, out = set(), []
    for line in pdb_text.splitlines():
        if not line.startswith("ATOM") or line[12:16].strip() != "CA":
            continue
        if line[21] != chain:
            continue
        num = int(line[22:26])
        if num not in seen:
            seen.add(num)
            out.append(num)
    return out


def run_thermomp(rows, *, url: str, limit: int) -> dict:
    """적용 가능한 설계에만 돌린다. 못 만든 것은 이유와 함께 센다."""
    from pipeline_mcp.clients.thermomp import LocalHTTPThermoMPNNClient

    client = LocalHTTPThermoMPNNClient(base_url=url, token=None, timeout_s=3600.0)
    done, skipped = [], collections.Counter()
    targets = rows if not limit else rows[:limit]
    for index, row in enumerate(targets, start=1):
        tier = Path(row["pdb_dir"])
        native = read_fasta((tier / ".." / ".." / "target.fasta").resolve())
        if not native:
            skipped["native fasta 없음"] += 1
            continue
        designs = {h.split(",")[0].split()[0]: seq for h, seq in
                   read_fasta(tier / "designs.fasta")}
        # relax 의 설계 id 는 "target:12" 이고 fasta 헤더는 "12" 다.
        sample = row["design"].split(":")[-1]
        design_seq = designs.get(sample)
        if design_seq is None:
            skipped["설계 서열 못 찾음"] += 1
            continue
        # ThermoMPNN 은 **native 구조**를 받아야 한다. 변이의 출발점이 native 이므로
        # 설계의 relaxed PDB 를 넘기면 "wildtype mismatch at A9: PDB says E, token
        # says A" 로 거부한다 - 그 위치가 이미 변이된 잔기이기 때문이다.
        native_pdb = (tier / ".." / ".." / "target.pdb").resolve()
        if not native_pdb.exists():
            skipped["native PDB 없음"] += 1
            continue
        text = native_pdb.read_text(encoding="utf-8", errors="replace")
        resseq = ca_resseq(text, "A")
        muts = mutation_list(native[0][1], design_seq, "A", resseq)
        if muts is None:
            skipped["길이 불일치 - 대응 불가"] += 1
            continue
        if not muts:
            skipped["변이 없음"] += 1
            continue
        # 워커 호출은 일시적으로 실패한다. 격자가 GPU0 을 쥐고 있던 동안 8/8 이
        # 죽었고, 격자가 끝난 뒤 같은 입력이 그대로 성공했다. 그래서 재시도한다.
        # 예외 타입만 세면 진단이 안 된다 - 그때 남은 것은 "RuntimeError" 뿐이었고
        # 그것만으로는 경합인지 입력 오류인지 구분할 수 없었다. 메시지를 남긴다.
        out, last_error = None, ""
        for attempt in range(3):
            try:
                out = client.predict(pdb_text=text, mutations=muts, chain="A")
                break
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
                if attempt < 2:
                    time.sleep(2.0 * (attempt + 1))
        if out is None:
            skipped[f"호출 실패: {last_error[:160]}"] += 1
            continue
        ddg = out.get("additive_ddg_kcal_mol") if isinstance(out, dict) else None
        if ddg is None:
            skipped["additive_ddg 없음"] += 1
            continue
        done.append({**row, "n_mutations": len(muts), "thermomp_additive_ddg": float(ddg)})
        if index % 20 == 0:
            print(f"    {index}/{len(targets)} · 성공 {len(done)}", flush=True)
    return {"results": done, "skipped": dict(skipped)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--thermomp-url", default=_worker_url(18114))
    parser.add_argument("--limit", type=int, default=0,
                        help="ThermoMPNN 을 돌릴 설계 수 상한. 0 이면 전부.")
    parser.add_argument("--skip-thermomp", action="store_true",
                        help="ThermoMPNN 없이 Rosetta/pLDDT/RMSD/변이수만 본다")
    parser.add_argument("--out", default=str(BASE / "stability_annotation_comparison.json"))
    args = parser.parse_args(argv)

    rows = collect_native_designs()
    by_run = collections.Counter(r["run"] for r in rows)
    muts = [r["mutation_median"] for r in rows if r["mutation_median"] is not None]
    print(f"native-백본 설계 {len(rows)} · run/tier {len(by_run)}")
    if muts:
        print(f"  설계당 변이 수 중앙값: {statistics.median(muts):.0f} "
              f"(범위 {min(muts):.0f}~{max(muts):.0f})")
        print(f"  → ThermoMPNN 학습 영역(단일 점변이)과의 간격을 기록한다")

    report = {
        "purpose": "ThermoMPNN·Rosetta·pLDDT·RMSD·변이수를 같은 후보에서 비교",
        "what_cannot_be_checked": "누가 맞는지. de novo 다중 변이 설계의 wet-lab "
                                  "안정성 라벨이 없다.",
        "what_is_checked": ["중복성", "적용 가능성", "불일치", "이상 동작"],
        "scope": "native-백본 설계만. RFD3·BioEmu 백본은 native 대비 변이가 정의되지 않는다.",
        "n_designs": len(rows), "n_run_tiers": len(by_run),
        "mutation_median_over_designs": (round(statistics.median(muts), 1) if muts else None),
        "spurs": "자동 설치하지 않는다. 이 결과를 보고 사람이 결정한다.",
        "code_sha": subprocess.run(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT,
                                   capture_output=True, text=True).stdout.strip(),
        "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    # Rosetta ↔ AF2 상관 (ThermoMPNN 없이도 되는 부분)
    by_bb = collections.defaultdict(list)
    for r in rows:
        by_bb[(r["run"], r["tier"])].append(r)
    pairs = {"relax_vs_plddt": ("relax", "plddt"), "relax_vs_rmsd": ("relax", "rmsd")}
    corr = {}
    for label, (a, b) in pairs.items():
        within = []
        for group in by_bb.values():
            xs = [g[a] for g in group if g[a] is not None and g[b] is not None]
            ys = [g[b] for g in group if g[a] is not None and g[b] is not None]
            rho = spearman(xs, ys)
            if rho is not None:
                within.append(rho)
        if within:
            corr[label] = {"n_groups": len(within),
                           "median_rho": round(statistics.median(within), 4),
                           "frac_negative": round(sum(1 for v in within if v < 0) / len(within), 3)}
    report["within_backbone_correlation"] = corr
    print("\nwithin-backbone 상관 (백본마다 rho 하나)")
    for label, v in corr.items():
        print(f"  {label:18s} 중앙값 {v['median_rho']:+.4f} · 음수 비율 "
              f"{v['frac_negative']} · n={v['n_groups']}")

    if args.skip_thermomp or not args.thermomp_url:
        report["thermomp"] = {"status": "skipped",
                              "why": "--skip-thermomp 또는 RAPID_GPU_HOST 미설정"}
        print("\nThermoMPNN 건너뜀 (URL 없음 또는 --skip-thermomp)")
    else:
        print(f"\nThermoMPNN 실행 ({args.thermomp_url})")
        tm = run_thermomp(rows, url=args.thermomp_url, limit=args.limit)
        got = tm["results"]
        report["thermomp"] = {
            "status": "ok" if got else "no_results",
            "n_scored": len(got), "n_attempted": args.limit or len(rows),
            "skipped": tm["skipped"],
            "note": ("additive_ddg_kcal_mol 은 단일 변이 예측의 합이다. 설계당 변이가 "
                     "중앙값 74 개이므로 에피스테이시스를 무시한 근사이고, 절대값을 "
                     "안정성 추정으로 읽으면 안 된다."),
        }
        print(f"  점수 매김 {len(got)} · 건너뜀 {sum(tm['skipped'].values())}")
        for reason, n in sorted(tm["skipped"].items(), key=lambda kv: -kv[1])[:5]:
            print(f"    {n:4d}x {reason}")

        if got:
            # 중복성·불일치·이상 동작. 누가 맞는지는 알 수 없다.
            pooled = {}
            for label, a, b in (("thermomp_vs_relax", "thermomp_additive_ddg", "relax"),
                                ("thermomp_vs_plddt", "thermomp_additive_ddg", "plddt"),
                                ("thermomp_vs_nmut", "thermomp_additive_ddg", "n_mutations")):
                xs = [g[a] for g in got if g.get(b) is not None]
                ys = [g[b] for g in got if g.get(b) is not None]
                rho = spearman(xs, ys)
                if rho is not None:
                    pooled[label] = round(rho, 4)
            groups = collections.defaultdict(list)
            for g in got:
                groups[(g["run"], g["tier"])].append(g)
            within = {}
            for label, a, b in (("thermomp_vs_relax", "thermomp_additive_ddg", "relax"),
                                ("thermomp_vs_plddt", "thermomp_additive_ddg", "plddt")):
                rhos = []
                for grp in groups.values():
                    r = spearman([x[a] for x in grp], [x[b] for x in grp])
                    if r is not None:
                        rhos.append(r)
                if rhos:
                    within[label] = {"n_groups": len(rhos),
                                     "median_rho": round(statistics.median(rhos), 4),
                                     "frac_negative": round(
                                         sum(1 for v in rhos if v < 0) / len(rhos), 3)}
            ddgs = sorted(g["thermomp_additive_ddg"] for g in got)
            nmuts = sorted(g["n_mutations"] for g in got)
            report["thermomp"].update({
                "pooled_spearman": pooled, "within_backbone_spearman": within,
                "ddg_distribution": {
                    "median": round(statistics.median(ddgs), 3),
                    "p10": round(ddgs[len(ddgs)//10], 3),
                    "p90": round(ddgs[9*len(ddgs)//10], 3),
                    "min": round(ddgs[0], 3), "max": round(ddgs[-1], 3)},
                "n_mutations_distribution": {
                    "median": nmuts[len(nmuts)//2], "min": nmuts[0], "max": nmuts[-1]},
                "anomaly_check": ("변이 수와 ddG 의 상관이 매우 높으면(rho > 0.9) 그 점수는 "
                                  "안정성이 아니라 변이 개수를 재고 있을 가능성이 크다. "
                                  f"관측값 rho = {pooled.get('thermomp_vs_nmut')}"),
            })
            print(f"  pooled: {pooled}")
            print(f"  within-backbone: {within}")
            print(f"  ddG 분포 중앙값 {statistics.median(ddgs):.2f} "
                  f"(범위 {ddgs[0]:.1f}~{ddgs[-1]:.1f})")
            if pooled.get("thermomp_vs_nmut") is not None and pooled["thermomp_vs_nmut"] > 0.9:
                print("  ← 변이 수와 거의 완전 상관: 안정성이 아니라 개수를 재고 있다")

    Path(args.out).write_text(json.dumps(report, indent=2, ensure_ascii=False),
                              encoding="utf-8")
    print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
