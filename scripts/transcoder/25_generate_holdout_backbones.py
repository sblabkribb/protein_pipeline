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
#: 재번호한 타겟을 두는 자리. RFD3 에 준 것과 native 기준 구조가 같아야 한다.
STAGED = BASE / "holdout_targets_pdb"


def first_model_only(pdb_text: str) -> tuple[str, int]:
    """다중 모델 파일에서 첫 모델만 남긴다.

    CATH 파일 중 일부는 NMR 앙상블이다. 홀드아웃 18 타겟 중 4 개가 그렇고
    (1tm9A00 26 모델, 2jokA01 20 모델, 2jo7A00 10 모델, 2yruA01 20 모델),
    1tm9A00 은 137 잔기인데 ATOM 이 56,836 줄이다. 모델 구분자를 잃으면 같은
    잔기가 26 번 겹쳐 한 사슬이 되고, RFD3 는 UnindexFlaggedTokens 단계에서
    죽는다. 2jo7A00 이 RMSD 수용 게이트에서 15 개 중 14 개를 기각당한 것도
    앙상블에 맞춰 재려 했기 때문이고, 임계값 문제가 아니었다.

    선정 기준의 길이 계산은 잔기번호의 집합을 세므로 앙상블도 정상 단일 사슬로
    보였다. 그래서 적격성으로는 걸러지지 않았다 - 여기서 처리한다.
    """
    lines = pdb_text.splitlines()
    n_models = sum(1 for line in lines if line.startswith("MODEL "))
    if n_models <= 1:
        return pdb_text, n_models
    kept, inside = [], False
    for line in lines:
        if line.startswith("MODEL "):
            if inside:
                break
            inside = True
            continue
        if line.startswith("ENDMDL"):
            break
        if inside:
            kept.append(line)
        else:
            kept.append(line)  # 헤더는 남긴다
    return "\n".join(kept) + "\n", n_models


def drop_ca_less_atoms(pdb_text: str) -> str:
    """CA 가 없는 잔기의 ATOM 줄과 HETATM 을 버린다. 나머지는 그대로 둔다.

    RFD3 는 contig 를 잔기번호 범위 하나로 받는데, 원자는 있고 CA 는 없는 잔기가
    번호에 끼면 contig 가 원자 배열에 없는 잔기를 가리켜 검증에서 죽는다
    (2iayA00: contig A3-113 인데 A28 이 없다).

    재번호만으로는 부족하다. preprocess_pdb 는 ATOM/HETATM 잔기 전부에 번호를
    매기므로 CA 없는 잔기가 남아 있으면 CA 서열의 빈틈이 그대로 남는다
    (2pgsA03: 빈틈 54 -> 10). 먼저 걸러야 0 이 된다.

    헤더는 남기되, 원자 번호나 개수를 참조하는 레코드는 버린다. 처음에 ATOM/TER
    만 남겼다가 MODEL/ENDMDL 이 사라져 NMR 앙상블 세 개를 망가뜨렸고, 그 다음에는
    헤더를 전부 남겼다가 CONECT 가 지워진 HETATM 원자를 가리켜 RFD3 가
    `IndexError: index 1099 is out of bounds for axis 0 with size 1098` 로 죽었다.
    """
    with_ca = {
        (line[21], line[22:27])
        for line in pdb_text.splitlines()
        if line.startswith("ATOM") and line[12:16].strip() == "CA"
    }
    #: 원자 번호나 개수를 참조하므로, HETATM 을 지우면 매달린 참조가 된다.
    dangling = {"CONECT", "LINK", "SITE", "HET", "HETNAM", "HETSYN", "FORMUL",
                "MASTER", "SSBOND", "MODRES", "ANISOU"}
    kept = []
    for line in pdb_text.splitlines():
        record = line[:6].strip().upper()
        if record == "ATOM":
            if (line[21], line[22:27]) in with_ca:
                kept.append(line)
        elif record == "HETATM" or record in dangling:
            continue
        else:
            kept.append(line)
    return "\n".join(kept) + "\n"


def stage_target(pdb_path: Path, domain: str) -> tuple[Path, dict]:
    """타겟을 걸러 1..N 연속 번호로 다시 쓰고, 그 파일을 쓴다."""
    from pipeline_mcp.bio.pdb import preprocess_pdb

    raw = pdb_path.read_text(encoding="utf-8", errors="replace")
    single, n_models = first_model_only(raw)
    filtered = drop_ca_less_atoms(single)
    processed, _mapping = preprocess_pdb(
        filtered, strip_nonpositive_resseq=True, renumber_resseq_from_1=True)

    def ca_stats(text: str) -> dict:
        nums = sorted({int(line[22:26]) for line in text.splitlines()
                       if line.startswith("ATOM") and line[12:16].strip() == "CA"})
        return {"n_residues": len(nums), "first": nums[0], "last": nums[-1],
                "gaps": (nums[-1] - nums[0] + 1) - len(nums)}

    STAGED.mkdir(parents=True, exist_ok=True)
    out = STAGED / f"{domain}.pdb"
    out.write_text(processed, encoding="utf-8")
    return out, {"source_pdb": str(pdb_path), "staged_pdb": str(out),
                 "n_models": n_models, "took_first_model": n_models > 1,
                 "before": ca_stats(raw), "after": ca_stats(processed)}


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
    parser.add_argument("--force", action="store_true",
                        help="designs 가 이미 있어도 다시 만든다. 전처리를 바꿨을 때 "
                             "12 개가 같은 경로로 만들어지도록 쓴다.")
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
        "target_preprocess": {
            "steps": ["다중 모델이면 첫 모델만", "CA 없는 잔기의 ATOM 과 HETATM 제거",
                      "strip_nonpositive_resseq", "renumber_resseq_from_1"],
            "why": ("RFD3 contig 는 잔기번호 범위 하나다. CA 없는 잔기가 번호에 "
                    "끼면 contig 가 원자 배열에 없는 잔기를 가리켜 검증에서 죽는다. "
                    "12 타겟 전부 같은 전처리를 거친다 - 일부만 바꾸면 생성 경로가 "
                    "섞여 교란이 된다."),
            "staged_dir": str(STAGED.relative_to(PROJECT_ROOT)),
            "metric_note": ("동결된 지표는 서열 순서로 대응하므로 기준 구조의 잔기번호가 "
                            "바뀌어도 RMSD 는 변하지 않는다. native 기준 구조는 "
                            "staged_pdb 를 쓴다 - 설계가 실제로 올라간 구조다."),
        },
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
        if have >= want and not args.force:
            print(f"[{index}/{len(targets)}] {run_id}: designs {have} 이미 있음, "
                  f"건너뜀", flush=True)
            report["runs"].append({"domain": row["domain"], "stratum": row["stratum"],
                                   "length": row["length"], "run_id": run_id,
                                   "status": "ok", "n_designs": have,
                                   "skipped": True})
            continue
        staged, prep = stage_target(Path(row["pdb"]), row["domain"])
        pdb_text = staged.read_text(encoding="utf-8")
        request = build_gate0_request(pdb_text, "rfd3", seed=args.seed,
                                      stop_after="rfd3", start_from="rfd3")
        record = {"domain": row["domain"], "stratum": row["stratum"],
                  "length": row["length"], "run_id": run_id,
                  "preprocess": prep,
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
