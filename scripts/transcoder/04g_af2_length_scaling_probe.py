#!/usr/bin/env python3
"""AF2 폴딩 시간의 길이 의존성을 실측한다.

게이트 0 캠페인 비용은 fold 당 시간 x fold 수인데, fold 당 시간이 서열 길이에
크게 좌우된다. 62aa 한 점으로 전체 예산을 추정하면 빗나가므로 대표 길이 몇 개를
직접 잰다.
"""

from __future__ import annotations

import argparse
import os
import json
from pathlib import Path
import sys
import time

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _worker_url(port: int) -> str:
    """RAPID_GPU_HOST 가 없으면 빈 문자열. 호출자가 --url 로 주어야 한다.

    내부 호스트를 기본값으로 박아두면 공개 저장소에 나간다.
    """
    host = os.environ.get("RAPID_GPU_HOST", "").strip()
    return f"http://{host}:{port}" if host else ""
sys.path.insert(0, str(PROJECT_ROOT / "pipeline-mcp" / "src"))

from pipeline_mcp.clients.local_http import LocalHTTPAlphaFold2Client  # noqa: E402
from pipeline_mcp.models import SequenceRecord  # noqa: E402

THREE_TO_ONE = {
    "ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C", "GLN": "Q",
    "GLU": "E", "GLY": "G", "HIS": "H", "ILE": "I", "LEU": "L", "LYS": "K",
    "MET": "M", "PHE": "F", "PRO": "P", "SER": "S", "THR": "T", "TRP": "W",
    "TYR": "Y", "VAL": "V", "MSE": "M",
}


def sequence_from_pdb(pdb_path: Path) -> str:
    """첫 MODEL 의 CA 만 읽는다. NMR 다중 MODEL 파일에서 길이가 뻥튀기되는 것을 막는다."""
    seen: set[str] = set()
    letters: list[str] = []
    for line in pdb_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("ENDMDL"):
            break
        if not line.startswith("ATOM") or line[12:16].strip() != "CA":
            continue
        key = line[21:27]
        if key in seen:
            continue
        seen.add(key)
        letters.append(THREE_TO_ONE.get(line[17:20].strip().upper(), "X"))
    return "".join(letters)


def fit_scaling(points: list[dict]) -> dict[str, object]:
    """log(time) = a + b*log(length) 로 지수 b 를 추정한다."""
    import math

    ok = [p for p in points if p.get("status") == "ok" and p.get("length", 0) > 0]
    if len(ok) < 2:
        return {"exponent": None, "n_points": len(ok)}
    xs = [math.log(float(p["length"])) for p in ok]
    ys = [math.log(float(p["elapsed_s"])) for p in ok]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    denom = sum((x - mx) ** 2 for x in xs)
    if denom == 0:
        return {"exponent": None, "n_points": len(ok)}
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom
    intercept = my - slope * mx
    return {
        "exponent": round(slope, 3),
        "coefficient": round(math.exp(intercept), 6),
        "n_points": len(ok),
        "model": "elapsed_s = coefficient * length^exponent",
    }


def predict_seconds(fit: dict, length: int) -> float | None:
    if fit.get("exponent") is None:
        return None
    return float(fit["coefficient"]) * float(length) ** float(fit["exponent"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--colabfold-url", default=_worker_url(18160))
    parser.add_argument("--pdb-dir", default="/opt/protein_pipeline/cath_train")
    parser.add_argument("--targets", required=True, help="쉼표 구분 CATH 도메인 id")
    parser.add_argument("--timeout-s", type=float, default=7200.0)
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)

    client = LocalHTTPAlphaFold2Client(args.colabfold_url, None, args.timeout_s)
    points: list[dict] = []
    for target in [t.strip() for t in args.targets.split(",") if t.strip()]:
        pdb_path = Path(args.pdb_dir) / f"{target}.pdb"
        sequence = sequence_from_pdb(pdb_path)
        record = SequenceRecord(id=f"lenprobe_{target}", sequence=sequence)
        point: dict = {"target": target, "length": len(sequence)}
        started = time.monotonic()
        try:
            result = client.predict([record])
            point["status"] = "ok"
            entry = result.get(record.id) if isinstance(result, dict) else None
            if isinstance(entry, dict):
                point["best_plddt"] = entry.get("best_plddt")
        except Exception as exc:
            point["status"] = "failed"
            point["error"] = f"{type(exc).__name__}: {exc}"[:200]
        point["elapsed_s"] = round(time.monotonic() - started, 1)
        print(f"  {target:12s} len={point['length']:5d} {point['status']:6s} "
              f"{point['elapsed_s']:>7}s plddt={point.get('best_plddt')}", flush=True)
        points.append(point)

    fit = fit_scaling(points)
    summary = {"points": points, "fit": fit}
    if fit.get("exponent") is not None:
        summary["predicted_s"] = {
            str(length): round(predict_seconds(fit, length), 1)
            for length in (60, 123, 254, 416, 619)
        }
    if args.out:
        Path(args.out).write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
