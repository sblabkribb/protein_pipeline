#!/usr/bin/env python3
"""폐기된 지표로 만들어진 산출물에 그 사실을 새긴다.

레지스트리(rapid_sr/provenance.py)만으로는 부족하다. 파일을 여는 사람이 늘
레지스트리를 함께 보지는 않고, CSV 는 특히 그냥 열린다. 그래서 파일 옆에
`.STATUS.json` 을 두고, JSON 산출물에는 최상위에 도장을 찍는다.

지우거나 옮기지 않는다. 그 파일들은 무엇이 틀렸는지의 기록이고, 재계산 결과와
대조할 대상이기도 하다.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "scripts" / "transcoder"))

from rapid_sr.provenance import (  # noqa: E402
    CORRESPONDENCE_HISTORY, METRIC_STATUS, VALID_CORRESPONDENCE, artifact_status,
)

BASE = PROJECT_ROOT / "public_data" / "benchmark" / "gate0"
STAMP_KEY = "_metric_status"


def stamp_json(path: Path, status: dict) -> bool:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    if not isinstance(payload, dict):
        return False
    # 최상위 첫 열쇠로 넣는다. 파일을 열면 바로 보여야 한다.
    stamped = {STAMP_KEY: status}
    stamped.update({k: v for k, v in payload.items() if k != STAMP_KEY})
    path.write_text(json.dumps(stamped, indent=2, ensure_ascii=False), encoding="utf-8")
    return True


def sidecar(path: Path, status: dict) -> Path:
    """CSV 옆에 두는 상태 파일. CSV 자체는 건드리지 않는다 - 헤더에 주석을
    넣으면 읽는 코드가 깨진다."""
    out = path.with_suffix(path.suffix + ".STATUS.json")
    out.write_text(json.dumps(status, indent=2, ensure_ascii=False), encoding="utf-8")
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    summary = {"stamped": [], "sidecar": [], "missing": [], "valid": []}
    for rel, entry in METRIC_STATUS.items():
        path = BASE / rel
        status = {
            **artifact_status(rel),
            "artifact": rel,
            "valid_correspondence_now": VALID_CORRESPONDENCE,
            "correspondence_history": CORRESPONDENCE_HISTORY,
        }
        if not path.exists():
            summary["missing"].append(rel)
            continue
        if entry["status"] == "valid":
            # 유효한 것에도 왜 유효한지를 남긴다. 나중에 "이건 왜 안 고쳤나" 를
            # 다시 묻지 않기 위해서다.
            summary["valid"].append(rel)
        if args.dry_run:
            continue
        if path.suffix == ".json":
            if stamp_json(path, status):
                summary["stamped"].append(rel)
            else:
                summary["sidecar"].append(str(sidecar(path, status).relative_to(BASE)))
        else:
            summary["sidecar"].append(str(sidecar(path, status).relative_to(BASE)))

    index = {
        "valid_correspondence": VALID_CORRESPONDENCE,
        "correspondence_history": CORRESPONDENCE_HISTORY,
        "artifacts": {rel: artifact_status(rel) for rel in METRIC_STATUS},
        "note": (
            "폐기된 correspondence 로 만들어진 파일을 지우지 않는다. 무엇이 틀렸는지의 "
            "기록이고, 재계산 결과와 대조할 대상이다."
        ),
    }
    if not args.dry_run:
        (BASE / "METRIC_STATUS.json").write_text(
            json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")

    for name, items in summary.items():
        if items:
            print(f"{name}: {len(items)}")
            for item in items:
                print(f"  {item}")
    if not args.dry_run:
        print(f"\nwrote {BASE / 'METRIC_STATUS.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
