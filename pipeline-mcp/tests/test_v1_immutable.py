"""v2 작업 중 frozen v1 정책 코드가 바뀌면 실패한다.

왜 해시가 아니라 태그와도 대조하는가
------------------------------------
freeze manifest 는 사람이 다시 만들 수 있다. 정책을 고치고 manifest 를 다시
생성하면 해시는 다시 일치하고 아무도 눈치채지 못한다. 태그
`rapid_structural_v1` 은 논문이 검증한 시점을 가리키므로, 그것과 직접 대조해야
"동결" 이 성립한다.

두 파일을 모두 보는 이유는 둘이 다르고 둘 다 쓰이기 때문이다.
`pipeline_mcp/allocation.py` 는 런타임 정본이고, `rapid_sr/allocation.py` 는
논문 재현 사본으로 `16_allocation_budget_simulation.py` 가 쓴다.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FREEZE = ROOT / "public_data" / "benchmark" / "gate0" / "RAPID_STRUCTURAL_V1_FREEZE.json"
TAG = "rapid_structural_v1"

#: 이 두 파일은 v2 작업 내내 byte-identical 로 남는다.
FROZEN_POLICY = (
    "pipeline-mcp/src/pipeline_mcp/allocation.py",
    "scripts/transcoder/rapid_sr/allocation.py",
)


def _freeze() -> dict:
    if not FREEZE.exists():
        pytest.skip(f"동결 기록 없음: {FREEZE}")
    return json.loads(FREEZE.read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True)


@pytest.mark.parametrize("rel", FROZEN_POLICY)
def test_policy_file_matches_the_tag(rel):
    """태그 시점의 내용과 바이트 단위로 같아야 한다."""
    if _git("rev-parse", "--verify", TAG).returncode != 0:
        pytest.skip(f"태그 {TAG} 없음")
    tagged = _git("show", f"{TAG}:{rel}")
    assert tagged.returncode == 0, f"{rel} 이 태그 {TAG} 에 없다"
    now = (ROOT / rel).read_bytes()
    assert now == tagged.stdout, (
        f"{rel} 이 {TAG} 이후 바뀌었다. v1 정책은 v2 작업 중 수정하지 않는다 - "
        f"바꿔야 한다면 리팩터링이 아니라 정책 변경이므로 새 프로파일로 만든다.")


@pytest.mark.parametrize("rel", FROZEN_POLICY)
def test_policy_file_is_pinned_in_the_manifest(rel):
    """manifest 에 들어 있고 해시가 맞아야 한다."""
    entry = next((e for e in _freeze()["code"].values() if e["path"] == rel), None)
    assert entry is not None, (
        f"{rel} 이 freeze manifest 에 없다. 수정 금지로 선언한 파일은 해시가 "
        f"걸려 있어야 드리프트를 잡는다.")
    assert entry["sha256"] == _sha(ROOT / rel)


def test_manifest_has_a_known_schema_version():
    got = _freeze().get("schema_version")
    assert got is not None, "manifest 에 schema_version 이 없다"
    assert got == 2, (
        f"모르는 기록 형식 {got!r}. 형식이 바뀌면 해시 비교가 같은 것을 "
        f"비교하는지 알 수 없다.")


def test_no_duplicate_normalized_paths():
    """정규화 경로가 겹치면 한 항목이 다른 항목을 덮는다.

    실제로 났던 사고다 - code 를 basename 으로 키잉해서 두 allocation.py 가
    충돌했고, 새 항목이 런타임 사본의 해시를 조용히 대체했다.
    """
    freeze = _freeze()
    for group in ("artifacts", "code"):
        paths = [e["path"] for e in freeze[group].values() if e.get("present")]
        dupes = {p for p in paths if paths.count(p) > 1}
        assert not dupes, f"{group}: 경로 중복 {sorted(dupes)}"
    # 두 사본이 모두 살아 있는지 - 충돌이 있었다면 하나가 사라진다
    code_paths = {e["path"] for e in freeze["code"].values()}
    for rel in FROZEN_POLICY:
        assert rel in code_paths, f"{rel} 이 manifest 에서 빠졌다"
