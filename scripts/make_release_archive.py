#!/usr/bin/env python3
"""Zenodo 에 올릴 소스 릴리스 묶음을 만든다.

git 이 추적하는 파일에 재현에 필요한 미추적 입력·스크립트를 더해 임시 디렉터리에
모은 뒤, 공개하면 안 되는 문자열(내부 워커 주소, 워커 쪽 경로)을 가리고, 비밀값
패턴을 검사한 다음 tar.gz 로 묶는다. 원본 작업 트리는 바꾸지 않는다.

사용법:
    python3 scripts/make_release_archive.py --version 1.1.0 --out dist/
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: 추적되지 않지만 재현에 필요한 파일.
EXTRA = [
    "docs/reproducibility.md",
    "requirements-repro.txt",
    "scripts/benchmark/_compare_results.py",
    "scripts/benchmark/28_dedup_controlled_reeval.py",
    "scripts/benchmark/29_orthogonal_fold_check.py",
    "scripts/benchmark/30_epsilon_band_selection.py",
    "scripts/benchmark/make_figure1_orchestration.py",
    "scripts/benchmark/make_figure1_simple.py",
    "scripts/paper_runs/diversity_4arm.py",
    "scripts/make_repro_manifest.py",
    "scripts/make_zenodo_package.sh",
    "scripts/make_release_archive.py",
    "scripts/reproduce_paper_tables_figures.sh",
    "scripts/sanitize_public_data.py",
    "scripts/score_soluprot.py",
    "data/benchmark/hier_confirmatory_emb_320d.npz",
    "data/benchmark/v2_emb_320d.npz",
    "data/benchmark/depth_pilot_emb_320d.npz",
    "data/benchmark/holdout_grid_emb_320d.npz",
    "public_data/benchmark/gate0/hier_confirmatory/af2_order_metric.csv",
    "public_data/benchmark/gate0/hier_confirmatory/candidates.json",
    "public_data/benchmark/gate0/hier_confirmatory/mpnn_scores.json",
    "public_data/benchmark/gate0/hier_confirmatory/backbones.json",
    "public_data/benchmark/gate0/hier_confirmatory/campaign_summary.json",
    "public_data/benchmark/gate0/depth_pilot/af2_order_metric.csv",
    "public_data/benchmark/gate0/depth_pilot/candidates_ext.json",
    "public_data/benchmark/gate0/repro_manifest.json",
]

#: 넣지 않는다.
EXCLUDE = re.compile(r"(^|/)\.env($|\.)|heuristic-soluprot|bak-salvage|\.bak($|-)"
                     r"|(^|/)__pycache__/|(^|/)node_modules/|/af2_models/")

#: 공개본에서 가릴 문자열. 맨 IP 숫자열은 CATH 코드와 모양이 같아 넣지 않는다.
BASE_MASK = [
    (re.compile(r"https?://\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?"), "http://<internal-worker>"),
    (re.compile(r"/home/[A-Za-z0-9_.-]+/[A-Za-z0-9_./-]*"), "<worker-path>"),
]

#: 기관 고유의 호스트·도메인은 이 스크립트에 적지 않는다. 적어 두면 공개되는
#: 스크립트가 그 이름을 드러내기 때문이다. 대신 저장소 밖(또는 .gitignore 된)
#: 파일에서 한 줄에 하나씩 읽는다.
#:   host  <IP 또는 호스트명>      -> <internal-host>
#:   domain <등록 도메인>          -> <하위이름>.example.invalid
LOCAL_MASK = Path(os.environ.get("RELEASE_MASK_FILE",
                                 str(ROOT / "scripts" / ".release_mask.local")))


def load_local_mask():
    rules = []
    if not LOCAL_MASK.is_file():
        return rules
    for line in LOCAL_MASK.read_text("utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        kind, _, value = line.partition(" ")
        value = value.strip()
        lit = re.escape(value)
        esc = re.escape(value.replace(".", "\\."))   # 정규식 안의 이스케이프 형태
        if kind == "host":
            rules.append((re.compile(r"\b" + lit + r"\b"), "<internal-host>"))
            rules.append((re.compile(esc), "<internal-host>"))
        elif kind == "domain":
            rules.append((re.compile(r"\b" + lit + r"\b"), "example.invalid"))
            rules.append((re.compile(esc), "example\\.invalid"))
    return rules


MASK = BASE_MASK + load_local_mask()
TEXT = {".py", ".sh", ".md", ".txt", ".csv", ".json", ".tsv", ".yaml", ".yml",
        ".cff", ".toml", ".cfg", ".ini", ".js", ".html", ".css", ".tex"}

#: 비밀값 패턴 (docs/release_checklist.md 7번과 같다).
#: 값은 영숫자 16자 이상이고 숫자를 하나 이상 포함할 때만 잡는다. 이렇게 해야
#: 셸 변수 참조("$X"), 자리표시 이름(thermomp-ddg-local), 검사용 정규식 문자열을
#: 실제 비밀값으로 오인하지 않는다.
_VAL = r"[\"']?(?=[A-Za-z0-9_\-]*\d)[A-Za-z0-9_\-]{16,}"
SECRET = re.compile(r"((?:RUNPOD_API_KEY|ENDPOINT_ID|AWS_SECRET_ACCESS_KEY|SECRET_KEY|ZENODO_TOKEN)="
                    + _VAL + r"|-----BEGIN [A-Z ]*PRIVATE KEY-----|\bAKIA[0-9A-Z]{16}\b)")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", required=True)
    ap.add_argument("--out", default=str(ROOT / "dist"))
    ap.add_argument("--ref", default="HEAD",
                    help="내보낼 커밋. 묶음이 이 커밋과 정확히 일치한다 (기본 HEAD)")
    a = ap.parse_args(argv)

    name = f"protein_pipeline-{a.version}"
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    stage = out / name
    if stage.exists():
        shutil.rmtree(stage)

    #: 작업 트리가 아니라 커밋에서 내보낸다. 미커밋 변경이 섞이지 않게 한다.
    src_root = out / f".{name}-src"
    if src_root.exists():
        shutil.rmtree(src_root)
    src_root.mkdir(parents=True)
    arch = subprocess.run(["git", "archive", "--format=tar", a.ref], cwd=ROOT,
                          check=True, capture_output=True).stdout
    with tarfile.open(fileobj=__import__("io").BytesIO(arch)) as tf:
        tf.extractall(src_root)
    commit = subprocess.run(["git", "rev-parse", a.ref], cwd=ROOT, check=True,
                            capture_output=True, text=True).stdout.strip()

    files = sorted(str(p.relative_to(src_root)) for p in src_root.rglob("*")
                   if p.is_file() and not EXCLUDE.search(str(p.relative_to(src_root))))
    missing = [f for f in EXTRA if not (src_root / f).is_file()]

    masked = 0
    for rel in files:
        dst = stage / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        src = src_root / rel
        if src.suffix.lower() in TEXT:
            try:
                text = src.read_text("utf-8")
            except UnicodeDecodeError:
                shutil.copy2(src, dst)
                continue
            for pat, rep in MASK:
                text, n = pat.subn(rep, text)
                masked += n
            dst.write_text(text, "utf-8")
            shutil.copystat(src, dst)
        else:
            shutil.copy2(src, dst)

    hits = []
    for p in stage.rglob("*"):
        if p.is_file() and p.suffix.lower() in TEXT:
            t = p.read_text("utf-8", errors="replace")
            for m in SECRET.finditer(t):
                hits.append(f"{p.relative_to(stage)}: {m.group(0)[:24]}…")
            for pat, _ in MASK:
                if pat.search(t):
                    hits.append(f"{p.relative_to(stage)}: 내부 주소 잔존")
                    break
    if hits:
        print("중단한다. 공개하면 안 되는 문자열이 남아 있다:")
        for h in hits[:20]:
            print("  -", h)
        return 1

    tgz = out / f"{name}.tar.gz"
    with tarfile.open(tgz, "w:gz") as tf:
        tf.add(stage, arcname=name)
    digest = hashlib.sha256(tgz.read_bytes()).hexdigest()
    (out / f"{name}.tar.gz.sha256").write_text(f"{digest}  {tgz.name}\n")

    shutil.rmtree(src_root)
    print(f"커밋 {commit[:12]} · 파일 {len(files)}개 · 가린 문자열 {masked}건 · 비밀값 검사 통과")
    if missing:
        print(f"경고: 재현에 필요한데 커밋에 없는 파일 {len(missing)}개: {missing[:6]}")
    print(f"{tgz}  {tgz.stat().st_size / 1048576:.1f} MB")
    print(f"sha256 {digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
