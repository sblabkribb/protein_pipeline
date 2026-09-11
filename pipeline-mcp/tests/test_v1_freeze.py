"""동결된 v1 산출물이 기록된 해시와 어긋나면 실패한다.

RAPID_STRUCTURAL_V1_FREEZE.json 은 원고가 인용하는 데이터와 그것을 만든 코드의
SHA256 을 담는다. 어느 하나가 바뀌면 원고의 수치가 더 이상 그 파일에서 나온 것이
아니게 되므로, 조용히 지나가지 않게 여기서 막는다.

예외가 하나 있다 (2026-09-11). `docs/results_of_record.md` 는 동결 산출물이
아니라 **살아 있는 인용 등기부**다 - 문서 첫머리의 규칙이 "이 표에 없는 수치는
원고에 넣지 않는다. 필요하면 먼저 여기에 추가한다" 이므로 결과가 확정될 때마다
절이 늘어나게 설계돼 있다. 그 파일에 불변 산출물의 전체 파일 해시를 걸어 둔
것이 잘못된 경계였다. 아래 `LIVING_REGISTRY` 를 보라 - 보호를 없앤 것이 아니라
`test_results_of_record.py` 로 옮겼다.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FREEZE = ROOT / "public_data" / "benchmark" / "gate0" / "RAPID_STRUCTURAL_V1_FREEZE.json"
SCRIPT = ROOT / "scripts" / "transcoder" / "42_freeze_v1_results.py"

#: 전체 파일 해시 대조에서 빼는 항목. **하나뿐이고 늘리지 않는다.**
#:
#: `docs/results_of_record.md` 는 설계상 계속 등재되는 등기부다. 여기에 불변
#: 산출물 해시를 걸면 Gate 1/2 판정을 규칙대로 등재하는 것만으로 27/27 이
#: 깨진다. 옳은 내용을 옳은 절차로 추가한 것이 실패의 원인이 되는 검사는
#: 지킬 수 없는 검사이고, 실제로 다섯 커밋 동안 빨간 상태로 방치됐다.
#:
#: 대신 이 파일의 v1 부분은 `test_results_of_record.py` 가 두 가지로 지킨다.
#:   1. v1 수치가 동결 산출물과 일치할 것 - 절 → 표의 행 → 부호까지.
#:   2. v1 시점 본문의 모든 줄이 지금도 그대로 있을 것 (덧붙이기만 허용).
#: 2 는 manifest 에 적힌 그 SHA256 을 **좌표**로 써서 v1 본문을 git 에서
#: 복원해 대조한다. digest 를 버리지 않고, 재발행하지도 않는다.
#:
#: 순서가 중요했다. 이 예외를 먼저 넣으면 보호가 실제로 준다 - 좁은 가드를
#: 조이기 전에는 인용 표의 한 칸을 고치는 것을 잡는 것이 이 digest 하나뿐이었고,
#: 그것을 red/green 으로 확인한 뒤에 뺐다.
#:
#: **이 우회는 이쪽에서만 유효하다.** `42_freeze_v1_results.py` 는 v1 동결
#: 도구이고 다른 워크스트림 소유라 손대지 않았다. 소유자가 그 스크립트의
#: ARTIFACTS 에서 `results_of_record` 를 빼면 (또는 living 항목으로 분리하면)
#: 이 집합을 비울 수 있고, --verify 는 26/26 으로 다시 초록이 된다.
LIVING_REGISTRY = {"artifacts/results_of_record"}

#: --verify 의 실패 줄: "  변경됨: artifacts/results_of_record · docs/..."
_CHANGED = re.compile(r"변경됨:\s*(\S+)\s*·")


def _freeze() -> dict:
    if not FREEZE.exists():
        pytest.skip(f"동결 기록 없음: {FREEZE}")
    return json.loads(FREEZE.read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_recorded_hashes_still_match():
    """동결 산출물·코드의 해시 대조. 살아 있는 등기부 한 항목만 제외한다."""
    if not SCRIPT.exists():
        pytest.skip("동결 스크립트 없음")
    done = subprocess.run([sys.executable, str(SCRIPT), "--verify"],
                          cwd=ROOT, capture_output=True, text=True)
    out = done.stdout + done.stderr
    if done.returncode == 0:
        return  # 소유자가 등기부를 ARTIFACTS 에서 뺐다면 여기로 온다
    changed = set(_CHANGED.findall(out))
    assert changed, (
        "--verify 가 실패했는데 변경 목록을 읽을 수 없다. 기록 형식이 바뀌었거나 "
        "다른 이유로 실패한 것이므로 그대로 실패로 둔다.\n" + out)
    unexpected = sorted(changed - LIVING_REGISTRY)
    assert not unexpected, (
        "동결된 산출물이 기록된 해시와 다르다. 재계산했다면 "
        "42_freeze_v1_results.py 를 다시 돌려 기록을 갱신하고, 원고와 "
        f"results_of_record 의 수치도 함께 고쳐야 한다.\n"
        f"  경계 밖의 변경: {unexpected}\n" + out)


def test_the_living_registry_exemption_stays_at_one_file():
    """예외는 한 파일이다. 늘어나면 더 이상 동결이 아니다.

    특히 `docs/manuscript.md` 는 예외가 아니다. 원고는 등기부와 달리 인용을
    받는 쪽이고, 지금도 v1 해시와 일치하며 일치해야 한다. 등기부 예외가
    "문서는 다 빼도 된다" 로 번지는 것을 여기서 막는다.
    """
    assert LIVING_REGISTRY == {"artifacts/results_of_record"}, (
        "등기부 예외가 늘어났다. 새 항목은 '왜 그 파일이 살아 있는 등기부인가' "
        "를 근거와 함께 남기고, 그 파일의 v1 부분을 대신 지킬 검사를 먼저 "
        "만들어야 한다.")
    freeze = _freeze()
    registry = freeze["artifacts"]["results_of_record"]
    assert registry["path"] == "docs/results_of_record.md"
    manuscript = freeze["artifacts"]["manuscript"]
    assert _sha(ROOT / manuscript["path"]) == manuscript["sha256"], (
        f"{manuscript['path']} 가 v1 해시와 다르다. 원고는 동결 대상이므로 "
        f"등기부 예외를 여기까지 넓히지 않는다.")


def test_every_frozen_artifact_is_committed():
    """작업트리에만 있는 파일을 해시해두면 그 상태로 돌아갈 수 없다."""
    freeze = _freeze()
    loose = [f"{group}/{role} -> {entry['path']} ({entry.get('git')})"
             for group in ("artifacts", "code")
             for role, entry in freeze[group].items()
             if entry.get("present") and entry.get("git") != "committed"]
    assert not loose, "동결 대상이 커밋되지 않았다:\n  " + "\n  ".join(loose)


def test_cohort_is_the_balanced_design():
    c = _freeze()["cohort"]
    assert c["ok"] == c["total_folds"] == 1728, "격자가 완전하지 않다"
    assert c["rfd3_balanced_cohort"]["n"] == 1440, "RFD3 코호트가 균형이 아니다"
    assert c["rfd3_balanced_cohort"]["n_backbones"] == 60
    # 지표 거부는 전부 native 여야 한다. RFD3 주 코호트에 들어오면 균형이 깨진다.
    assert set(c["metric_refusals"]["by_source"]) <= {"target"}, (
        "지표 거부가 RFD3 백본에도 생겼다 - 주 코호트가 더 이상 완전하지 않다")


def test_unsupported_claims_are_listed():
    """무엇을 주장하지 않는지가 기록에 남아 있어야 한다."""
    claims = _freeze()["claims_not_supported"]
    for key in ("ligand_self_docking", "stability_annotation",
                "condition_exploration", "panel2_policy_performance"):
        assert key in claims and claims[key].strip(), f"{key} 의 비주장 기록이 없다"
