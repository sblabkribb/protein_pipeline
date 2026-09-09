"""동결된 v1 산출물이 기록된 해시와 어긋나면 실패한다.

RAPID_STRUCTURAL_V1_FREEZE.json 은 원고가 인용하는 데이터와 그것을 만든 코드의
SHA256 을 담는다. 어느 하나가 바뀌면 원고의 수치가 더 이상 그 파일에서 나온 것이
아니게 되므로, 조용히 지나가지 않게 여기서 막는다.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FREEZE = ROOT / "public_data" / "benchmark" / "gate0" / "RAPID_STRUCTURAL_V1_FREEZE.json"
SCRIPT = ROOT / "scripts" / "transcoder" / "42_freeze_v1_results.py"


def _freeze() -> dict:
    if not FREEZE.exists():
        pytest.skip(f"동결 기록 없음: {FREEZE}")
    return json.loads(FREEZE.read_text(encoding="utf-8"))


def test_recorded_hashes_still_match():
    if not SCRIPT.exists():
        pytest.skip("동결 스크립트 없음")
    done = subprocess.run([sys.executable, str(SCRIPT), "--verify"],
                          cwd=ROOT, capture_output=True, text=True)
    assert done.returncode == 0, (
        "동결된 산출물이 기록된 해시와 다르다. 재계산했다면 "
        "42_freeze_v1_results.py 를 다시 돌려 기록을 갱신하고, 원고와 "
        "results_of_record 의 수치도 함께 고쳐야 한다.\n" + done.stdout + done.stderr)


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
