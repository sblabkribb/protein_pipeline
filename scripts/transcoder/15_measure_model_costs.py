#!/usr/bin/env python3
"""레지스트리의 비용 공백을 실제 측정으로 채운다.

`MODEL_REGISTRY_V1.yaml` 은 측정하지 않은 비용에 숫자를 붙이지 않는다. 그래서
빈 칸이 생기고, 예산 추정은 그 스테이지를 `unknown_stages` 로 돌려준다. 이
스크립트는 그 빈 칸 중 값싸게 측정할 수 있는 것만 실제로 재서 아티팩트로
남긴다.

**무엇을 재는가**: 같은 백본에 대해 서열 수를 바꿔가며 벽시계를 재고, 선형
적합의 기울기를 서열당 한계 비용으로, 절편을 호출 고정비로 본다. 한 번의
호출을 재서 나누면 고정비가 서열당 비용에 섞여 들어간다.

**무엇을 재지 않는가**: AF2. 이미 길이 적합이 있고, 지금 다른 캠페인이 그
워커를 쓰고 있다. 남의 작업을 밀어내면서 얻는 숫자는 그 자체가 오염된다.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time

import requests
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "pipeline-mcp" / "src"))

from pipeline_mcp.clients.esm_embedding import LocalHTTPESMEmbeddingClient  # noqa: E402

DEFAULT_OUT = PROJECT_ROOT / "public_data" / "benchmark" / "gate0" / "model_cost_probe.json"
BACKBONE_DIR = PROJECT_ROOT / "public_data" / "benchmark" / "gate0" / "backbones" / "pdb"


def _pdb_length(text: str) -> int:
    seen = set()
    for line in text.splitlines():
        if line.startswith("ATOM") and line[12:16].strip() == "CA":
            seen.add(line[21:27])
    return len(seen)


def _submit_and_poll(url: str, payload: dict, *, poll_s: float, timeout_s: float) -> tuple[float, dict]:
    """워커에 직접 제출하고 촘촘히 폴링해서 워커 자체 시간을 잰다.

    프로덕션 클라이언트를 그대로 쓰면 안 되는 이유: LocalHttpRunClient 의 폴링
    간격은 `min(15, max(2, timeout_s/200))` 이라 timeout 1800 초에서 9 초가 된다.
    1 초 안에 끝나는 작업도 9 초로 관측된다. 그건 모델의 비용이 아니라 폴링
    바닥값이다. 둘을 같은 숫자로 보고하면 최적화할 대상을 못 찾는다.
    """
    started = time.time()
    response = requests.post(f"{url}/run", json={"input": payload}, timeout=60)
    response.raise_for_status()
    data = response.json()
    status = str(data.get("status") or "").upper()
    if status in {"COMPLETED", "OK"}:
        return time.time() - started, data
    job_id = data.get("id")
    if not job_id:
        raise RuntimeError(f"worker accepted the job but returned no id: {data}")
    deadline = started + timeout_s
    while time.time() < deadline:
        time.sleep(poll_s)
        poll = requests.get(f"{url}/status", params={"id": job_id}, timeout=30).json()
        status = str(poll.get("status") or "").upper()
        if status in {"COMPLETED", "OK"}:
            return time.time() - started, poll
        if status in {"FAILED", "CANCELLED"}:
            raise RuntimeError(str(poll.get("error") or status))
    raise TimeoutError(f"job {job_id} did not finish within {timeout_s}s")


def measure_proteinmpnn(
    pdb_path: Path, *, url: str, counts: list[int], repeats: int, poll_s: float,
) -> dict:
    import base64

    text = pdb_path.read_text(encoding="utf-8")
    length = _pdb_length(text)
    encoded = base64.b64encode(text.encode("utf-8")).decode("ascii")
    points: list[dict] = []
    for n in counts:
        for repeat in range(repeats):
            payload = {
                "pdb_base64": encoded, "pdb_name": pdb_path.stem,
                "use_soluble_model": True, "model_name": "v_48_020",
                "num_seq_per_target": int(n), "batch_size": 1,
                "sampling_temp": 0.1, "seed": repeat, "backbone_noise": 0.0,
                "cleanup": True,
            }
            try:
                elapsed, _ = _submit_and_poll(url, payload, poll_s=poll_s, timeout_s=1800.0)
                status = "ok"
            except Exception as exc:  # noqa: BLE001
                elapsed, status = float("nan"), f"failed: {exc}"
            points.append({
                "num_seq": n, "repeat": repeat,
                "elapsed_s": round(elapsed, 3) if status == "ok" else None,
                "status": status,
            })
            print(f"  mpnn n={n} rep={repeat}: {points[-1]['elapsed_s']}s {status}", flush=True)
    out = {
        "backbone": pdb_path.name, "length_aa": length,
        "poll_interval_s": poll_s, "points": points,
        **_fit(points, "num_seq"),
    }
    # 파이프라인이 실제로 지불하는 시간은 폴링 바닥값에 올림된다. 워커 시간과
    # 따로 보고하지 않으면 "MPNN 이 9 초 걸린다" 는 잘못된 결론이 남는다.
    production_poll = min(15.0, max(2.0, 1800.0 / 200))
    out["production_client_floor_s"] = production_poll
    out["production_client_note"] = (
        f"LocalHttpRunClient 의 폴링 간격은 timeout_s/200 로 계산되어 기본 설정에서 "
        f"{production_poll} 초다. 그보다 빨리 끝나는 호출도 {production_poll} 초로 "
        f"관측된다. 워커 시간이 아니라 클라이언트가 만드는 비용이다."
    )
    return out


def measure_esm(sequences: list[str], *, url: str, counts: list[int], repeats: int) -> dict:
    client = LocalHTTPESMEmbeddingClient(base_url=url)
    points: list[dict] = []
    for n in counts:
        batch = (sequences * ((n // len(sequences)) + 1))[:n]
        for repeat in range(repeats):
            started = time.time()
            try:
                client.embed(batch)
                status = "ok"
            except Exception as exc:  # noqa: BLE001
                status = f"failed: {exc}"
            points.append({
                "num_seq": n, "repeat": repeat,
                "elapsed_s": round(time.time() - started, 2), "status": status,
            })
            print(f"  esm  n={n} rep={repeat}: {points[-1]['elapsed_s']}s {status}", flush=True)
    return {"points": points, **_fit(points, "num_seq")}


def _fit(points: list[dict], key: str) -> dict:
    """호출 고정비와 단위당 한계비용을 최소제곱으로 분리한다.

    측정점이 서로 다른 n 두 개 미만이면 기울기를 추정할 수 없다. 그때는 숫자를
    지어내는 대신 `insufficient_points` 를 돌려준다.
    """
    ok = [p for p in points if p["status"] == "ok" and p.get("elapsed_s") is not None]
    xs = sorted({float(p[key]) for p in ok})
    if len(xs) < 2:
        return {"fit": None, "fit_note": "insufficient_points"}
    grouped = {
        x: statistics.median([p["elapsed_s"] for p in ok if float(p[key]) == x]) for x in xs
    }
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(grouped.values()) / n
    denom = sum((x - mean_x) ** 2 for x in xs)
    if denom == 0:
        return {"fit": None, "fit_note": "no_variation_in_x"}
    slope = sum((x - mean_x) * (grouped[x] - mean_y) for x in xs) / denom
    intercept = mean_y - slope * mean_x
    return {
        "fit": {
            "model": "elapsed_s = intercept + slope * " + key,
            "intercept_s": round(intercept, 3),
            "slope_s_per_unit": round(slope, 4),
            "n_distinct_x": n,
            "medians": {str(int(k)): round(v, 2) for k, v in grouped.items()},
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="211.188.35.221")
    parser.add_argument("--mpnn-port", type=int, default=18101)
    parser.add_argument("--esm-port", type=int, default=18170)
    parser.add_argument("--counts", default="1,4,16")
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--backbone", default="")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--poll-interval", type=float, default=0.2,
                        help="워커 상태 폴링 간격(초). 측정 해상도를 정한다.")
    parser.add_argument("--skip-mpnn", action="store_true")
    parser.add_argument("--skip-esm", action="store_true")
    args = parser.parse_args()

    counts = [int(c) for c in args.counts.split(",") if c.strip()]
    out: dict = {
        "measured_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "host": args.host,
        "counts": counts,
        "repeats": args.repeats,
        "note": (
            "기울기가 서열당 한계비용, 절편이 호출 고정비다. 한 번의 호출을 재서 "
            "나누면 둘이 섞인다. AF2 는 여기서 재지 않는다 - 길이 적합이 이미 있고, "
            "측정을 위해 다른 캠페인의 워커를 밀어내지 않는다."
        ),
    }

    if not args.skip_mpnn:
        pdb = Path(args.backbone) if args.backbone else sorted(BACKBONE_DIR.glob("*__target__*.pdb"))[0]
        print(f"ProteinMPNN on {pdb.name}", flush=True)
        out["proteinmpnn"] = measure_proteinmpnn(
            pdb, url=f"http://{args.host}:{args.mpnn_port}", counts=counts,
            repeats=args.repeats, poll_s=args.poll_interval,
        )

    if not args.skip_esm:
        print("ESM2-8M embedding", flush=True)
        seqs = ["MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQAPILSRVGDGTQDNLSGAEKAVQVKVKALPDAQFEVVHSLAKWKR"]
        out["esm2_embedding"] = measure_esm(
            seqs, url=f"http://{args.host}:{args.esm_port}", counts=counts, repeats=args.repeats,
        )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {args.out}")
    for name in ("proteinmpnn", "esm2_embedding"):
        block = out.get(name)
        if block and block.get("fit"):
            fit = block["fit"]
            print(f"  {name}: {fit['intercept_s']} s fixed + {fit['slope_s_per_unit']} s/seq")
        elif block:
            print(f"  {name}: {block.get('fit_note')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
