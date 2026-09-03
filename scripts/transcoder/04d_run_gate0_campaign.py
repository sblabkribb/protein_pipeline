#!/usr/bin/env python3
"""게이트 0 백본 증량 캠페인 (설계 6.1b).

파도(wave) 단위로 순차 확장한다. 최종 목표 백본 수를 미리 정하지 않고,
learning curve 가 포화할 때까지 파도를 추가한다.

모든 run 은 `build_gate0_request` 로 만들어지므로 MPNN 설정과 서열 수가
백본 간 동일하고, AF2 는 모든 후보에 실행되어 절단 편향이 없다.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
from collections.abc import Callable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(PROJECT_ROOT / "pipeline-mcp" / "src"))

from rapid_sr.gate0_request import GATE0_ARMS, build_gate0_request  # noqa: E402
from rapid_sr.protocol import protocol_fingerprint  # noqa: E402

DEFAULT_WAVE_SIZES = [32, 64, 128]
DEFAULT_MANIFEST_DIR = PROJECT_ROOT / "public_data" / "benchmark" / "gate0"


def plan_waves(*, existing_backbones: int, wave_sizes: list[int]) -> list[dict]:
    waves: list[dict] = []
    cumulative = int(existing_backbones)
    for index, size in enumerate(wave_sizes, start=1):
        cumulative += int(size)
        waves.append({
            "wave_index": index,
            "new_backbones": int(size),
            "cumulative_backbones": cumulative,
        })
    return waves


def build_run_id(target: str, arm: str, *, wave: int) -> str:
    return f"gate0_w{int(wave)}_{arm}_{target}"


def build_manifest(*, wave: int, targets: list[str], arms: list[str], seed: int) -> dict:
    return {
        "wave": int(wave),
        "targets": list(targets),
        "arms": list(arms),
        "seed": int(seed),
        "protocol": protocol_fingerprint(),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }


def plan_runs(
    *,
    targets: list[str],
    arms: list[str],
    wave: int,
    pdb_lookup: Callable[[str], Path | None],
) -> list[dict]:
    for arm in arms:
        if arm not in GATE0_ARMS:
            raise ValueError(f"unknown gate0 arm: {arm!r}; expected one of {GATE0_ARMS}")
    planned: list[dict] = []
    for target in targets:
        pdb_path = pdb_lookup(target)
        if pdb_path is None:
            continue
        for arm in arms:
            planned.append({
                "run_id": build_run_id(target, arm, wave=wave),
                "target": target,
                "arm": arm,
                "pdb_path": str(pdb_path),
            })
    return planned


def _pdb_lookup(pdb_dirs: list[Path]) -> Callable[[str], Path | None]:
    def lookup(target: str) -> Path | None:
        for directory in pdb_dirs:
            candidate = directory / f"{target}.pdb"
            if candidate.exists():
                return candidate
        return None
    return lookup


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wave", type=int, required=True)
    parser.add_argument("--targets-file", required=True)
    parser.add_argument(
        "--pdb-dirs",
        default="/opt/protein_pipeline/cath_train,/opt/protein_pipeline/cath_val,"
        "/opt/protein_pipeline/cath_test",
    )
    parser.add_argument("--arms", default="rfd3")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--output-root", default="/opt/protein_pipeline/outputs")
    parser.add_argument("--manifest-dir", default=str(DEFAULT_MANIFEST_DIR))
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--env-file",
        default="/opt/protein_pipeline/pipeline-mcp/.env",
        help="RunPod/NCP 자격증명 등 런타임 환경. 저장소에 복사하지 않는다.",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    # 이미 export 된 값(예: BOP 워커 URL)이 .env 보다 우선하도록 override=False.
    env_file = Path(args.env_file)
    if env_file.exists():
        from dotenv import load_dotenv

        load_dotenv(str(env_file), override=False)
        print(f"env_file={env_file}")

    arms = [a.strip() for a in args.arms.split(",") if a.strip()]
    targets = [
        line.strip()
        for line in Path(args.targets_file).read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    pdb_dirs = [Path(p) for p in args.pdb_dirs.split(",") if p.strip()]

    planned = plan_runs(
        targets=targets, arms=arms, wave=args.wave, pdb_lookup=_pdb_lookup(pdb_dirs)
    )
    if args.limit > 0:
        planned = planned[: args.limit]

    manifest_dir = Path(args.manifest_dir)
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest = build_manifest(
        wave=args.wave, targets=targets, arms=arms, seed=args.seed
    )
    manifest["planned_runs"] = planned
    manifest_path = manifest_dir / f"wave_{args.wave:02d}_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"manifest={manifest_path} planned_runs={len(planned)}")

    if args.dry_run:
        for item in planned[:10]:
            print(f"  [dry-run] {item['run_id']}  <- {item['pdb_path']}")
        if len(planned) > 10:
            print(f"  ... and {len(planned) - 10} more")
        return 0

    from pipeline_mcp.app import build_runner  # noqa: E402

    runner = build_runner()
    results: list[dict] = []
    for index, item in enumerate(planned, start=1):
        pdb_text = Path(item["pdb_path"]).read_text(encoding="utf-8")
        request = build_gate0_request(pdb_text, item["arm"], seed=args.seed)
        started = time.time()
        print(f"[{index}/{len(planned)}] run {item['run_id']}", flush=True)
        record = {**item, "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
        try:
            runner.run(request, run_id=item["run_id"])
            record["status"] = "ok"
        except Exception as exc:
            record["status"] = "failed"
            record["error"] = f"{type(exc).__name__}: {exc}"
            print(f"    failed: {record['error']}", flush=True)
        record["elapsed_s"] = round(time.time() - started, 1)
        results.append(record)
        # 진행 상황을 매 run 마다 남겨 중간에 죽어도 복구 가능하게 한다.
        (manifest_dir / f"wave_{args.wave:02d}_results.json").write_text(
            json.dumps(results, indent=2), encoding="utf-8"
        )

    ok = sum(1 for r in results if r["status"] == "ok")
    print(f"\ncompleted: {ok}/{len(results)} ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
