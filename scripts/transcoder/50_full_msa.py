#!/usr/bin/env python3
"""Step 7 — 24 타겟의 MSA 를 한 번씩 만든다. target 수준 산출물이다.

동결 문서: `docs/specs/rapid-v2-multisource-validation-freeze.md` §8

MSA 는 backbone 생성기와 무관하므로 **source 마다 다시 돌리지 않는다.** 타겟당
한 번 만들고 그 conservation mask 를 RFD3 와 BioEmu 에 동일하게 매핑한다.

설정은 배포 기본값을 `PipelineRequest` 에서 직접 읽는다. 여기 상수를 다시 적으면
배포와 갈라지고, 그것이 이번 검증 전체가 존재하는 이유였다.

재개 가능하다. 타겟당 약 42 분이고 24 개면 약 17 시간이므로, 중간에 끊겨도
이미 만든 A3M 은 다시 만들지 않는다 - manifest 의 sha256 과 대조해 건너뛴다.

A3M 은 `.gitignore` 에 걸려 있어 저장소에 들어가지 않는다. manifest 에 해시와
품질 지표만 남긴다 (`fold_artifact_archive.json` 과 같은 방식).

**하지 않는 것**: threshold 변경 · 타겟 선정 변경 · tier 변경 · 후보 수 변경 ·
품질이 나쁜 타겟 골라내기. `usable_hits < 10` 은 동결된 feasibility 결과이고
실패가 아니다.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BASE = PROJECT_ROOT / "public_data" / "benchmark" / "gate0"
MSA_DIR = BASE / "msa"
OUT = BASE / "full_msa_manifest.json"
sys.path.insert(0, str(PROJECT_ROOT / "pipeline-mcp" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

#: 배포 경로가 읽는 응답 키. pilot 과 같은 값이어야 하고 테스트가 대조한다.
A3M_RESPONSE_KEY = "a3m_gz_b64"
#: pilot 과 동일한 검색 설정. 여기서 고르지 않는다.
TARGET_DB, MAX_SEQS, THREADS, USE_GPU = "uniref90", 3000, 4, False

COHORTS = (("calibration_v2", "calibration_v2_targets.json"),
           ("confirmatory", "masked_holdout_targets.json"))


def run_provenance() -> dict:
    """실행 시점에 **한 번** 잡는다.

    `_write` 마다 `git rev-parse HEAD` 를 다시 읽으면, 17 시간 실행 중에 다른
    커밋이 생기면 타겟마다 다른 SHA 가 박힌다. 그러면 "무슨 코드로 24 개를
    돌렸는가" 에 답할 수 없다.

    HEAD 만으로는 부족하다 - 작업 트리가 더러우면 HEAD 가 실제 실행 코드가
    아니다. 그래서 두 스크립트의 내용 해시도 함께 남긴다.
    """
    def git(*a):
        return subprocess.run(["git", *a], cwd=PROJECT_ROOT,
                              capture_output=True, text=True).stdout.strip()

    here = Path(__file__).resolve().parent
    scripts = {}
    for name in ("50_full_msa.py", "48_msa_pilot.py"):
        f = here / name
        if f.exists():
            scripts[name] = hashlib.sha256(f.read_bytes()).hexdigest()
    dirty = git("status", "--porcelain", "--", "scripts/transcoder", "pipeline-mcp/src")
    return {
        "code_sha": git("rev-parse", "HEAD"),
        "code_sha_short": git("rev-parse", "--short=7", "HEAD"),
        "pinned_at_start": True,
        "worktree_clean_for_code_paths": not dirty,
        # `git()` 이 .strip() 을 하므로 첫 줄의 선행 공백이 사라진다.
        # 고정 오프셋으로 자르면 한 칸 밀린다 - 공백 기준으로 나눈다.
        "dirty_paths": [l.split(maxsplit=1)[-1] for l in dirty.splitlines()
                        if l.split(maxsplit=1)] if dirty else [],
        "script_sha256": scripts,
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def deployment_defaults() -> dict:
    """동결 §1 의 conservation 설정을 배포 기본값에서 읽는다."""
    from pipeline_mcp.models import PipelineRequest

    def d(name):
        f = PipelineRequest.__dataclass_fields__[name]
        return f.default if f.default is not dataclasses.MISSING else f.default_factory()

    return {"conservation_tiers": list(d("conservation_tiers")),
            "conservation_mode": d("conservation_mode"),
            "conservation_weighting": d("conservation_weighting")}


_PILOT = None


def pilot_mod():
    """48_ 의 구현을 그대로 쓴다. 다시 구현하면 서열과 지표가 갈라진다."""
    global _PILOT
    if _PILOT is None:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "msa_pilot", Path(__file__).resolve().parent / "48_msa_pilot.py")
        _PILOT = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_PILOT)
    return _PILOT


def query_sequence(pdb_path: str) -> str:
    return pilot_mod().query_sequence(pdb_path)


def targets() -> list[dict]:
    out = []
    for cohort, fname in COHORTS:
        d = json.loads((BASE / fname).read_text(encoding="utf-8"))
        for t in d["selected"]:
            out.append({"cohort": cohort, "domain": t["domain"],
                        "stratum": t["stratum"], "length_aa": t["length"],
                        "pdb": t["pdb"], "superfamily": t["superfamily"]})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=None)
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--only", default=None, help="쉼표로 구분한 도메인 (진단용)")
    args = ap.parse_args()

    host = os.environ.get("RAPID_GPU_HOST", "")
    url = args.url or f"http://{host}:18106"
    from pipeline_mcp.bio.a3m import compute_conservation, decode_a3m_gz_b64, msa_quality
    from pipeline_mcp.clients.local_http import LocalHTTPMMseqsClient

    prov = run_provenance()
    cons_cfg = deployment_defaults()
    rows = targets()
    if args.only:
        keep = {x.strip() for x in args.only.split(",")}
        rows = [r for r in rows if r["domain"] in keep]

    prev = {}
    out_path = Path(args.out)
    if out_path.exists():
        prev = {e["domain"]: e for e in
                json.loads(out_path.read_text(encoding="utf-8")).get("targets", [])}

    MSA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"타겟 {len(rows)} · target_db={TARGET_DB} max_seqs={MAX_SEQS} "
          f"threads={THREADS} use_gpu={USE_GPU}")
    print(f"conservation {cons_cfg}")
    print(f"A3M -> {MSA_DIR}  (gitignored)")
    print(f"code {prov['code_sha_short']} · 코드 경로 작업트리 "
          f"{'clean' if prov['worktree_clean_for_code_paths'] else 'DIRTY ' + str(prov['dirty_paths'])}\n")

    client = LocalHTTPMMseqsClient(base_url=url, token=None, timeout_s=7200.0)
    results: list[dict] = []
    for i, row in enumerate(rows, 1):
        domain = row["domain"]
        a3m_path = MSA_DIR / domain / "result.a3m"
        entry = dict(row)
        entry["a3m_path"] = str(a3m_path.relative_to(PROJECT_ROOT))

        # ---- 재개: 이미 만든 것은 다시 만들지 않는다 ----
        old = prev.get(domain)
        if a3m_path.exists() and old and old.get("a3m_sha256"):
            digest = hashlib.sha256(a3m_path.read_bytes()).hexdigest()
            if digest == old["a3m_sha256"]:
                print(f"[{i}/{len(rows)}] {domain:9s} 건너뜀 (해시 일치)", flush=True)
                results.append(old)
                continue
            print(f"[{i}/{len(rows)}] {domain:9s} 해시 불일치 - 다시 만든다", flush=True)

        seq = query_sequence(row["pdb"])
        print(f"[{i}/{len(rows)}] {domain:9s} {len(seq):>4} aa · {row['cohort']} · 시작",
              flush=True)
        started = time.time()
        try:
            resp = client.search(query_fasta=f">{domain}\n{seq}\n", target_db=TARGET_DB,
                                 threads=THREADS, use_gpu=USE_GPU,
                                 return_a3m=True, max_seqs=MAX_SEQS)
            entry["endpoint_status"] = "ok"
            entry["response_keys"] = sorted(resp)
            blob = resp.get(A3M_RESPONSE_KEY)
            entry["a3m_key_present"] = bool(blob)
            a3m = ""
            if blob:
                try:
                    a3m = decode_a3m_gz_b64(str(blob))
                    entry["decode_ok"] = True
                except Exception as exc:
                    entry["decode_ok"] = False
                    entry["decode_error"] = f"{type(exc).__name__}: {exc}"[:200]
            for k in ("hit_count", "query_length", "query_id"):
                if k in resp:
                    entry[k] = resp[k]
            entry["query_consistent"] = {
                "sent_length": len(seq),
                "returned_length": resp.get("query_length"),
                "id_match": str(resp.get("query_id") or "").strip() in ("", domain),
                "length_match": (resp.get("query_length") is None
                                 or int(resp["query_length"]) == len(seq)),
            }
            entry["a3m_bytes"] = len(a3m)
            if a3m.strip():
                a3m_path.parent.mkdir(parents=True, exist_ok=True)
                a3m_path.write_text(a3m, encoding="utf-8")
                entry["a3m_sha256"] = hashlib.sha256(a3m_path.read_bytes()).hexdigest()
                q = msa_quality(a3m)
                entry["msa_quality"] = {
                    k: q.get(k) for k in ("usable_hits", "coverage", "depth",
                                          "full_length_fraction", "warnings",
                                          "query_length")}
                # 동결 §8 이 쓰는 네 값. coverage/depth 는 백분위 dict 이므로
                # p50 을 꺼낸다 - 코드의 경고 로직과 같은 값이다.
                entry["quality_medians"] = pilot_mod().quality_medians(entry["msa_quality"])
                # conservation mask 는 이 A3M 의 결정적 함수다. 지금 계산해 두면
                # Step 8 이 MSA 를 다시 돌리지 않아도 된다.
                c = compute_conservation(
                    a3m, tiers=cons_cfg["conservation_tiers"],
                    mode=cons_cfg["conservation_mode"], weights=None)
                entry["conservation"] = {
                    "query_length": c.query_length,
                    "tiers": {str(t): len(p)
                              for t, p in c.fixed_positions_by_tier.items()},
                    "fixed_positions_sha256": {
                        str(t): hashlib.sha256(json.dumps(p).encode()).hexdigest()
                        for t, p in c.fixed_positions_by_tier.items()},
                    "query_length_matches_sequence": c.query_length == len(seq),
                }
            else:
                entry["classification"] = "MSA_INFEASIBLE"
        except Exception as exc:
            entry["endpoint_status"] = "failed"
            entry["error"] = f"{type(exc).__name__}: {exc}"[:300]
            entry["classification"] = "MSA_INFEASIBLE"
        entry["wall_seconds"] = round(time.time() - started, 1)

        # ---- 동결된 §8 규칙만 적용한다. 새 규칙을 만들지 않는다. ----
        if "classification" not in entry:
            hits = (entry.get("msa_quality") or {}).get("usable_hits")
            entry["classification"] = ("MSA_INSUFFICIENT_DEPTH"
                                       if isinstance(hits, int) and hits < 10 else "OK")
        m = entry.get("quality_medians") or {}
        print(f"    {entry['wall_seconds']}s · hits={entry.get('hit_count', '-')} · "
              f"usable={m.get('usable_hits', '-')} · "
              f"cov={m.get('median_coverage', '-')} · {entry['classification']}",
              flush=True)
        results.append(entry)

        # 매 타겟마다 저장한다. 17 시간짜리 실행에서 마지막에만 쓰면 다 잃는다.
        _write(out_path, results, rows, cons_cfg, prov)

    _write(out_path, results, rows, cons_cfg, prov)
    _summary(results)
    print(f"\nwrote {out_path}")
    return 0


def _write(out_path: Path, results: list[dict], rows: list[dict],
           cons_cfg: dict, prov: dict) -> None:
    by_class: dict[str, int] = {}
    for e in results:
        by_class[e.get("classification", "?")] = by_class.get(e.get("classification", "?"), 0) + 1
    out_path.write_text(json.dumps({
        "purpose": "Step 7 - 24 타겟의 target 수준 MSA. source 마다 다시 돌리지 않는다.",
        "freeze_doc": "docs/specs/rapid-v2-multisource-validation-freeze.md",
        "settings": {"target_db": TARGET_DB, "max_seqs": MAX_SEQS,
                     "threads": THREADS, "use_gpu": USE_GPU,
                     "a3m_response_key": A3M_RESPONSE_KEY},
        "conservation": cons_cfg,
        "conservation_note": "weighting=none 이므로 cluster TSV 가 필요하지 않다",
        "a3m_note": "*.a3m 는 gitignored 다. 해시와 품질 지표만 남긴다.",
        "not_done": ["threshold 변경", "타겟 선정 변경", "tier 변경",
                     "후보 수 변경", "품질로 타겟 골라내기"],
        "n_planned": len(rows), "n_done": len(results),
        "by_classification": by_class,
        "targets": results,
        "run_provenance": prov,
        "code_sha": prov["code_sha"],
        "updated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }, ensure_ascii=False, indent=2), encoding="utf-8")


def _summary(results: list[dict]) -> None:
    def f(v, fmt="{:.3f}"):
        return fmt.format(v) if isinstance(v, (int, float)) else "-"
    print(f"\n{'코호트':14s}{'타겟':10s}{'aa':>5}{'wall':>8}{'hits':>7}"
          f"{'usable':>8}{'cover':>7}{'depth':>8}{'full':>7}  판정")
    for e in results:
        m = e.get("quality_medians") or {}
        print(f"  {e['cohort']:12s}{e['domain']:10s}{e['length_aa']:>5}"
              f"{e.get('wall_seconds', 0):>8.0f}{str(e.get('hit_count', '-')):>7}"
              f"{f(m.get('usable_hits'), '{:.0f}'):>8}{f(m.get('median_coverage')):>7}"
              f"{f(m.get('median_depth'), '{:.1f}'):>8}"
              f"{f(m.get('full_length_fraction')):>7}  {e['classification']}")
    total = sum(e.get("wall_seconds", 0) for e in results)
    print(f"\n합계 벽시계 {total/3600:.1f} 시간 · 타겟 {len(results)}")
    for e in results:
        w = (e.get("msa_quality") or {}).get("warnings") or []
        if w:
            print(f"  {e['domain']} warnings: {w}")


if __name__ == "__main__":
    raise SystemExit(main())
