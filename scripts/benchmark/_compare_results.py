#!/usr/bin/env python3
"""두 결과 JSON 의 모든 수치를 비교한다.

사용법: _compare_results.py <원본.json> <재현.json> [허용 상대오차]
불일치가 있으면 종료 코드 1 을 돌려준다.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path


def walk(a, b, path, diffs, counter):
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k in a and k in b:
                walk(a[k], b[k], f"{path}/{k}", diffs, counter)
            else:
                diffs.append((f"{path}/{k}", "키 없음", ""))
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            diffs.append((path, f"길이 {len(a)}", f"길이 {len(b)}"))
            return
        for i, (x, y) in enumerate(zip(a, b)):
            walk(x, y, f"{path}[{i}]", diffs, counter)
    elif isinstance(a, (int, float)) and not isinstance(a, bool) \
            and isinstance(b, (int, float)) and not isinstance(b, bool):
        counter[0] += 1
        fa, fb = float(a), float(b)
        if math.isnan(fa) and math.isnan(fb):
            return
        if abs(fa - fb) > counter[1] * max(1.0, abs(fa)):
            diffs.append((path, a, b))
    elif a != b:
        diffs.append((path, a, b))


def main(argv) -> int:
    if len(argv) < 3:
        print(__doc__)
        return 2
    orig, repro = Path(argv[1]), Path(argv[2])
    tol = float(argv[3]) if len(argv) > 3 else 1e-9
    a = json.loads(orig.read_text("utf-8"))
    b = json.loads(repro.read_text("utf-8"))
    diffs, counter = [], [0, tol]
    walk(a, b, "", diffs, counter)
    name = orig.stem
    if diffs:
        print(f"  {name:34s} 수치 {counter[0]:6d}개 · 불일치 {len(diffs)}건")
        for p, x, y in diffs[:8]:
            print(f"      {p}: 원본 {x!r} / 재현 {y!r}")
        return 1
    print(f"  {name:34s} 수치 {counter[0]:6d}개 · 일치")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
