"""서열에서 직접 읽는 응집·개발가능성 지표와 (임시) 게이트.

antigen 파이프라인의 antibody_developability.py 에서 이식한 창 통계다. 계산은
scripts/transcoder/rapid_sr/liabilities.py (논문 재현본) 와 같다. 이 모듈이
파이프라인의 진실이고, 테스트가 두 사본의 일치를 고정한다.

**이것은 휴리스틱이다.** Kyte-Doolittle 소수성과 전하로 만든 창 통계일 뿐, 어떤
응집 측정에도 맞춰본 적이 없다. 창 통계의 임계값(폭 5, 소수성 2.0, 전하 1.0)은
항체 문맥에서 정해졌다. 단량체 재설계에 그대로 옮기면 그 근거가 따라오지 않는다.

**게이트는 임시(provisional)이다.** 운영 판단으로 게이트를 켜되, 임계값은
측정에 맞춘 것이 아니라 상속값에서 정한 초기값이다. 그래서:

- 모든 리포트에 ``calibrated: false`` 와 실제 쓴 임계값이 기록된다.
- 임계값은 환경변수로 바꿀 수 있다. 응집 측정 코호트가 생기면 그 코호트로
  다시 정하고 ``calibrated`` 를 true 로 바꾼다.
- ``PIPELINE_LIABILITY_GATE=0`` 으로 게이트를 끌 수 있다 (기록은 계속 된다).
"""

from __future__ import annotations

import os

#: Kyte-Doolittle 소수성 척도.
_KYTE_DOOLITTLE = {
    "A": 1.8, "R": -4.5, "N": -3.5, "D": -3.5, "C": 2.5,
    "Q": -3.5, "E": -3.5, "G": -0.4, "H": -3.2, "I": 4.5,
    "L": 3.8, "K": -3.9, "M": 1.9, "F": 2.8, "P": -1.6,
    "S": -0.8, "T": -0.7, "W": -0.9, "Y": -1.3, "V": 4.2,
}

#: 노출된 기름진 구간이 문제가 되기 시작하는 폭 (항체 문맥에서 상속).
PATCH_WINDOW = 5
#: 창이 응집 위험으로 세지려면 강하게 소수성이면서 전하가 거의 없어야 한다.
AGGREGATION_HYDROPATHY = 2.0
AGGREGATION_CHARGE = 1.0

METRIC_ID = "sequence_liabilities_v1"
GATE_ID = "sequence_liability_gate_v1"

#: 게이트 기본 임계값. 측정에 맞춘 값이 아니라 상속값에서 정한 초기값이다.
DEFAULT_MAX_PATCH = 2.5          # 최악 창의 평균 소수성 상한
DEFAULT_MAX_FRACTION = 0.10      # 응집 위험 창 비율 상한
DEFAULT_MAX_FREE_CYS = 0         # free cysteine 개수 상한
DEFAULT_MAX_NG_DG_MOTIFS = 2     # NG(탈아미드) + DG(이성질화) 모티프 상한


def gate_enabled() -> bool:
    """``PIPELINE_LIABILITY_GATE`` 로 게이트 on/off. 기본은 켜짐(운영 판단)."""
    return os.environ.get("PIPELINE_LIABILITY_GATE", "1").strip().lower() not in {
        "0", "false", "no", "off",
    }


def gate_thresholds() -> dict[str, float]:
    """게이트 임계값. 환경변수로 덮어쓸 수 있다."""
    def _float(name: str, default: float) -> float:
        raw = os.environ.get(name, "").strip()
        try:
            return float(raw)
        except (TypeError, ValueError):
            return float(default)

    return {
        "max_hydrophobic_patch": _float(
            "PIPELINE_AGGREGATION_GATE_MAX_PATCH", DEFAULT_MAX_PATCH
        ),
        "max_aggregation_prone_fraction": _float(
            "PIPELINE_AGGREGATION_GATE_MAX_FRACTION", DEFAULT_MAX_FRACTION
        ),
        "max_free_cysteine": _float(
            "PIPELINE_DEVELOPABILITY_GATE_MAX_FREE_CYS", DEFAULT_MAX_FREE_CYS
        ),
        "max_ng_dg_motifs": _float(
            "PIPELINE_DEVELOPABILITY_GATE_MAX_NG_DG_MOTIFS", DEFAULT_MAX_NG_DG_MOTIFS
        ),
        # 창 통계 자체의 상속값 (게이트 임계값이 아니다).
        "patch_window": PATCH_WINDOW,
        "aggregation_hydropathy": AGGREGATION_HYDROPATHY,
        "aggregation_charge": AGGREGATION_CHARGE,
    }


def _chains(sequence: str) -> tuple[str, ...]:
    """':' 로 이어 붙인 복합체 표기를 사슬로 나눈다."""
    return tuple(part for part in str(sequence or "").split(":") if part)


def _residue_charge(residue: str) -> float:
    if residue in {"K", "R"}:
        return 1.0
    if residue in {"D", "E"}:
        return -1.0
    # His 는 생리 pH 에서 대체로 중성이지만 0 으로 두면 His 가 많은 설계가
    # 무전하로 보고된다. 그래서 일부만 센다.
    return 0.1 if residue == "H" else 0.0


def net_charge(sequence: str) -> float:
    return round(
        sum(_residue_charge(r) for chain in _chains(sequence) for r in chain), 3
    )


def _windows(chain: str):
    if len(chain) <= PATCH_WINDOW:
        return [(0, chain)] if chain else []
    return [(i, chain[i : i + PATCH_WINDOW]) for i in range(len(chain) - PATCH_WINDOW + 1)]


def _hydropathy(window: str) -> float:
    if not window:
        return 0.0
    return sum(_KYTE_DOOLITTLE.get(r, 0.0) for r in window) / len(window)


def max_hydrophobic_patch(sequence: str) -> float | None:
    """가장 기름진 창의 평균 소수성. 서열이 없으면 None (0 이 아니다)."""
    scores = [_hydropathy(w) for chain in _chains(sequence) for _s, w in _windows(chain)]
    return round(max(scores), 3) if scores else None


def aggregation_prone_fraction(sequence: str) -> float:
    """응집 위험 창의 비율. 강하게 소수성이면서 전하가 거의 없는 창을 센다."""
    total = 0
    flagged = 0
    for chain in _chains(sequence):
        for _start, window in _windows(chain):
            total += 1
            charge = sum(abs(_residue_charge(r)) for r in window)
            if _hydropathy(window) >= AGGREGATION_HYDROPATHY and charge <= AGGREGATION_CHARGE:
                flagged += 1
    return round(flagged / total, 4) if total else 0.0


def motif_counts(sequence: str) -> dict[str, int]:
    """화학적 열화가 알려진 자리. 개수만 세고 위험도로 환산하지 않는다."""
    joined = "".join(_chains(sequence))
    pairs = [joined[i : i + 2] for i in range(len(joined) - 1)]
    return {
        "deamidation_NG": sum(1 for p in pairs if p == "NG"),
        "isomerisation_DG": sum(1 for p in pairs if p == "DG"),
        "oxidation_MW": sum(1 for r in joined if r in {"M", "W"}),
        "free_cysteine": joined.count("C"),
    }


def liability_report(sequence: str) -> dict:
    """한 서열의 응집·개발가능성 지표. 판정은 하지 않는다."""
    return {
        "metric_id": METRIC_ID,
        "kind": "heuristic",
        # 맞춰본 적이 없다는 사실이 값 옆에 늘 붙어 있어야 한다.
        "calibrated": False,
        "net_charge": net_charge(sequence),
        "max_hydrophobic_patch": max_hydrophobic_patch(sequence),
        "aggregation_prone_fraction": aggregation_prone_fraction(sequence),
        "motifs": motif_counts(sequence),
    }


def liability_gate_report(sequence: str) -> dict:
    """지표 + (임시) 게이트 판정. 임계값과 근거 상태가 함께 기록된다."""
    report = liability_report(sequence)
    thresholds = gate_thresholds()
    enabled = gate_enabled()
    reasons: list[str] = []

    patch = report["max_hydrophobic_patch"]
    fraction = report["aggregation_prone_fraction"]
    motifs = report["motifs"]

    if isinstance(patch, (int, float)) and patch > thresholds["max_hydrophobic_patch"]:
        reasons.append(
            f"aggregation: max_hydrophobic_patch {patch} > {thresholds['max_hydrophobic_patch']}"
        )
    if fraction > thresholds["max_aggregation_prone_fraction"]:
        reasons.append(
            f"aggregation: aggregation_prone_fraction {fraction} > "
            f"{thresholds['max_aggregation_prone_fraction']}"
        )
    if motifs["free_cysteine"] > thresholds["max_free_cysteine"]:
        reasons.append(
            f"developability: free_cysteine {motifs['free_cysteine']} > "
            f"{thresholds['max_free_cysteine']}"
        )
    ng_dg = motifs["deamidation_NG"] + motifs["isomerisation_DG"]
    if ng_dg > thresholds["max_ng_dg_motifs"]:
        reasons.append(
            f"developability: deamidation_NG+isomerisation_DG {ng_dg} > "
            f"{thresholds['max_ng_dg_motifs']}"
        )

    report.update(
        {
            "metric_id": METRIC_ID,
            "gate": {
                "gate_id": GATE_ID,
                "enabled": enabled,
                "passed": (not reasons) if enabled else None,
                "reasons": reasons,
                "thresholds": thresholds,
                # 임계값이 측정에 맞춰진 적 없다는 표시. 코호트 보정 후에 true 로 바꾼다.
                "calibrated": False,
                "threshold_basis": (
                    "창 통계 임계값(폭 5, 소수성 2.0, 전하 1.0)은 항체 문맥에서 상속. "
                    "게이트 상한은 측정 코호트 없이 정한 임시값이다."
                ),
            },
        }
    )
    return report


def summarize_gate(reports: list[dict]) -> dict:
    """여러 서열의 게이트 리포트를 티어 요약으로 묶는다.

    failed_by_objective 는 이유 수가 아니라 그 목표로 탈락한 설계 수다 -
    한 설계가 같은 목표로 두 이유를 받아도 한 번 센다.
    """
    evaluated = [r for r in reports if isinstance(r, dict) and "gate" in r]
    failed = [
        r for r in evaluated
        if r.get("gate", {}).get("enabled") and r.get("gate", {}).get("passed") is False
    ]
    by_objective: dict[str, int] = {"aggregation": 0, "developability": 0}
    for report in failed:
        objectives = set()
        for reason in report.get("gate", {}).get("reasons") or []:
            if reason.startswith("aggregation:"):
                objectives.add("aggregation")
            elif reason.startswith("developability:"):
                objectives.add("developability")
        for key in objectives:
            by_objective[key] += 1
    return {
        "gate_id": GATE_ID,
        "evaluated": len(evaluated),
        "failed": len(failed),
        "failed_by_objective": by_objective,
        "enabled": bool(evaluated and evaluated[0].get("gate", {}).get("enabled")),
        "calibrated": False,
    }
