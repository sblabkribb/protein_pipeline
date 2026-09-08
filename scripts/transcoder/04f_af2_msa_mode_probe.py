#!/usr/bin/env python3
"""AF2 MSA 모드에 따른 폴딩 시간을 실측 비교한다.

ProteinMPNN 설계 서열에는 MSA 가 무의미하지만(설계 6.1b) MSA 단계가 ColabFold
비용의 대부분이다. 같은 서열을 두 모드로 순차 제출해 실제 차이를 잰다.

두 arm 은 동일한 백그라운드 부하를 겪도록 **순차** 실행한다. 워커가 다른 작업으로
바쁘면 두 값 모두 대기시간을 포함하므로, 절대값보다 비율을 본다.
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

SINGLE_SEQUENCE_FLAGS = "--msa-mode single_sequence"


def summarise(arms: list[dict]) -> dict[str, object]:
    """두 arm 의 경과시간을 비교한다. 실패한 arm 은 비율 계산에서 제외한다."""
    ok = {arm["name"]: arm for arm in arms if arm.get("status") == "ok"}
    out: dict[str, object] = {"arms": arms}
    if "full_dbs" in ok and "single_sequence" in ok:
        base = float(ok["full_dbs"]["elapsed_s"])
        fast = float(ok["single_sequence"]["elapsed_s"])
        out["speedup"] = round(base / fast, 2) if fast > 0 else None
        out["saved_s"] = round(base - fast, 1)
    return out


def _read_fasta(fasta_path: Path) -> list[SequenceRecord]:
    records: list[SequenceRecord] = []
    header, parts = None, []
    for line in fasta_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith(">"):
            if header is not None and parts:
                records.append(SequenceRecord(id=header, sequence="".join(parts)))
            header, parts = line[1:].split()[0], []
        elif header is not None:
            parts.append(line)
    if header is not None and parts:
        records.append(SequenceRecord(id=header, sequence="".join(parts)))
    if not records:
        raise SystemExit(f"no sequence found in {fasta_path}")
    return records


def aggregate(replicates: list[dict]) -> dict[str, object]:
    """여러 서열의 arm 별 평균. 서열 하나로는 결론을 낼 수 없다."""
    import statistics as st

    by_arm: dict[str, list[dict]] = {}
    for rep in replicates:
        for arm in rep.get("arms", []):
            if arm.get("status") == "ok":
                by_arm.setdefault(arm["name"], []).append(arm)

    means: dict[str, dict[str, float | int]] = {}
    for name, arms in by_arm.items():
        elapsed = [float(a["elapsed_s"]) for a in arms]
        plddt = [float(a["best_plddt"]) for a in arms if a.get("best_plddt") is not None]
        means[name] = {
            "n": len(arms),
            "mean_elapsed_s": round(st.mean(elapsed), 1),
            "mean_plddt": round(st.mean(plddt), 2) if plddt else None,
        }

    out: dict[str, object] = {"per_arm": means, "replicates": replicates}
    if "full_dbs" in means and "single_sequence" in means:
        base = means["full_dbs"]["mean_elapsed_s"]
        fast = means["single_sequence"]["mean_elapsed_s"]
        out["speedup"] = round(base / fast, 2) if fast else None
        if means["full_dbs"]["mean_plddt"] and means["single_sequence"]["mean_plddt"]:
            out["plddt_delta"] = round(
                means["single_sequence"]["mean_plddt"] - means["full_dbs"]["mean_plddt"], 2
            )
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--colabfold-url", default=_worker_url(18160))
    parser.add_argument("--fasta", required=True, help="설계 FASTA (첫 서열만 사용)")
    parser.add_argument("--timeout-s", type=float, default=7200.0)
    parser.add_argument("--n-sequences", type=int, default=1)
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)

    records = _read_fasta(Path(args.fasta))[: max(1, args.n_sequences)]
    client = LocalHTTPAlphaFold2Client(args.colabfold_url, None, args.timeout_s)

    replicates: list[dict] = []
    for record in records:
        print(f"probe sequence: {record.id} (len={len(record.sequence)})")
        arms: list[dict] = []
        for name, flags in (("full_dbs", None), ("single_sequence", SINGLE_SEQUENCE_FLAGS)):
            probe_record = SequenceRecord(
                id=f"{record.id}__{name}", sequence=record.sequence
            )
            started = time.monotonic()
            arm: dict[str, object] = {"name": name, "extra_flags": flags}
            try:
                result = client.predict([probe_record], extra_flags=flags)
                arm["status"] = "ok"
                entry = result.get(probe_record.id) if isinstance(result, dict) else None
                if isinstance(entry, dict):
                    arm["best_plddt"] = entry.get("best_plddt")
            except Exception as exc:
                arm["status"] = "failed"
                arm["error"] = f"{type(exc).__name__}: {exc}"[:300]
            arm["elapsed_s"] = round(time.monotonic() - started, 1)
            print(f"  {name:16s} {arm['status']:6s} {arm['elapsed_s']:>6}s "
                  f"plddt={arm.get('best_plddt')}")
            arms.append(arm)
        rep = summarise(arms)
        rep["sequence_id"] = record.id
        rep["sequence_length"] = len(record.sequence)
        replicates.append(rep)

    summary = aggregate(replicates)
    if args.out:
        Path(args.out).write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
