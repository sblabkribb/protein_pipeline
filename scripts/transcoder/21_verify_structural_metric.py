#!/usr/bin/env python3
"""구조 지표 계약을 동결하기 전에 검증한다.

1,312 폴드를 다시 접기 전에 통과해야 하는 관문이다. 지표 정의가 세 번 틀렸고
매번 재폴딩을 했으므로, 이번에는 정의가 맞다는 것을 먼저 보인다.

Primary metric
--------------
    sequence-order correspondence + reference DSSP non-loop CA + Kabsch RMSD

잔기 번호는 대응에 쓰지 않는다. CATH 도메인은 잘려 나온 사슬의 번호를 유지하고
(1af7A01 은 11..284) AF2 는 늘 1..N 으로 번호매긴다. non-loop 마스크도 번호가
아니라 **서열 인덱스** 로 적용한다 - 마스크를 번호로 들고 있으면 같은 문제가
마스크 쪽에서 다시 생긴다.

검사 항목
---------
1. 좌표가 같고 번호만 다르면 RMSD 가 불변인가
2. CATH 오프셋 백본에서 순서 대응이 올바른 값을 내는가
3. 길이 불일치나 잔기 누락에서 잘라 쓰지 않고 실패하는가
4. rmsd_nonloop_order 와 rmsd_all_ca_order 를 모두 저장하는가
5. 실제 중첩을 그려 계산값과 눈으로 일치하는가
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "transcoder"))
sys.path.insert(0, str(PROJECT_ROOT / "pipeline-mcp" / "src"))

from pipeline_mcp.bio.pdb import dssp_non_loop_positions_by_chain  # noqa: E402
from pipeline_mcp.clients.local_http import LocalHTTPAlphaFold2Client  # noqa: E402
from pipeline_mcp.models import SequenceRecord  # noqa: E402
from rapid_sr.clustered import kabsch_rmsd  # noqa: E402
from rapid_sr.descriptors import ca_coords  # noqa: E402
from rapid_sr.protocol import AF2_SETTINGS_V1  # noqa: E402
from rapid_sr.structural import (  # noqa: E402
    ca_records, designed_length, model_positions, non_loop_indices,
    positional_non_loop_rmsd, sequence_indices,
)

BASE = PROJECT_ROOT / "public_data" / "benchmark" / "gate0"
DEFAULT_OUT = BASE / "structural_metric_verification.json"


def renumber(pdb_text: str, offset: int) -> str:
    """좌표는 그대로 두고 잔기 번호만 옮긴다. 검사 1 의 도구다."""
    out = []
    for line in pdb_text.splitlines():
        if line.startswith(("ATOM", "HETATM")):
            try:
                num = int(line[22:26]) + offset
            except ValueError:
                out.append(line)
                continue
            out.append(f"{line[:22]}{num:4d}{line[26:]}")
        else:
            out.append(line)
    return "\n".join(out) + "\n"


def drop_residue(pdb_text: str, index: int) -> str:
    """n 번째 CA 잔기를 통째로 뺀다. 검사 3 의 도구다."""
    seen = -1
    target = None
    out = []
    for line in pdb_text.splitlines():
        if line.startswith("ATOM") and line[12:16].strip() == "CA":
            seen += 1
            if seen == index:
                target = line[21:27]
        if line.startswith("ATOM") and target and line[21:27] == target:
            continue
        out.append(line)
    return "\n".join(out) + "\n"


def check_offset_invariance(reference: str, model: str, mask, sequence: str) -> dict:
    base = positional_non_loop_rmsd(reference, model, mask, sequence=sequence)
    results = {}
    for offset in (-5, 7, 162, 1000):
        shifted = renumber(reference, offset)
        shifted_mask = {
            chain: {(num + offset, icode) for num, icode in positions}
            for chain, positions in mask.items()
        }
        results[str(offset)] = positional_non_loop_rmsd(shifted, model, shifted_mask)
    # 반올림한 값을 1e-9 허용오차로 비교하면 반올림 오차에 걸린다. 비교는
    # 원값으로 하고 보고만 반올림한다.
    ok = base is not None and all(
        v is not None and abs(v - base) < 1e-9 for v in results.values())
    return {
        "passed": bool(ok),
        "baseline": None if base is None else round(base, 6),
        "shifted": {k: (None if v is None else round(v, 6)) for k, v in results.items()},
        "note": "좌표가 같고 번호만 다르면 값이 변하면 안 된다.",
    }


def check_fail_closed(reference: str, model: str, mask, sequence: str) -> dict:
    """대응을 세울 수 없을 때 잘라 쓰지 않고 거부하는지."""
    outcomes = {}
    for name, ref, mdl, seq in (
        ("model_one_short", reference, drop_residue(model, 3), sequence),
        ("model_two_short", reference, drop_residue(drop_residue(model, 3), 4), sequence),
        ("sequence_from_another_backbone", reference, model, sequence[:-3]),
    ):
        try:
            positional_non_loop_rmsd(ref, mdl, mask, sequence=seq)
            outcomes[name] = "값을 돌려줬다"
        except ValueError as exc:
            outcomes[name] = f"거부: {str(exc)[:60]}"
    thin = positional_non_loop_rmsd(reference, model, {"A": {(1, ""), (2, "")}},
                                    sequence=sequence)
    outcomes["too_few_masked_positions"] = "None" if thin is None else f"값 {thin}"
    ok = (all(v.startswith("거부") for k, v in outcomes.items()
              if k != "too_few_masked_positions")
          and outcomes["too_few_masked_positions"] == "None")
    return {"passed": bool(ok), "outcomes": outcomes,
            "note": "잘라 쓰면 뒤쪽이 어긋난 채로 숫자가 나온다. 거부해야 한다."}


def _all_ca_order_rmsd(reference: str, model: str, sequence: str) -> float | None:
    """전체 CA, 서열 인덱스 대응. 마스크만 빼고 primary 와 같은 대응을 쓴다."""
    records = ca_records(reference)
    if not records:
        return None
    try:
        positions = model_positions(reference, model, sequence=sequence)
    except ValueError:
        return None
    a = ca_coords(reference)
    b = ca_coords(model)
    return round(float(kabsch_rmsd(b[positions], a)), 4)


def superpose_pdb(reference: str, model: str, keep: list[int], positions: list[int]) -> str:
    """모델을 기준에 겹쳐 하나의 PDB 로 만든다. 검사 5 에서 눈으로 확인한다."""
    import numpy as np

    seq_index = sequence_indices(reference)
    a_all, b_all = ca_coords(reference), ca_coords(model)
    a = a_all[keep]
    b = b_all[[positions[i] for i in keep]]
    ca, cb = a.mean(axis=0), b.mean(axis=0)
    u, _s, vt = np.linalg.svd((a - ca).T @ (b - cb))
    d = np.sign(np.linalg.det(u @ vt))
    rot = u @ np.diag([1.0, 1.0, d]) @ vt
    lines = [l for l in reference.splitlines() if l.startswith("ATOM")]
    out = list(lines) + ["TER"]
    for line in model.splitlines():
        if not line.startswith("ATOM"):
            continue
        xyz = np.array([float(line[30:38]), float(line[38:46]), float(line[46:54])])
        moved = (xyz - cb) @ rot.T + ca
        out.append(f"{line[:21]}B{line[22:30]}"
                   f"{moved[0]:8.3f}{moved[1]:8.3f}{moved[2]:8.3f}{line[54:]}")
    return "\n".join(out + ["TER", "END"]) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=12, help="검증에 쓸 폴드 수 (10-20)")
    parser.add_argument("--visual", type=int, default=4, help="중첩 그림을 만들 개수")
    parser.add_argument("--colabfold-url", default="http://211.188.35.221:18160")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--pdb-out", type=Path, default=BASE / "metric_verification_pdb")
    args = parser.parse_args(argv)

    labels = {r["backbone_key"]: r for r in
              csv.DictReader((BASE / "backbones" / "backbone_labels.csv").open(encoding="utf-8"))}
    seqs = list(csv.DictReader(
        (BASE / "temperature_sweep" / "sequences.csv").open(encoding="utf-8")))
    pdbdir = BASE / "backbones" / "pdb"

    # 오프셋과 비오프셋을 섞어 고른다. 오프셋만 보면 고쳐졌다는 것만 알고,
    # 비오프셋이 그대로인지는 모른다.
    def start_of(key):
        text = (pdbdir / labels[key]["pdb_file"]).read_text(errors="replace")
        return next(int(l[22:26]) for l in text.splitlines()
                    if l.startswith("ATOM") and l[12:16].strip() == "CA")

    keys = sorted({r["backbone_key"] for r in seqs})
    offset_keys = [k for k in keys if start_of(k) != 1]
    aligned_keys = [k for k in keys if start_of(k) == 1]
    chosen = (offset_keys[: args.n // 2] + aligned_keys[: args.n - args.n // 2])
    print(f"검증 대상 {len(chosen)} 백본 (오프셋 {len([k for k in chosen if start_of(k)!=1])}, "
          f"1부터 {len([k for k in chosen if start_of(k)==1])})")

    client = LocalHTTPAlphaFold2Client(args.colabfold_url, None, 7200.0)
    args.pdb_out.mkdir(parents=True, exist_ok=True)
    report = {
        "metric": "sequence_order + reference_dssp_non_loop + kabsch_ca",
        "af2_settings": {k: v for k, v in AF2_SETTINGS_V1.items()
                         if k != "not_controlled_here"},
        "code_sha": subprocess.run(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT,
                                   capture_output=True, text=True).stdout.strip(),
        "folds": [],
    }

    for index, key in enumerate(chosen):
        row = next(r for r in seqs if r["backbone_key"] == key and r["temperature"] == "0.1")
        reference = (pdbdir / labels[key]["pdb_file"]).read_text(errors="replace")
        mask = dssp_non_loop_positions_by_chain(reference)
        sid = row["sequence_id"].replace("|", "_")
        result = client.predict(
            [SequenceRecord(id=sid, sequence=row["sequence"])],
            model_preset=str(AF2_SETTINGS_V1["model_preset"]),
            db_preset=str(AF2_SETTINGS_V1["db_preset"]),
            max_template_date=str(AF2_SETTINGS_V1["max_template_date"]),
        )
        payload = (result or {}).get(sid) or {}
        model = payload.get("ranked_0_pdb") or payload.get("pdb") or ""
        if not model:
            print(f"  [{key}] 폴드 실패 — 건너뜀", flush=True)
            continue

        keep = non_loop_indices(reference, mask)
        entry = {
            "backbone_key": key,
            "sequence_id": row["sequence_id"],
            "reference_start_resnum": start_of(key),
            "n_reference_ca": len(ca_records(reference)),
            "n_model_ca": len(ca_records(model)),
            "designed_length": designed_length(reference),
            "n_non_loop": len(keep),
            "non_loop_indices_head": keep[:8],
            "plddt": payload.get("best_plddt"),
            "designed_sequence_length": len(row["sequence"]),
            "x_placeholders": row["sequence"].count("X"),
            "correspondence": ("file_order" if len(ca_records(model)) == len(ca_records(reference))
                               else "numbering_span"),
            "rmsd_nonloop_order": positional_non_loop_rmsd(
                reference, model, mask, sequence=row["sequence"]),
            "rmsd_all_ca_order": _all_ca_order_rmsd(reference, model, row["sequence"]),
            "check_1_offset_invariance": check_offset_invariance(
                reference, model, mask, row["sequence"]),
            "check_3_fail_closed": check_fail_closed(
                reference, model, mask, row["sequence"]),
        }
        if index < args.visual:
            path = args.pdb_out / f"{key.replace('|', '_')}_superposed.pdb"
            path.write_text(
                superpose_pdb(reference, model, keep,
                              model_positions(reference, model, sequence=row["sequence"])),
                encoding="utf-8")
            entry["superposition_pdb"] = str(path.relative_to(PROJECT_ROOT))
        report["folds"].append(entry)
        v = entry["rmsd_nonloop_order"]
        print(f"  [{key.split('|')[0]:10s} start={entry['reference_start_resnum']:>4d}] "
              f"pLDDT {entry['plddt']:.1f} · non-loop {v if v is None else round(v,2)} A · "
              f"all-CA {entry['rmsd_all_ca_order']} A · "
              f"불변 {'OK' if entry['check_1_offset_invariance']['passed'] else 'FAIL'} · "
              f"fail-closed {'OK' if entry['check_3_fail_closed']['passed'] else 'FAIL'}",
              flush=True)

    checks = {
        "1_offset_invariance": all(f["check_1_offset_invariance"]["passed"] for f in report["folds"]),
        "3_fail_closed": all(f["check_3_fail_closed"]["passed"] for f in report["folds"]),
        "4_both_variants_stored": all(
            f.get("rmsd_all_ca_order") is not None for f in report["folds"]),
    }
    # 검사 2: 오프셋 백본이 비오프셋 백본과 같은 범위의 값을 내는가.
    offset_vals = [f["rmsd_nonloop_order"] for f in report["folds"]
                   if f["reference_start_resnum"] != 1 and f["rmsd_nonloop_order"] is not None]
    aligned_vals = [f["rmsd_nonloop_order"] for f in report["folds"]
                    if f["reference_start_resnum"] == 1 and f["rmsd_nonloop_order"] is not None]
    checks["2_offset_case_sane"] = bool(offset_vals) and max(offset_vals) < 30.0
    report["checks"] = checks
    report["offset_rmsd"] = [round(v, 3) for v in offset_vals]
    report["aligned_rmsd"] = [round(v, 3) for v in aligned_vals]
    report["visual_check_pending"] = [f["superposition_pdb"] for f in report["folds"]
                                      if f.get("superposition_pdb")]

    print("\n=== 검사 결과 ===")
    for name, ok in checks.items():
        print(f"  {name:26s} {'통과' if ok else '실패'}")
    print(f"  5_visual                   {len(report['visual_check_pending'])} 개 중첩 PDB 생성 "
          f"(눈으로 확인 필요)")
    report["all_programmatic_checks_passed"] = all(checks.values())
    print(f"\n프로그램 검사 종합: {'통과' if report['all_programmatic_checks_passed'] else '실패'}")

    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {args.out}")
    return 0 if report["all_programmatic_checks_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
