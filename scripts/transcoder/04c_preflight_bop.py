#!/usr/bin/env python3
"""게이트 0 캠페인 전 워커 가용성 확인.

자격증명은 환경변수로만 받는다. 파일이나 artifact 에 쓰지 않는다.
어떤 arm 을 실제로 돌릴 수 있는지도 함께 판정한다.
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request

# (env_key, required). SoluProt 과 ColabFold, ProteinMPNN 이 없으면 캠페인이 성립하지 않는다.
ENDPOINTS = {
    "proteinmpnn": ("PROTEINMPNN_GPU_URL", True),
    "colabfold": ("COLABFOLD_URL", True),
    "soluprot": ("SOLUPROT_URL", True),
    "rfd3": ("RFD3_HTTP_URL", False),
    "bioemu": ("BIOEMU_HTTP_URL", False),
    "esm_embedding": ("ESM_EMBEDDING_URL", False),
}

# arm -> 그 arm 을 돌리는 데 필요한 워커. target arm 은 백본 생성기가 필요 없다.
ARM_REQUIREMENTS = {"target": None, "rfd3": "rfd3", "bioemu": "bioemu"}


def probe(url: str, *, timeout: float = 10.0) -> tuple[bool, str]:
    if not url:
        return False, "url not configured"
    # SOLUPROT_URL 처럼 경로가 붙은 경우를 위해 base 로 잘라 healthz 를 붙인다.
    base = url.split("//", 1)
    prefix = base[0] + "//" if len(base) == 2 else ""
    rest = base[1] if len(base) == 2 else base[0]
    host = rest.split("/", 1)[0]
    health = f"{prefix}{host}/healthz"
    try:
        with urllib.request.urlopen(health, timeout=timeout) as response:
            return response.status == 200, f"HTTP {response.status}"
    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code}"
    except Exception as exc:
        return False, type(exc).__name__


def summarise(checks: list[dict]) -> dict[str, object]:
    by_name = {check["name"]: check for check in checks}
    blocking = [c["name"] for c in checks if c["required"] and not c["ok"]]
    degraded = [c["name"] for c in checks if not c["required"] and not c["ok"]]

    available_arms: list[str] = []
    for arm, requirement in ARM_REQUIREMENTS.items():
        if requirement is None:
            available_arms.append(arm)
        elif by_name.get(requirement, {}).get("ok"):
            available_arms.append(arm)
    order = list(ARM_REQUIREMENTS)
    available_arms.sort(key=order.index)

    return {
        "ready": not blocking,
        "blocking": blocking,
        "degraded": degraded,
        "available_arms": available_arms,
        "checks": checks,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args(argv)

    checks = []
    for name, (env_key, required) in ENDPOINTS.items():
        url = os.environ.get(env_key, "")
        ok, detail = probe(url, timeout=args.timeout)
        checks.append({
            "name": name, "ok": ok, "detail": detail,
            "required": required, "env_key": env_key,
        })

    summary = summarise(checks)
    print(json.dumps(summary, indent=2))
    return 0 if summary["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
