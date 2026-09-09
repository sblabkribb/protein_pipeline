#!/usr/bin/env python3
"""MODEL_REGISTRY_V1.yaml → MODEL_REGISTRY_V1.json 미러 생성.

YAML 이 정본이고 JSON 은 **생성물**이다. 런타임이 표준 라이브러리만으로 읽을 수
있도록 두는 것이지 따로 편집하라고 두는 것이 아니다. 손으로 고치면 두 파일이
말이 달라지고, 어느 쪽이 맞는지 알 방법이 없어진다.

  python3 scripts/regenerate_registry_mirror.py            생성
  python3 scripts/regenerate_registry_mirror.py --check    다르면 종료코드 1
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

REGISTRY_DIR = (Path(__file__).resolve().parents[1]
                / "pipeline-mcp" / "src" / "pipeline_mcp" / "model_registry")
YAML_PATH = REGISTRY_DIR / "MODEL_REGISTRY_V1.yaml"
JSON_PATH = REGISTRY_DIR / "MODEL_REGISTRY_V1.json"

#: 현재 JSON 과 바이트 단위로 같아지는 설정. 바꾸면 미러 전체가 diff 로 잡힌다.
DUMP = {"indent": 2, "ensure_ascii": False}


def render() -> str:
    source = yaml.safe_load(YAML_PATH.read_text(encoding="utf-8"))
    return json.dumps(source, **DUMP) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="생성 결과와 현재 파일이 다르면 실패한다")
    args = ap.parse_args()

    want = render()
    have = JSON_PATH.read_text(encoding="utf-8") if JSON_PATH.exists() else ""
    if args.check:
        if want != have:
            print("미러가 YAML 과 다르다. "
                  "python3 scripts/regenerate_registry_mirror.py 로 다시 만든다.")
            return 1
        print(f"미러 일치 ({len(have)} 바이트)")
        return 0
    if want == have:
        print("변경 없음")
        return 0
    JSON_PATH.write_text(want, encoding="utf-8")
    print(f"wrote {JSON_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
