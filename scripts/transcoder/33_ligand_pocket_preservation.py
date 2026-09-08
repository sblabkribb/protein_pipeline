#!/usr/bin/env python3
"""재설계가 리간드 결합 부위를 보존하는가 (DiffDock).

두 단계이고, 주장할 수 있는 것이 서로 다르다
---------------------------------------------
1 단계 자기도킹 - native 구조에 그 구조의 결정 리간드를 다시 도킹한다.
   **이것은 검증이 아니라 배선 점검이다.** DiffDock 은 PDBBind 로 학습했고 이
   복합체들이 거의 확실히 그 안에 있다. 학습 데이터에서 포즈를 회수하는 것은
   "워커가 제대로 돈다"까지만 말해준다. ThermoMPNN 을 MegaScale 에서 평가하는
   것과 같은 순환이므로 검증으로 보고하지 않는다.

2 단계 재설계 비교 - 같은 리간드를 재설계 서열의 AF2 구조에 도킹한다.
   DiffDock 은 우리 재설계 서열을 본 적이 없다. native 대비 상대 비교이므로
   1 단계와 같은 순환이 아니다. 이것이 답하는 질문은 논문이 지금 답하지 못하는
   것이다 - 용해도를 위한 재설계가 결합 부위를 망가뜨리는가.

지표를 왜 이렇게 고르는가
-------------------------
RDKit 이 없어 대칭 보정 RMSD 를 계산할 수 없다. 대칭이 있는 리간드에서
원자 대응 RMSD 는 틀린 값을 준다. 그래서 대칭과 무관한 두 가지를 쓴다.

  centroid_shift  예측 포즈 중심과 결정 리간드 중심의 거리
  pocket_overlap  예측 리간드 원자 중 결정 리간드 4 A 안에 있는 비율

둘 다 "같은 자리에 들어갔는가" 를 재고, 원자 하나하나의 대응을 요구하지 않는다.
포즈 정확도가 아니라 부위 보존을 재는 것이므로 이 질문에는 이 편이 맞다.
"""

from __future__ import annotations

import argparse
import os
import csv
import json
import math
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _worker_url(port: int) -> str:
    """RAPID_GPU_HOST 가 없으면 빈 문자열. 호출자가 --url 로 주어야 한다.

    내부 호스트를 기본값으로 박아두면 공개 저장소에 나간다.
    """
    host = os.environ.get("RAPID_GPU_HOST", "").strip()
    return f"http://{host}:{port}" if host else ""
sys.path.insert(0, str(PROJECT_ROOT / "pipeline-mcp" / "src"))

BASE = PROJECT_ROOT / "public_data" / "benchmark" / "gate0"
OUT = BASE / "ligand_pocket"
#: 물·이온·결정화 첨가물·변형 잔기. 결합 부위 질문의 대상이 아니다.
SKIP_HET = {
    "HOH", "WAT", "MSE", "CL", "NA", "K", "MG", "ZN", "CA", "SO4", "PO4",
    "GOL", "EDO", "ACT", "PEG", "DMS", "MPD", "NO3", "IOD", "BR", "MN",
    "FE", "CU", "NI", "CD", "CO", "CU1", "FMT", "TRS", "BME", "EPE",
}
MIN_LIGAND_ATOMS = 8
POCKET_RADIUS = 4.0
RCSB_SDF = "https://files.rcsb.org/ligands/download/{code}_ideal.sdf"


def het_instances(pdb_text: str) -> dict[str, list[list[tuple[float, float, float]]]]:
    """리간드 코드 -> 사본 목록. 사본은 (chain, resseq, icode) 로 가른다.

    예전에는 코드로만 묶어서 한 코드의 모든 사본을 한 덩어리로 합쳤다. NAG 처럼
    당사슬로 여러 자리에 붙는 리간드에서는 그 덩어리의 중심이 어느 결합 자리도
    아니게 되고, 4 A 겹침은 아무 사본에나 걸리면 인정돼 후해진다. 그래서 중심
    이동 23 A 와 포켓 겹침 1.0 이 한 줄에 같이 적히는 모순이 나왔다.
    """
    inst: dict[tuple, list] = {}
    for line in pdb_text.splitlines():
        if not line.startswith("HETATM"):
            continue
        code = line[17:20].strip()
        if code in SKIP_HET or line[76:78].strip().upper() == "H":
            continue
        try:
            xyz = (float(line[30:38]), float(line[38:46]), float(line[46:54]))
        except ValueError:
            continue
        inst.setdefault((code, line[21], line[22:26].strip(), line[26]), []).append(xyz)
    out: dict[str, list[list]] = {}
    for (code, *_), atoms in inst.items():
        if len(atoms) >= MIN_LIGAND_ATOMS:
            out.setdefault(code, []).append(atoms)
    return out


def protein_only(pdb_text: str) -> str:
    """도킹 입력에서 리간드를 뺀다. 넣어두면 답을 주고 푸는 셈이다."""
    keep = [ln for ln in pdb_text.splitlines()
            if ln.startswith("ATOM") or ln[:3] == "TER" or ln[:5] == "MODEL"
            or ln[:6] == "ENDMDL"]
    return "\n".join(keep) + "\n"


def centroid(points):
    n = len(points)
    return tuple(sum(p[i] for p in points) / n for i in range(3))


def dist(a, b) -> float:
    return math.sqrt(sum((a[i] - b[i]) ** 2 for i in range(3)))


def sdf_coords(sdf_text: str) -> list[tuple[float, float, float]]:
    lines = sdf_text.splitlines()
    if len(lines) < 4:
        return []
    try:
        n_atoms = int(lines[3][0:3])
    except ValueError:
        return []
    out = []
    for line in lines[4:4 + n_atoms]:
        try:
            x, y, z = float(line[0:10]), float(line[10:20]), float(line[20:30])
        except ValueError:
            continue
        if line[31:34].strip().upper() != "H":
            out.append((x, y, z))
    return out


def fetch_ideal_sdf(code: str, cache: Path) -> str | None:
    """RCSB 의 이상화 좌표. 도킹 입력이지 정답이 아니다 - 정답은 결정 좌표다."""
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / f"{code}_ideal.sdf"
    if path.exists():
        return path.read_text(encoding="utf-8")
    try:
        with urllib.request.urlopen(RCSB_SDF.format(code=code), timeout=30) as r:
            text = r.read().decode("utf-8", "replace")
    except Exception as exc:
        print(f"  [{code}] SDF 내려받기 실패: {type(exc).__name__}", flush=True)
        return None
    path.write_text(text, encoding="utf-8")
    return text


def score_pose(pose_coords, copies) -> dict:
    """가장 가까운 **한 사본**에 대해 두 지표를 낸다.

    두 지표가 같은 사본을 가리켜야 서로 모순되지 않는다. 사본을 합쳐놓고 재면
    "중심은 23 A 떨어졌는데 겹침은 100%" 같은 값이 나오고, 그건 자세가 좋다는
    뜻도 나쁘다는 뜻도 아니다.
    """
    if not pose_coords or not copies:
        return {"centroid_shift": None, "pocket_overlap": None, "n_crystal_copies": 0}
    pose_c = centroid(pose_coords)
    best = min(copies, key=lambda atoms: dist(pose_c, centroid(atoms)))
    shift = dist(pose_c, centroid(best))
    inside = sum(1 for p in pose_coords
                 if min(dist(p, c) for c in best) <= POCKET_RADIUS)
    return {"centroid_shift": round(shift, 3),
            "pocket_overlap": round(inside / len(pose_coords), 4),
            "n_crystal_copies": len(copies),
            "matched_copy_atoms": len(best)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=["self", "redesign", "both"], default="both")
    parser.add_argument("--diffdock-url", default=_worker_url(18105))
    parser.add_argument("--designs-per-target", type=int, default=4)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    labels = list(csv.DictReader(
        (BASE / "backbones" / "backbone_labels.csv").open(encoding="utf-8")))
    targets = sorted({r["target_id"] for r in labels})

    jobs = []
    for target in targets:
        source = None
        for sub in ("cath_train", "cath_val", "cath_test"):
            cand = Path("/opt/protein_pipeline") / sub / f"{target}.pdb"
            if cand.exists():
                source = cand
                break
        if source is None:
            continue
        text = source.read_text(errors="replace")
        groups = het_instances(text)
        if not groups:
            continue
        # 가장 큰 사본을 가진 코드를 고른다. 사본 전체를 비교 대상으로 넘겨서
        # 점수는 그중 가장 가까운 하나에 대해 매긴다.
        code, copies = max(groups.items(),
                           key=lambda kv: max(len(a) for a in kv[1]))
        jobs.append({"target_id": target, "ligand_code": code,
                     "n_ligand_atoms": max(len(a) for a in copies),
                     "n_copies": len(copies), "crystal": copies,
                     "pdb_path": str(source), "protein_pdb": protein_only(text)})
    if args.limit:
        jobs = jobs[: args.limit]

    print(f"리간드 결합 타겟 {len(jobs)} 개")
    for job in jobs[:8]:
        print(f"  {job['target_id']:10s} {job['ligand_code']:5s} "
              f"원자 {job['n_ligand_atoms']}")
    if args.dry_run:
        return 0

    OUT.mkdir(parents=True, exist_ok=True)
    from pipeline_mcp.clients.local_http import LocalHTTPDiffDockClient  # noqa: E402
    client = LocalHTTPDiffDockClient(base_url=args.diffdock_url, token=None,
                                     timeout_s=3600.0)

    results = []
    for index, job in enumerate(jobs, start=1):
        sdf = fetch_ideal_sdf(job["ligand_code"], OUT / "ligands")
        if sdf is None:
            continue
        record = {k: job[k] for k in
                  ("target_id", "ligand_code", "n_ligand_atoms", "n_copies", "pdb_path")}
        print(f"[{index}/{len(jobs)}] {job['target_id']} + {job['ligand_code']}",
              flush=True)
        started = time.time()
        try:
            out = client.dock(protein_pdb=job["protein_pdb"], ligand_sdf=sdf,
                              complex_name=f"{job['target_id']}_{job['ligand_code']}")
            # 워커가 돌려주는 키는 sdf_text 다. 예전에는 "sdf" 를 읽었는데 그런
            # 키가 없어서 항상 빈 문자열이 나왔고, 좌표 0 개짜리 결과를 22/22
            # "ok" 로 적었다. 예외가 없다는 것과 결과가 있다는 것은 다르다.
            body = out or {}
            pose = sdf_coords(str(body.get("sdf_text") or body.get("sdf") or ""))
            if not pose:
                # 무엇이 왔는지 남긴다. 키 이름이 또 바뀌면 여기서 드러난다.
                # 워커 로그에 이유가 있으면 같이 남긴다 - "자세 없음" 만으로는
                # 배선 문제인지 입력 문제인지 구분할 수 없다. 실제로 여기서
                # 갈렸다: DiffDock 은 멀쩡했고 RDKit 이 우리가 넘긴 ideal SDF 를
                # 읽지 못한 것이었다.
                reason = ""
                for line in str(body.get("output", "")).replace("\\n", "\n").splitlines():
                    if "Failed to read molecule" in line or "could not read" in line:
                        reason = line.strip()[:200]
                        break
                record.update({"status": "no_pose",
                               "response_keys": sorted(body),
                               "sdf_text_len": len(str(body.get("sdf_text") or "")),
                               "worker_reason": reason or "워커 로그에 이유 없음",
                               "n_pose_atoms": 0,
                               "centroid_shift": None, "pocket_overlap": None})
                print(f"    자세 없음 · sdf_text {record['sdf_text_len']}자 · "
                      f"{record['worker_reason'][:110]}", flush=True)
            else:
                record.update({"status": "ok", **score_pose(pose, job["crystal"]),
                               "n_pose_atoms": len(pose)})
        except Exception as exc:
            record.update({"status": "failed",
                           "error": f"{type(exc).__name__}: {exc}"[:200]})
            print(f"    실패: {record['error']}", flush=True)
        record["elapsed_s"] = round(time.time() - started, 1)
        results.append(record)
        (OUT / "self_docking.json").write_text(json.dumps({
            "stage": "1_self_docking",
            "claim": "배선 점검이다. DiffDock 이 PDBBind 로 학습했고 이 복합체들이 "
                     "그 안에 있을 것이므로 검증이 아니다.",
            "metrics": {"centroid_shift": "예측 중심과 결정 리간드 중심의 거리 (A)",
                        "pocket_overlap": f"예측 원자 중 결정 리간드 {POCKET_RADIUS} A "
                                          f"안에 있는 비율"},
            "why_not_rmsd": "RDKit 이 없어 대칭 보정 RMSD 를 낼 수 없다. 대칭 리간드에서 "
                            "원자 대응 RMSD 는 틀린 값을 준다.",
            "code_sha": subprocess.run(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT,
                                       capture_output=True, text=True).stdout.strip(),
            "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "results": results,
        }, indent=2, ensure_ascii=False), encoding="utf-8")

    ok = [r for r in results if r.get("status") == "ok"]
    print(f"\n1 단계 완료 · ok {len(ok)}/{len(results)}")
    if ok:
        shifts = sorted(r["centroid_shift"] for r in ok if r["centroid_shift"] is not None)
        if shifts:
            print(f"  centroid_shift 중앙값 {shifts[len(shifts)//2]:.2f} A · "
                  f"2 A 이내 {sum(1 for s in shifts if s <= 2.0)}/{len(shifts)}")
    print(f"wrote {OUT / 'self_docking.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
