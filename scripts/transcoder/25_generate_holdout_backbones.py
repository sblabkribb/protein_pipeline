#!/usr/bin/env python3
"""홀드아웃 타겟의 백본을 만든다 (1 단계).

왜 RFD3 에서 멈추는가
---------------------
게이트 0 의 표준 실행은 백본당 서열 16 개를 만들고 전부 접는다. 홀드아웃은
백본당 24 폴드 격자를 따로 채우므로, 표준 실행을 그대로 쓰면 16 + 24 를 낸다.
그래서 `stop_after="rfd3"` 로 백본만 만든다. ColabFold 를 건드리지 않으므로
다른 폴딩 작업과 경합하지 않는다.

구성
----
타겟당 6 개다: native 1 개(CATH 도메인 구조 자체) + RFD3 5 개. 개발에서 가장
흔한 구성과 같다. 근거는 holdout_targets.json 의 backbone_plan 에 있다.

실패 처리
---------
RFD3 가 5 개를 못 만들거나 수용 기준에 미달하면 그 타겟을 예비 타겟으로
교체한다. 선정 목록을 다시 뽑지 않는다 - 다시 뽑으면 freeze 가 무의미해진다.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(PROJECT_ROOT / "pipeline-mcp" / "src"))

from rapid_sr.gate0_request import build_gate0_request  # noqa: E402
from rapid_sr.protocol import protocol_fingerprint  # noqa: E402

BASE = PROJECT_ROOT / "public_data" / "benchmark" / "gate0"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--holdout", default=str(BASE / "holdout_targets.json"))
    parser.add_argument("--out", default=str(BASE / "holdout_generation.json"))
    parser.add_argument("--output-root", default="/opt/protein_pipeline/outputs")
    parser.add_argument("--seed", type=int, default=20260907)
    parser.add_argument("--env-file", default="/opt/protein_pipeline/pipeline-mcp/.env")
    parser.add_argument("--use-reserve", type=int, default=0,
                        help="선정 타겟이 실패했을 때 쓸 예비 개수. 기본 0 - "
                             "실패 목록을 먼저 보고 사람이 정한다.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    env_file = Path(args.env_file)
    if env_file.exists():
        from dotenv import load_dotenv
        load_dotenv(str(env_file), override=False)
        print(f"env_file={env_file}")

    spec = json.loads(Path(args.holdout).read_text(encoding="utf-8"))
    plan = spec["backbone_plan"]
    targets = list(spec["selected"])
    if args.use_reserve:
        targets += spec["reserve"][: args.use_reserve]

    report = {
        "phase": "1_backbone_generation",
        "holdout_spec": str(Path(args.holdout).relative_to(PROJECT_ROOT)),
        "composition": dict(plan["composition"]),
        "stop_after": "rfd3",
        "start_from": "rfd3",
        "why_skip_msa": (
            "RFD3 는 타겟 구조에 조건을 걸고 MSA 를 읽지 않는다. 첫 시도에서 "
            "mmseqs_msa 단계에 50 분 동안 멈춰 있었고 (mmseqs 프로세스는 없었다) "
            "MSA 산출물은 비어 있었다. 백본만 만드는 데 MSA 는 낭비다."
        ),
        "why_stop_after_rfd3": (
            "격자를 따로 채우므로 표준 실행의 16 폴드를 내지 않는다. "
            "ColabFold 를 쓰지 않아 다른 폴딩과 경합하지 않는다."
        ),
        "seed": args.seed,
        "protocol_fingerprint": protocol_fingerprint(),
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "runs": [],
    }

    print(f"홀드아웃 {len(targets)} 타겟 · 타겟당 native 1 + RFD3 "
          f"{plan['composition']['rfd3']}")
    if args.dry_run:
        for row in targets:
            print(f"  [dry-run] {row['domain']:10s} {row['length']:4d} 잔기 "
                  f"· {row['pdb']}")
        return 0

    from pipeline_mcp.app import build_runner  # noqa: E402
    runner = build_runner()

    want = int(plan["composition"]["rfd3"])
    output_root = Path(args.output_root)

    def designs_for(domain: str) -> int:
        return len(list((output_root / f"holdout_{domain}_rfd3" / "rfd3"
                         / "designs").glob("*.pdb")))

    out_path = Path(args.out)
    for index, row in enumerate(targets, start=1):
        run_id = f"holdout_{row['domain']}_rfd3"
        # 이미 다 만든 타겟을 다시 돌리면 성공한 백본을 덮어쓸 위험만 있다.
        have = designs_for(row["domain"])
        if have >= want:
            print(f"[{index}/{len(targets)}] {run_id}: designs {have} 이미 있음, "
                  f"건너뜀", flush=True)
            report["runs"].append({"domain": row["domain"], "stratum": row["stratum"],
                                   "length": row["length"], "run_id": run_id,
                                   "status": "ok", "n_designs": have,
                                   "skipped": True})
            continue
        pdb_text = Path(row["pdb"]).read_text(encoding="utf-8", errors="replace")
        request = build_gate0_request(pdb_text, "rfd3", seed=args.seed,
                                      stop_after="rfd3", start_from="rfd3")
        record = {"domain": row["domain"], "stratum": row["stratum"],
                  "length": row["length"], "run_id": run_id,
                  "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
        started = time.time()
        print(f"[{index}/{len(targets)}] {run_id} ({row['length']} 잔기)", flush=True)
        try:
            runner.run(request, run_id=run_id)
        except Exception as exc:
            record["error"] = f"{type(exc).__name__}: {exc}"
            print(f"    실패: {record['error']}", flush=True)
        # runner 가 ok 를 돌려줘도 designs 가 없을 수 있다. 실제로 2iayA00 은
        # state=completed 인데 designs 가 0 이었고, 오류는 summary.json 의
        # errors 에만 있었다. 그래서 파일 수로 판정한다.
        record["n_designs"] = designs_for(row["domain"])
        record["status"] = "ok" if record["n_designs"] >= want else "failed"
        if record["status"] == "failed" and "error" not in record:
            record["error"] = (f"designs {record['n_designs']}/{want} - runner 는 "
                               f"완료를 보고했다. summary.json 의 errors 를 본다.")
            print(f"    부족: {record['error']}", flush=True)
        record["elapsed_s"] = round(time.time() - started, 1)
        report["runs"].append(record)
        # run 마다 기록해서 중간에 죽어도 복구된다.
        out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False),
                            encoding="utf-8")

    report["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    ok = sum(1 for r in report["runs"] if r["status"] == "ok")
    report["n_ok"] = ok
    report["n_failed"] = len(report["runs"]) - ok
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False),
                        encoding="utf-8")
    print(f"\n완료 · ok {ok}/{len(report['runs'])} · {out_path}")
    if report["n_failed"]:
        print("실패한 타겟은 예비로 교체한다: --use-reserve N")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
