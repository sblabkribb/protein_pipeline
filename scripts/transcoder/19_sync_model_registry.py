#!/usr/bin/env python3
"""MODEL_REGISTRY_V1.yaml 에서 런타임이 읽을 JSON 미러를 만든다.

왜 미러가 필요한가. 배포는 파일 복사 + systemd 재시작이고 중간에 pip install
단계가 없다. 서비스가 PyYAML 에 의존하면 그 라이브러리가 우연히 설치된
환경에서만 동작한다 - prod venv 에는 있었고 dev venv 에는 없어서, guided
화면의 plan_from_objective / explain_plan / approve_plan 이 한꺼번에 죽었다.

YAML 은 계속 사람이 쓰는 원본이다. 그 파일의 주석이 레지스트리의 문서이고
JSON 은 주석을 담을 수 없다. 그래서 원본은 YAML, 런타임은 JSON 이고, 둘이
어긋나면 테스트가 잡는다.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "pipeline-mcp" / "src"))

from pipeline_mcp.model_routing import (  # noqa: E402
    REGISTRY_JSON_PATH, REGISTRY_PATH, read_yaml_source,
)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--yaml", type=Path, default=REGISTRY_PATH)
    parser.add_argument("--json", type=Path, default=REGISTRY_JSON_PATH)
    parser.add_argument("--check", action="store_true",
                        help="쓰지 않고 어긋났는지만 확인한다. 어긋나면 종료 코드 1.")
    args = parser.parse_args(argv)

    source = read_yaml_source(args.yaml)
    # 키를 정렬하면 안 된다. purposes 의 선언 순서는 의미를 갖는다 - 가장 검증된
    # 경로가 먼저 오고, 화면은 그 순서를 기본 선택에 쓴다. 정렬하면 알파벳순이
    # 되어 실행조차 못 하는 antibody_design 이 맨 앞에 온다.
    rendered = json.dumps(source, indent=2, ensure_ascii=False) + "\n"

    if args.check:
        current = args.json.read_text(encoding="utf-8") if args.json.exists() else ""
        if current != rendered:
            print(f"{args.json} 이 {args.yaml} 과 어긋났다. --check 없이 다시 실행한다.",
                  file=sys.stderr)
            return 1
        print(f"{args.json.name} 은 원본과 일치한다.")
        return 0

    args.json.write_text(rendered, encoding="utf-8")
    print(f"wrote {args.json} ({len(source.get('models', {}))} models, "
          f"{len(source.get('purposes', {}))} purposes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
