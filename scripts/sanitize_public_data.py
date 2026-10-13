#!/usr/bin/env python3
"""공개 배포본에서 내부 호스트 주소와 내부 경로를 가린다.

구조예측 격자의 `error` 열과 일부 메타데이터에는 실패 당시의 내부 워커 주소와
워커 쪽 파일 경로가 문자열로 남아 있다. 이 값은 어떤 분석에도 입력되지 않지만
(status 가 ok 가 아닌 행은 모든 로더가 건너뛴다) 공개하면 내부 구성이 드러난다.

원본을 바꾸지 않는다. `--out` 으로 지정한 디렉터리에 사본을 만들고 거기에서만
치환한다. `--check` 를 주면 치환하지 않고 남은 건수만 센다.

사용법:
    python3 scripts/sanitize_public_data.py --check
    python3 scripts/sanitize_public_data.py --out dist/public_data
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: 내부 구성을 드러내는 패턴과 공개본에서 쓸 대체 문자열.
#: 맨 IP 숫자열은 CATH 슈퍼패밀리 코드(예: 3.30.370.10)와 모양이 같으므로
#: 규칙에 넣지 않는다. 내부 주소는 언제나 URL 맥락에 나타난다.
RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"https?://\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?"),
     "http://<internal-worker>"),
    (re.compile(r"/home/[A-Za-z0-9_.-]+/[A-Za-z0-9_./-]*"), "<worker-path>"),
]

#: 치환 대상 텍스트 파일 확장자.
TEXT_SUFFIXES = {".csv", ".json", ".tsv", ".txt", ".md"}


def scan(text: str) -> int:
    return sum(len(p.findall(text)) for p, _ in RULES)


def sanitize(text: str) -> tuple[str, int]:
    n = 0
    for pat, rep in RULES:
        text, k = pat.subn(rep, text)
        n += k
    return text, n


def iter_files(base: Path):
    for p in sorted(base.rglob("*")):
        if p.is_file() and p.suffix.lower() in TEXT_SUFFIXES:
            yield p


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default=str(ROOT / "public_data"),
                    help="검사할 디렉터리 (기본: public_data)")
    ap.add_argument("--out", help="사본을 만들 디렉터리. 주지 않으면 검사만 한다.")
    ap.add_argument("--check", action="store_true", help="치환하지 않고 건수만 센다")
    a = ap.parse_args(argv)

    base = Path(a.base)
    if not base.is_dir():
        print(f"없는 디렉터리: {base}")
        return 2

    hits: list[tuple[Path, int]] = []
    for p in iter_files(base):
        try:
            text = p.read_text("utf-8", errors="replace")
        except OSError:
            continue
        n = scan(text)
        if n:
            hits.append((p, n))

    total = sum(n for _, n in hits)
    for p, n in hits:
        print(f"  {n:4d}건  {p.relative_to(base)}")
    print(f"총 {len(hits)}개 파일 · {total}건")

    if a.check or not a.out:
        return 1 if total else 0

    out = Path(a.out)
    if out.exists():
        print(f"이미 있는 경로라 중단한다: {out}")
        return 2
    shutil.copytree(base, out)

    changed = 0
    for p in iter_files(out):
        try:
            text = p.read_text("utf-8", errors="replace")
        except OSError:
            continue
        new, n = sanitize(text)
        if n:
            p.write_text(new, "utf-8")
            changed += n

    left = sum(scan(p.read_text("utf-8", errors="replace")) for p in iter_files(out))
    print(f"사본 {out} · 치환 {changed}건 · 남은 건수 {left}")
    return 0 if left == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
