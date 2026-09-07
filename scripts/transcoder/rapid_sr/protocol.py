"""게이트 0 고정 평가 프로토콜 (설계 6.1b).

백본끼리 yield 를 비교하려면 백본마다 조건이 같아야 한다. 여기 값이 바뀌면
artifact 에 기록되는 지문도 바뀌므로, 캠페인 도중에는 바꾸지 않는다.
"""

from __future__ import annotations

GATE0_THRESHOLDS = {
    "soluprot_min": 0.5,
    "plddt_min": 85.0,
    "rmsd_max": 2.0,
}

# 이 세 임계값이 어디서 왔는가. 셋 다 이 저장소의 측정으로 정해진 값이 아니다.
#
# 임계값을 데이터에서 고르고 같은 데이터로 결론을 내면 그 결론은 순환이다.
# 그래서 값 자체보다 "언제 정해졌는가"가 중요하다. 셋 다 게이트 0 캠페인
# (2026-09-03)과 온도 패널보다 앞서므로, 폐기된 resnum 매칭 결과에서 역산된
# 값일 수 없다.
THRESHOLD_PROVENANCE = {
    "plddt_min": {
        "value": 85.0,
        "first_seen": "dc7cac0 (2026-01-06), 저장소 최초 커밋의 af2_plddt_cutoff 기본값",
        "changed_since": False,
        "basis": "convention_without_internal_calibration",
        "note": (
            "AF2 자체 신뢰 구간의 경계가 아니다. AF2 는 90 이상을 very high, "
            "70~90 을 confident 로 나누는데 85 는 그 안쪽이라 외부 근거가 없다. "
            "rmsd_max=2.0 이 설계 문헌의 관례인 것과 달리 85 는 그런 지지도 없다."
        ),
        "sensitivity_panel1": (
            "70~90 에서 전체 structural yield 는 0.623~0.367 로 크게 움직이지만 "
            "정보 백본 수는 2~5, 포화 백본은 10~13 으로 거의 그대로다. 패널 1 의 "
            "expand_backbones 판정은 임계값에 의존하지 않는다."
        ),
    },
    "rmsd_max": {
        "value": 2.0,
        "first_seen": "af2_rmsd_cutoff 기본값 (2026-01-28)",
        "changed_since": False,
        "basis": "convention_without_internal_calibration",
        "note": "설계 문헌에서 널리 쓰이는 값이다. 다만 이 저장소가 보정한 값은 아니다.",
    },
    "soluprot_min": {
        "value": 0.5,
        "first_seen": "dc7cac0 (2026-01-06), soluprot_cutoff 기본값",
        "changed_since": False,
        "basis": "convention_without_internal_calibration",
        "note": "SoluProt 이 확률로 보고하는 값의 중점이다.",
    },
    "how_to_change": (
        "온도 패널이나 게이트 0 결과로 이 값들을 다시 고르지 않는다. 바꾸려면 "
        "결론을 내는 데 쓰지 않는 별도 보정 세트가 필요하다."
    ),
}

# 구조 판정 지표의 동결 정의.
#
# 같은 임계값을 서로 다른 정의에 적용하면 결과가 조용히 뒤집힌다. 게이트 0
# 캠페인은 DSSP non-loop 위치에서, 1 차 온도 패널은 전체 CA 에서 RMSD 를 재면서
# 둘 다 2.0 A 를 적용했고, loop 가 많은 백본은 어떤 설계도 통과할 수 없었다.
# 같은 AF2 모델 여덟 개(1bg5A03, 254 잔기, non-loop 85 개)에서:
#
#     kabsch, 파일 순서, 전체 CA    13.3 - 22.8 A
#     ca_rmsd, resnum, 전체 위치    35.5 - 37.7 A
#     ca_rmsd, resnum, non-loop      1.15 - 1.86 A
#
# 확인된 것은 두 지표가 서로 다른 구조 영역을 잰다는 것이다. non-loop 는 이차구조
# 코어를, 전체 CA 는 loop 와 말단까지 포함한다. 그 유연 영역의 편차가 전체 CA 값을
# 지배한다. 정렬 오류였다면 resnum 매칭이 값을 줄였어야 하는데 오히려 늘었다.
#
# 이 정의가 유일한 출처다. Gate 0 와 sweep 이 같은 상수를 읽는다.
STRUCTURAL_METRIC_V1 = {
    "metric_id": "gate0_structural_v1",
    "frozen": True,
    "rmsd": {
        "method": "ca_rmsd_dssp_non_loop",
        "reference": "parent_backbone_input_pdb",
        # 마스크는 **기준 백본** 에서 뽑는다. AF2 출력에서 뽑으면 서열마다 다른
        # 위치를 재게 되어, 온도 비교가 지표 변화와 섞인다.
        "mask_source": "reference_backbone",
        "mask_scope": "once_per_backbone_applied_to_all_sequences_and_conditions",
        "pairing": "residue_number_and_insertion_code_per_chain",
        "superposition": "kabsch_ca",
        "cutoff_angstrom": 2.0,
    },
    "plddt": {"source": "best_plddt", "cutoff": 85.0},
    # 이진 통과 여부만 보면 0/1 포화에서 정보를 통째로 잃는다. 연속값을 함께
    # 기록해 같은 데이터에서 더 많은 것을 읽는다.
    "secondary_metrics": [
        {"name": "rmsd", "kind": "continuous",
         "note": "동결 정의의 연속값. 임계값 통과 여부보다 정보가 많다."},
        {"name": "plddt", "kind": "continuous", "note": "AF2 신뢰도. 측정이 아니다."},
        {"name": "soluprot", "kind": "continuous",
         "note": "가용성 예측 점수. 통과율과 달리 포화되지 않는다."},
        {"name": "rmsd_all_ca", "kind": "continuous",
         "note": "전체 CA, 파일 순서 정합. 유연 영역이 얼마나 벌어졌는지를 잰다."},
        {"name": "rmsd_all_positions", "kind": "continuous",
         "note": "전체 위치, resnum 정합. 위와 정합 방식만 다르다."},
        {"name": "positional_entropy", "kind": "continuous",
         "note": "생성 다양성. 값싼 단계에서 이미 측정된다."},
    ],
    "why_frozen": (
        "게이트 0 와 온도 패널이 같은 2.0 A 임계값을 서로 다른 RMSD 정의에 "
        "적용했다. non-loop 정의와 전체 CA 정의는 다른 구조 영역을 재며, 그 차이는 "
        "loop 와 말단의 편차가 지배한다."
    ),
}

# AF2 예측 설정. 재실행이 '재측정' 이 되려면 예측 조건이 같아야 한다.
#
# 클라이언트 기본값에 기대면 기본값이 바뀔 때 두 실행이 조용히 갈리고, RMSD 정의
# 수정과 run-to-run 차이가 섞인다. 그래서 여기에 못박고 실행마다 기록한다.
AF2_SETTINGS_V1 = {
    "model_preset": "monomer",
    "db_preset": "full_dbs",
    "max_template_date": "2020-05-14",
    "extra_flags": None,
    # 워커가 소유하는 것. 우리가 고정한다고 주장하지 않는다 - 기록만 한다.
    "not_controlled_here": [
        "random seed (ColabFold worker owns it)",
        "num_recycles",
        "MSA pipeline version and database snapshot",
    ],
    "reproducibility_reference": (
        "af2_reproducibility.json: 같은 서열 재실행의 |delta pLDDT| 평균 0.006, "
        "최대 0.011 (n=3). 타겟 내부 SD 0.556 대비 무시할 수준이지만 n 이 작다."
    ),
}

# 모든 백본에서 동일해야 하는 ProteinMPNN 설정.
GATE0_MPNN_SETTINGS = {
    "use_soluble_model": True,
    "model_name": "v_48_020",
    "sampling_temp": 0.1,
    "seed": 0,
    "batch_size": 1,
}

# 백본당 1차 생성 서열 수. 백본 간 동일해야 yield 비교가 성립한다.
#
# 예산 근거: AF2 호출 수 = (백본 수) x (백본당 서열 수) x (tier 수).
# `num_seq_per_tier` 는 파이프라인에서 **백본당** 값이므로
# (백본 10 x 서열 40 x tier 3) 은 run 당 1,200 폴딩이 되어 비현실적이다.
# 게이트 0 의 라벨은 백본 단위 yield 이고 tier 는 별개의 설계 축이므로
# 단일 tier 로 고정해 비용을 1/3 로 줄인다.
#
# 게이트 0 의 유효 표본은 서열 수가 아니라 **독립 백본 수**다. 같은 백본에서 서열을
# 더 뽑아도 백본 N 은 늘지 않는다. 그래서 1차로 16개만 돌려 백본 수를 빨리 늘리고,
# yield 가 애매한 백본만 16개를 더해 32개로 만든다(2단 생성).
#
# n=16 이면 비율 추정 표준오차가 p=0.5 에서 약 0.125, n=32 면 약 0.088 이다.
GATE0_SEQUENCES_PER_BACKBONE = 16

# 2차 보강 대상 판정 구간. 이 안에 들면 애매한 백본으로 보고 16개를 더 생성한다.
GATE0_TOPUP_YIELD_RANGE = (0.25, 0.75)
GATE0_TOPUP_SEQUENCES = 16

# 게이트 0 은 단일 tier 로 설계 프로토콜을 고정한다. tier 비교는 SP2 의 축이다.
GATE0_TIERS = [0.5]

# run 당 생성할 백본 수. run 당 AF2 = 5 x 20 x 1 = 100 회.
GATE0_BACKBONES_PER_RUN = 5

# AF2 실행 설정: 기본(full_dbs) 을 쓴다. single-sequence 로 바꾸지 않는다.
#
# `scripts/phase1_memory_bank/README.md` 는 "ProteinMPNN 설계 서열은 자연계에
# 없으므로 MSA 가 무의미하다"고 적고 있어 single-sequence 가 큰 비용 절감이 될
# 것으로 보였다. 실측(`04f_af2_msa_mode_probe.py`, 유휴 워커, 62aa 설계 4개)은
# 그 예상을 뒤집었다.
#
#   full_dbs         91.0s  pLDDT 87.02
#   single_sequence  64.5s  pLDDT 65.75
#   -> 1.41배 빨라지는 대신 pLDDT 가 21.3점 떨어진다
#
# 게이트 0 의 구조 통과 기준이 pLDDT >= 85 이므로 single-sequence 로는 거의
# 모든 설계가 탈락해 yield 라벨이 전부 0 이 된다. 29% 시간 절감으로 살 수 없는
# 손실이다. 또한 기존 CATH 라벨이 full_dbs 로 생성되어 있어 섞을 수도 없다.
#
# 결과 원본: `public_data/benchmark/gate0/af2_msa_mode_probe.json`
GATE0_AF2_EXTRA_FLAGS: str | None = None


def protocol_fingerprint() -> dict[str, object]:
    """artifact 에 그대로 실릴 프로토콜 스냅숏."""
    return {
        "thresholds": dict(GATE0_THRESHOLDS),
        "mpnn_settings": dict(GATE0_MPNN_SETTINGS),
        "sequences_per_backbone": GATE0_SEQUENCES_PER_BACKBONE,
        "topup_sequences": GATE0_TOPUP_SEQUENCES,
        "topup_yield_range": list(GATE0_TOPUP_YIELD_RANGE),
        "tiers": list(GATE0_TIERS),
        "backbones_per_run": GATE0_BACKBONES_PER_RUN,
        "af2_calls_per_run": (
            GATE0_BACKBONES_PER_RUN * GATE0_SEQUENCES_PER_BACKBONE * len(GATE0_TIERS)
        ),
        # AF2 설정이 다르면 pLDDT 를 다른 데이터와 섞을 수 없다. 지문에 남긴다.
        "af2_extra_flags": GATE0_AF2_EXTRA_FLAGS,
    }
