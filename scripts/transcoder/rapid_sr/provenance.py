"""어떤 산출물이 어떤 대응으로 만들어졌고, 그래서 지금 유효한지.

구조 지표의 대응 방식이 세 번 바뀌었다. 그 사이에 만들어진 파일이 디스크에
남아 있고, 파일만 봐서는 어느 대응으로 쟀는지 알 수 없다. 표시하지 않으면
누군가 - 나를 포함해 - 그 숫자를 다시 읽는다.

전부 무효로 묶지 않는다. SoluProt 과 생성 다양성은 RMSD 를 거치지 않으므로
그대로 유효하고, 재현성 보고의 pLDDT 대조도 마찬가지다. 멀쩡한 결과까지 버리면
다시 재야 할 것이 늘어난다.
"""

from __future__ import annotations

#: 지금 유효한 대응.
VALID_CORRESPONDENCE = "folded_sequence_order"

CORRESPONDENCE_HISTORY = {
    "kabsch_all_ca_file_order": {
        "valid": False,
        "used_until": "2026-09-06",
        "defect": (
            "전체 CA 를 파일 순서로 짝지었다. 대응 자체는 대체로 맞았지만 loop 와 "
            "말단이 포함되어, non-loop 에서 정해진 2.0 A 임계값이 다른 것을 뜻했다."
        ),
        "evidence": (
            "1bg5A03 의 같은 모델에서 전체 CA 22.6 A 대 non-loop 1.32 A. "
            "loop 가 많은 백본은 어떤 설계도 통과하지 못했다."
        ),
    },
    "ca_rmsd_dssp_non_loop_resnum": {
        "valid": False,
        "used_until": "2026-09-06",
        "defect": (
            "마스크는 맞았지만 잔기 번호로 짝지었다. CATH 도메인은 잘려 나온 사슬의 "
            "번호를 유지하고 AF2 는 1..N 을 쓰므로, 오프셋 백본에서 대응이 통째로 "
            "밀리거나(1af7A01) 아예 비었다(1bctA00). 157 개 중 36 개가 해당한다."
        ),
        "evidence": (
            "같은 모델(pLDDT 92.97)에서 번호 대응 29.01 A 대 순서 대응 1.57 A. "
            "1eruA00 처럼 1 번에서 시작하는 백본은 0.33 A 로 양쪽이 같다."
        ),
    },
    VALID_CORRESPONDENCE: {
        "valid": True,
        "adopted": "2026-09-06",
        "defect": "",
        "evidence": (
            "12 폴드(오프셋 6, 비오프셋 6)에서 번호 이동 불변, fail-closed, 두 변형 "
            "저장, 중첩 시각 확인까지 통과. structural_metric_verification.json."
        ),
    },
}

#: RMSD 를 거쳐 나오는 endpoint. 이것들만 무효화 대상이다.
_RMSD_DERIVED = frozenset({
    "structural_yield", "joint_yield", "af2_structural_pass_yield",
    "joint_pass_yield", "rmsd", "rmsd_all_ca", "rmsd_all_positions",
})


def is_rmsd_derived(endpoint: str) -> bool:
    return str(endpoint).strip().lstrip("_") in _RMSD_DERIVED


_SUPERSEDED_REASON = (
    "superseded correspondence 로 계산되었다. 올바른 대응으로 다시 계산하기 전까지 "
    "구조 관련 수치를 읽으면 안 된다."
)

METRIC_STATUS = {
    # --- 무효: 폐기된 대응으로 만들어진 값 --------------------------------
    "temperature_sweep/af2_stage1.csv": {
        "status": "invalid",
        "correspondence": "kabsch_all_ca_file_order",
        "reason": _SUPERSEDED_REASON,
        "still_valid": ["soluprot", "plddt"],
        "replaced_by": "temperature_sweep/af2_order_metric.csv",
    },
    "temperature_sweep/af2_stage1_rmsd_fixed.csv": {
        "status": "invalid",
        "correspondence": "ca_rmsd_dssp_non_loop_resnum",
        "reason": _SUPERSEDED_REASON,
        "still_valid": ["soluprot", "plddt"],
        "replaced_by": "temperature_sweep/af2_order_metric.csv",
    },
    "temperature_panel2/af2_stage1.csv": {
        "status": "invalid",
        "correspondence": "ca_rmsd_dssp_non_loop_resnum",
        "reason": _SUPERSEDED_REASON,
        "still_valid": ["soluprot", "plddt"],
        "replaced_by": "temperature_panel2/af2_order_metric.csv",
    },
    "temperature_sweep/af2_analysis.json": {
        "status": "invalid",
        "correspondence": "kabsch_all_ca_file_order",
        "reason": (
            "structural_yield 와 joint_yield 로 낸 온도 결론은 폐기된 correspondence 에 "
            "기대고 있다. 포화 진단과 expand_backbones 판정도 그 위에서 나왔다."
        ),
        "still_valid": ["soluprot 연속 endpoint", "pLDDT 연속 endpoint"],
        "replaced_by": "corrected metric 으로 재계산 후 다시 생성",
    },
    # --- 일부 유효 -----------------------------------------------------
    "temperature_sweep/af2_rerun_reproducibility.json": {
        "status": "partially_valid",
        "correspondence": "ca_rmsd_dssp_non_loop_resnum",
        "reason": (
            "pLDDT 재현성(평균 |delta| 0.1203, prediction_only 0)은 RMSD 를 거치지 "
            "않으므로 유효하다. 통과 변화의 원인 귀속은 폐기된 correspondence 의 "
            "RMSD 게이트를 썼으므로 무효다."
        ),
        "still_valid": ["pLDDT delta 분포", "pLDDT 게이트 뒤집힘 수"],
        "invalid_parts": ["attribution", "metric_definition_only", "confounded"],
    },
    # --- 유효: RMSD 를 거치지 않음 --------------------------------------
    "temperature_sweep/conditions.csv": {
        "status": "valid",
        "correspondence": "",
        "reason": "생성 단계의 서열 통계다. 구조 지표를 거치지 않는다.",
        "still_valid": ["positional_entropy", "mean_pairwise_distance", "soluprot"],
    },
    "temperature_panel2/conditions.csv": {
        "status": "valid",
        "correspondence": "",
        "reason": "생성 단계의 서열 통계다. 구조 지표를 거치지 않는다.",
        "still_valid": ["positional_entropy", "mean_pairwise_distance", "soluprot"],
    },
    "backbones/backbone_labels.csv": {
        "status": "valid",
        "correspondence": "ca_rmsd_dssp_non_loop_resnum",
        "reason": (
            "캠페인은 pdb_renumber_resseq_from_1 을 켜고 돌았다(표본 60 개 run 전부). "
            "기준과 모델이 모두 1..N 이므로 번호 대응이 올바르게 작동했다. 데이터도 "
            "같은 말을 한다 - 오프셋 백본의 structural yield 가 오히려 높다"
            "(0.622 대 0.484). 프레임 시프트였다면 반대여야 한다."
        ),
        "still_valid": ["af2_structural_pass_yield", "joint_pass_yield", "soluprot_pass_yield"],
    },
    "gate0_target_level.json": {
        "status": "valid",
        "correspondence": "ca_rmsd_dssp_non_loop_resnum",
        "reason": "backbone_labels.csv 위에서 계산된다. 그 라벨이 유효하므로 AUC 도 유효하다.",
        "still_valid": ["AUC 0.7247", "paired C-B +0.0725"],
    },
}


def artifact_status(path: str) -> dict:
    """이 산출물이 지금 유효한가. 모르는 파일은 유효하다고 가정하지 않는다."""
    entry = METRIC_STATUS.get(str(path).strip())
    if entry is None:
        return {
            "status": "unknown",
            "reason": (
                "이 산출물의 지표 출처가 기록되어 있지 않다. 유효하다고 가정하지 "
                "않는다 - 세 가지 대응이 쓰였고 파일만 봐서는 구별되지 않는다."
            ),
            "still_valid": [],
        }
    return {**entry, "still_valid": list(entry.get("still_valid") or [])}
