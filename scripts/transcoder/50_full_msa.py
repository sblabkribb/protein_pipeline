#!/usr/bin/env python3
"""Step 7 — 24 타겟의 MSA 를 한 번씩 만든다. target 수준 산출물이다.

동결 문서: `docs/specs/rapid-v2-multisource-validation-freeze.md` §8

MSA 는 backbone 생성기와 무관하므로 **source 마다 다시 돌리지 않는다.** 타겟당
한 번 만들고 그 conservation mask 를 RFD3 와 BioEmu 에 동일하게 매핑한다.

설정은 배포 기본값을 `PipelineRequest` 에서 직접 읽는다. 여기 상수를 다시 적으면
배포와 갈라지고, 그것이 이번 검증 전체가 존재하는 이유였다.

재개 가능하다. 타겟당 약 40 분이므로 중간에 끊겨도 이미 만든 A3M 은 다시 만들지
않는다. 재개 기준은 manifest 가 아니라 **A3M 산출물 자체**다 - 그래야 다른
manifest(예: 동시성 probe)가 만든 A3M 도 그대로 재사용된다. 품질과 보존도
마스크는 A3M 의 결정적 함수이므로 다시 계산해도 같은 값이고, 런타임 값
(hit_count · wall_seconds)만 이전 기록에서 가져온다.

`--workers N` 으로 타겟 간 병렬 실행이 된다. **per-job 파라미터는 하나도 바뀌지
않는다** - target_db · max_seqs · threads · use_gpu 를 그대로 넘기므로 배포
일치와 결정성에 영향이 없고, 제약은 서버 메모리뿐이다.

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
import threading
from concurrent.futures import ThreadPoolExecutor
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

#: `--cohorts` 로만 닿는 추가 코호트. `COHORTS` 기본값은 건드리지 않는다 - 동결
#: v2 흐름(24 타겟)이 그 기본값에 걸려 있으므로, 인자를 주지 않은 호출은 이
#: 변경 전과 같은 목록·같은 출력이어야 한다.
OPTIONAL_COHORTS = {"holdout_grid": "holdout_targets.json"}

#: 코호트마다 파일 안의 **어느 목록**을 읽는가. 기본은 `selected` 이고 동결 v2
#: 두 코호트가 그것을 읽는다.
#:
#: `holdout_targets.json` 은 다르다. `selected` 는 동결 전 희망 목록이고, 선정에
#: 실패한 4 개가 `resolved.rule` 에 따라 같은 stratum 의 reserve 로 교체됐다
#: (1sh6A02←2jo7A00 · 5xpdA02←1vprA02 · 3f2pA01←2pgsA03 · 5pc8A00←2iayA00).
#: 실제로 백본이 만들어진 격자는 `resolved.targets` 다. `selected` 를 읽으면 fold
#: 가 없는 4 개를 가져오고 fold 가 있는 4 개를 놓쳐 코호트의 1/3 이 조용히 빠진다.
COHORT_TARGET_KEY = {"holdout_grid": ("resolved", "targets")}
DEFAULT_TARGET_KEY = ("selected",)


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


def resolve_cohorts(spec: str | None) -> tuple[tuple[str, str], ...]:
    """`--cohorts` 문자열을 (코호트, 파일) 목록으로 바꾼다.

    타겟 선정을 바꾸는 것이 아니다 - 이미 동결된 **다른** 목록을 옵트인으로
    가리킬 뿐이다. 인자가 없으면 `COHORTS` 를 그대로 돌려준다.
    """
    if not spec:
        return COHORTS
    known = {**dict(COHORTS), **OPTIONAL_COHORTS}
    picked = []
    for name in (x.strip() for x in spec.split(",")):
        if not name:
            continue
        if name not in known:
            raise SystemExit(f"알 수 없는 코호트 {name!r} · 가능: {sorted(known)}")
        picked.append((name, known[name]))
    if not picked:
        raise SystemExit("--cohorts 가 비어 있다")
    return tuple(picked)


def check_out_path(out_path: Path, cohorts: tuple[tuple[str, str], ...]) -> None:
    """기본 코호트가 아니면 동결 v2 manifest 에 쓰지 못하게 막는다.

    `--out` 기본값은 `full_msa_manifest.json` 이고 그것은 동결된 v2 multisource
    validation 의 산출물이다. `--cohorts` 만 주고 `--out` 을 잊으면 그것을
    덮어쓴다 - 되돌릴 수 없으므로 코드에서 막는다.
    """
    if tuple(cohorts) != COHORTS and out_path.resolve() == OUT.resolve():
        # 순서까지 본다. 코호트 순서가 바뀌면 manifest 의 타겟 순서가 바뀌어
        # 동결 산출물과 다른 바이트가 되므로 그것도 덮어쓰기다.
        raise SystemExit(
            f"{OUT.name} 은 동결된 v2 산출물이라 읽기 전용이다. 기본 코호트를 "
            f"기본 순서 {[c for c, _ in COHORTS]} 로 돌릴 때만 그 파일에 쓴다 - "
            f"요청은 {[c for c, _ in cohorts]} 이므로 --out 을 따로 지정해야 한다."
        )


def targets(cohorts: tuple[tuple[str, str], ...] | None = None) -> list[dict]:
    """인자를 주지 않으면 `COHORTS` 그대로다. 기존 호출의 동작은 바뀌지 않는다."""
    out = []
    for cohort, fname in (cohorts or COHORTS):
        d = json.loads((BASE / fname).read_text(encoding="utf-8"))
        node = d
        for key in COHORT_TARGET_KEY.get(cohort, DEFAULT_TARGET_KEY):
            node = node[key]
        for t in node:
            out.append({"cohort": cohort, "domain": t["domain"],
                        "stratum": t["stratum"], "length_aa": t["length"],
                        "pdb": t["pdb"], "superfamily": t["superfamily"]})
    return out


def finish(entry: dict) -> dict:
    """동결된 8 절 규칙만 적용한다. 새 규칙을 만들지 않는다."""
    if "classification" not in entry:
        hits = (entry.get("quality_medians") or {}).get("usable_hits")
        entry["classification"] = ("MSA_INSUFFICIENT_DEPTH"
                                   if isinstance(hits, int) and hits < 10 else "OK")
    return entry

def measure(a3m: str, seq_len: int, cons_cfg: dict) -> dict:
    """A3M 에서 품질과 보존도 마스크를 낸다. 파일만 있으면 재현된다."""
    from pipeline_mcp.bio.a3m import compute_conservation, msa_quality

    q = msa_quality(a3m)
    out = {"msa_quality": {k: q.get(k) for k in
                           ("usable_hits", "coverage", "depth",
                            "full_length_fraction", "warnings", "query_length")}}
    out["quality_medians"] = pilot_mod().quality_medians(out["msa_quality"])
    c = compute_conservation(a3m, tiers=cons_cfg["conservation_tiers"],
                             mode=cons_cfg["conservation_mode"], weights=None)
    out["conservation"] = {
        "query_length": c.query_length,
        "tiers": {str(t): len(v) for t, v in c.fixed_positions_by_tier.items()},
        "fixed_positions_sha256": {
            str(t): hashlib.sha256(json.dumps(v).encode()).hexdigest()
            for t, v in c.fixed_positions_by_tier.items()},
        "query_length_matches_sequence": c.query_length == seq_len,
    }
    return out

def from_artifact(row: dict, seq_len: int, cons_cfg: dict,
                  prev: dict, msa_dir: Path | None = None) -> dict | None:
    """A3M 파일이 이미 있으면 그것으로 재개한다.

    manifest 가 아니라 **산출물**을 기준으로 삼는다. 그래야 probe 가 만든
    A3M 도, 다른 manifest 에 적힌 A3M 도 그대로 재사용된다. 품질과 보존도는
    파일의 결정적 함수이므로 다시 계산해도 같은 값이다.
    """
    msa_dir = msa_dir or MSA_DIR
    path = msa_dir / row["domain"] / "result.a3m"
    if not path.exists():
        return None
    raw = path.read_bytes()
    text = raw.decode("utf-8", errors="replace")
    if not text.strip():
        return None
    entry = dict(row)
    try:
        entry["a3m_path"] = str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        entry["a3m_path"] = str(path)
    entry["a3m_bytes"] = len(text)
    entry["a3m_sha256"] = hashlib.sha256(raw).hexdigest()
    entry["resumed_from_file"] = True
    entry.update(measure(text, seq_len, cons_cfg))
    # 런타임 값은 파일에서 나오지 않는다. 이전 기록이 있으면 가져온다.
    old = prev.get(row["domain"]) or {}
    for k in ("hit_count", "wall_seconds", "endpoint_status", "query_consistent",
              "response_keys", "decode_ok", "a3m_key_present", "query_id",
              "query_length"):
        if k in old:
            entry[k] = old[k]
    entry.setdefault("endpoint_status", "resumed")
    if old.get("a3m_sha256") and old["a3m_sha256"] != entry["a3m_sha256"]:
        entry["sha_changed_since"] = old["a3m_sha256"]
    return finish(entry)



def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=None)
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--only", default=None, help="쉼표로 구분한 도메인 (진단용)")
    ap.add_argument("--cohorts", default=None,
                    help="쉼표로 구분한 코호트. 생략하면 동결 기본값 "
                         f"{[c for c, _ in COHORTS]} · 추가 가능 "
                         f"{sorted(OPTIONAL_COHORTS)}. 바꾸면 --out 도 바꿔야 한다.")
    ap.add_argument("--workers", type=int, default=1,
                    help="타겟 간 동시 실행 수. per-job 설정은 바뀌지 않는다.")
    args = ap.parse_args()

    host = os.environ.get("RAPID_GPU_HOST", "")
    url = args.url or f"http://{host}:18106"
    from pipeline_mcp.bio.a3m import compute_conservation, decode_a3m_gz_b64, msa_quality
    from pipeline_mcp.clients.local_http import LocalHTTPMMseqsClient

    prov = run_provenance()
    cons_cfg = deployment_defaults()
    cohorts = resolve_cohorts(args.cohorts)
    rows = targets(cohorts)
    if args.only:
        keep = {x.strip() for x in args.only.split(",")}
        rows = [r for r in rows if r["domain"] in keep]

    # 이전 실행 기록을 여러 manifest 에서 모은다. probe 와 본 실행이 서로 다른
    # 파일에 쓰므로, 하나만 보면 이미 만든 A3M 을 다시 만든다.
    out_path = Path(args.out)
    check_out_path(out_path, cohorts)
    prev: dict[str, dict] = {}
    for cand in (BASE / "full_msa_manifest.json",
                 BASE / "msa_probe_concurrency.json", out_path):
        if cand.exists():
            for e in json.loads(cand.read_text(encoding="utf-8")).get("targets", []):
                if e.get("domain"):
                    prev.setdefault(e["domain"], e)

    MSA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"타겟 {len(rows)} · target_db={TARGET_DB} max_seqs={MAX_SEQS} "
          f"threads={THREADS} use_gpu={USE_GPU}")
    print(f"conservation {cons_cfg}")
    print(f"A3M -> {MSA_DIR}  (gitignored)")
    print(f"code {prov['code_sha_short']} · 코드 경로 작업트리 "
          f"{'clean' if prov['worktree_clean_for_code_paths'] else 'DIRTY ' + str(prov['dirty_paths'])}\n")

    client = LocalHTTPMMseqsClient(base_url=url, token=None, timeout_s=7200.0)
    results: list[dict] = []
    lock = threading.Lock()
    done = [0]

    def process(row: dict) -> dict:
        domain = row["domain"]
        seq = query_sequence(row["pdb"])

        resumed = from_artifact(row, len(seq), cons_cfg, prev)
        if resumed is not None:
            with lock:
                done[0] += 1
                print(f"[{done[0]}/{len(rows)}] {domain:9s} 건너뜀 (A3M 존재, "
                      f"품질 재계산) · {resumed['classification']}", flush=True)
            return resumed

        entry = dict(row)
        a3m_path = MSA_DIR / domain / "result.a3m"
        entry["a3m_path"] = str(a3m_path.relative_to(PROJECT_ROOT))
        with lock:
            print(f"[  ../{len(rows)}] {domain:9s} {len(seq):>4} aa · "
                  f"{row['cohort']} · 시작", flush=True)
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
                entry.update(measure(a3m, len(seq), cons_cfg))
            else:
                entry["classification"] = "MSA_INFEASIBLE"
        except Exception as exc:
            entry["endpoint_status"] = "failed"
            entry["error"] = f"{type(exc).__name__}: {exc}"[:300]
            entry["classification"] = "MSA_INFEASIBLE"
        entry["wall_seconds"] = round(time.time() - started, 1)
        finish(entry)
        m = entry.get("quality_medians") or {}
        with lock:
            done[0] += 1
            print(f"[{done[0]}/{len(rows)}] {domain:9s} {entry['wall_seconds']}s · "
                  f"hits={entry.get('hit_count', '-')} · "
                  f"usable={m.get('usable_hits', '-')} · "
                  f"cov={m.get('median_coverage', '-')} · {entry['classification']}",
                  flush=True)
        return entry

    if args.workers <= 1:
        for row in rows:
            results.append(process(row))
            _write(out_path, results, rows, cons_cfg, prov, cohorts)
    else:
        # 타겟 간 병렬. per-job 파라미터는 하나도 바뀌지 않는다 - 배포 일치와
        # 결정성에 영향이 없고, 제약은 서버 메모리뿐이다.
        print(f"타겟 간 병렬 {args.workers} worker (per-job 설정 불변)\n")
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            for entry in pool.map(process, rows):
                results.append(entry)
                with lock:
                    _write(out_path, results, rows, cons_cfg, prov, cohorts)

    _write(out_path, results, rows, cons_cfg, prov, cohorts)
    _summary(results)
    print(f"\nwrote {out_path}")
    return 0


def _write(out_path: Path, results: list[dict], rows: list[dict],
           cons_cfg: dict, prov: dict,
           cohorts: tuple[tuple[str, str], ...] = COHORTS) -> None:
    by_class: dict[str, int] = {}
    for e in results:
        by_class[e.get("classification", "?")] = by_class.get(e.get("classification", "?"), 0) + 1
    # 기본 코호트가 아니면 v2 provenance 를 그대로 찍지 않는다 - 그러면 우리
    # 산출물이 남의 동결 문서를 가리킨다. 기본 경로에서는 `extra` 가 비어 있어
    # 출력 바이트가 한 글자도 바뀌지 않는다 (키 순서 포함).
    extra: dict = {}
    if tuple(cohorts) != COHORTS:
        names = [c for c, _ in cohorts]
        extra = {"purpose": f"{names} 코호트의 target 수준 MSA. --cohorts 로 지정됐다.",
                 "freeze_doc": "docs/specs/2026-09-10-surrogate-rapid-2d-gate-design.md",
                 "cohorts": names}
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
        **extra,
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
