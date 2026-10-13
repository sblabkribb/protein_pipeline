#!/usr/bin/env python3
"""벤치마크 격자의 서열을 SoluProt 으로 채점하고 soluprot 열을 채운다.

SoluProt 은 Python 3.7 과 scikit-learn 0.20.1 을 요구하므로 별도 환경에서 돈다.
이 스크립트는 그 환경의 인터프리터를 `--soluprot-python` 으로 받아 호출한다.

설치 (한 번만):
    # 1) SoluProt 1.0.1.0 과 데이터
    curl -L -o soluprot.zip 'https://loschmidt.chemi.muni.cz/soluprot/?f=soluprot.zip'
    unzip soluprot.zip
    # 2) 전용 환경
    micromamba create -y -n soluprot -c conda-forge \
        python=3.7 scikit-learn=0.20.1 biopython=1.74 pandas tqdm
    # 3) USEARCH (CC0 공개 도메인 배포본)
    curl -L -o usearch11 \
      https://raw.githubusercontent.com/rcedgar/usearch_old_binaries/main/bin/usearch11.0.667_i86linux64
    chmod +x usearch11

사용:
    python3 scripts/score_soluprot.py \
        --cohort public_data/benchmark/gate0/hier_confirmatory \
        --soluprot-dir /path/to/soluprot-1.0.1.0 \
        --soluprot-python /path/to/env/bin/python \
        --usearch /path/to/usearch11

TMHMM 은 별도 학술 등록이 필요해 재현성을 해치므로, 저자가 함께 배포하는
TMHMM 비의존 모델(grad_clf_v1_tc_notmhmm)을 쓴다(`--no_tmhmm`).
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
import tempfile
from pathlib import Path


def candidate_sequences(cohort: Path) -> dict[str, str]:
    """sequence_id -> 서열. 코호트마다 후보 파일 이름이 다르다."""
    for name in ("candidates.json", "candidates_ext.json"):
        p = cohort / name
        if p.is_file():
            return {c["sequence_id"]: c["sequence"]
                    for c in json.loads(p.read_text("utf-8"))}
    raise SystemExit(f"후보 파일이 없다: {cohort}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cohort", required=True, help="격자 디렉터리")
    ap.add_argument("--soluprot-dir", required=True, help="soluprot-1.0.1.0 경로")
    ap.add_argument("--soluprot-python", required=True, help="Python 3.7 환경의 인터프리터")
    ap.add_argument("--usearch", required=True, help="usearch 실행 파일")
    ap.add_argument("--out", help="격자 CSV 출력 경로. 기본은 제자리 갱신")
    ap.add_argument("--threads", type=int, default=4)
    a = ap.parse_args(argv)

    cohort = Path(a.cohort)
    grid = cohort / "af2_order_metric.csv"
    if not grid.is_file():
        raise SystemExit(f"격자가 없다: {grid}")

    seqs = candidate_sequences(cohort)
    rows = list(csv.DictReader(grid.open(encoding="utf-8")))
    needed = {r["sequence_id"] for r in rows if r["sequence_id"] in seqs}
    uniq: dict[str, list[str]] = {}
    for sid in sorted(needed):
        uniq.setdefault(seqs[sid], []).append(sid)
    print(f"후보 {len(needed)} · 고유 서열 {len(uniq)}")

    with tempfile.TemporaryDirectory(prefix="soluprot-") as tmp:
        tmpd = Path(tmp)
        fa = tmpd / "in.fasta"
        with fa.open("w") as fh:
            for i, s in enumerate(uniq):
                fh.write(f">u{i}\n{s}\n")
        out_csv = tmpd / "out.csv"
        cmd = [a.soluprot_python, "soluprot.py",
               "--i_fa", str(fa), "--o_csv", str(out_csv),
               "--tmp_dir", str(tmpd / "work"), "--no_tmhmm",
               "--usearch", a.usearch, "--no_proc", str(a.threads)]
        (tmpd / "work").mkdir()
        print("SoluProt 실행 중…", flush=True)
        r = subprocess.run(cmd, cwd=a.soluprot_dir)
        if r.returncode != 0 or not out_csv.is_file():
            raise SystemExit("SoluProt 실행에 실패했다")

        by_uid = {row["fa_id"]: float(row["soluble"])
                  for row in csv.DictReader(out_csv.open(encoding="utf-8"))}

    by_sid: dict[str, float] = {}
    for i, (_seq, sids) in enumerate(uniq.items()):
        score = by_uid.get(f"u{i}")
        if score is None:
            continue
        for sid in sids:
            by_sid[sid] = score
    print(f"점수 {len(by_sid)}건")

    fields = list(rows[0].keys())
    filled = 0
    for row in rows:
        if row["sequence_id"] in by_sid:
            row["soluprot"] = f"{by_sid[row['sequence_id']]:.6f}"
            filled += 1
    dst = Path(a.out) if a.out else grid
    with dst.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"{dst} · {len(rows)}행 중 {filled}행 갱신")
    return 0


if __name__ == "__main__":
    sys.exit(main())
