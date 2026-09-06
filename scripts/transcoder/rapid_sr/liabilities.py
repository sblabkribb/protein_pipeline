"""서열에서 직접 읽는 응집·개발가능성 지표.

antigen 파이프라인의 antibody_developability.py 에서 옮겨 왔다. 계산은 같고,
옮기면서 두 가지를 분명히 한다.

**이것은 휴리스틱이다.** Kyte-Doolittle 소수성과 전하로 만든 창 통계일 뿐,
어떤 응집 측정에도 맞춰본 적이 없다. 임계값은 항체 문맥에서 정해졌다 - 5 잔기
창은 노출된 기름진 구간이 문제가 되기 시작하는 폭이고, 전하 2 는 pI 와 비특이
결합에 나타나기 시작하는 이동폭이다. 단량체 재설계에 그대로 옮기면 그 근거가
따라오지 않는다.

**그래서 값은 내되 통과/탈락을 정하지 않는다.** `calibrated: False` 이고
`passed` 같은 열쇠는 없다. 게이트로 쓰려면 먼저 무엇에 맞출지를 정해야 한다.
지금 임계값을 붙이면, 맞춰본 적 없는 기준으로 설계를 버리게 된다.
"""

from __future__ import annotations

#: Kyte-Doolittle 소수성 척도.
_KYTE_DOOLITTLE = {
    "A": 1.8, "R": -4.5, "N": -3.5, "D": -3.5, "C": 2.5,
    "Q": -3.5, "E": -3.5, "G": -0.4, "H": -3.2, "I": 4.5,
    "L": 3.8, "K": -3.9, "M": 1.9, "F": 2.8, "P": -1.6,
    "S": -0.8, "T": -0.7, "W": -0.9, "Y": -1.3, "V": 4.2,
}

#: 노출된 기름진 구간이 문제가 되기 시작하는 폭. 한 번의 치환이 값을 움직일
#: 만큼 짧기도 하다.
PATCH_WINDOW = 5
#: 창이 응집 위험으로 세지려면 강하게 소수성이면서 전하가 거의 없어야 한다.
#: 전하가 기름진 구간을 녹여 두는 것이 모든 전하/소수성 용해도 휴리스틱의 근거다.
AGGREGATION_HYDROPATHY = 2.0
AGGREGATION_CHARGE = 1.0

LIABILITY_METRIC = {
    "metric_id": "sequence_liabilities_v1",
    "ported_from": "antigen_pipeline antibody_developability.py",
    "kind": "heuristic",
    "inherited_thresholds": {
        "patch_window": PATCH_WINDOW,
        "aggregation_hydropathy": AGGREGATION_HYDROPATHY,
        "aggregation_charge": AGGREGATION_CHARGE,
    },
    "scope_note": (
        "임계값은 항체 문맥에서 정해졌다. 단량체 재설계에 그대로 옮기면 그 근거가 "
        "따라오지 않으므로, 값은 기록하되 통과/탈락 판정에는 쓰지 않는다."
    ),
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
        "metric_id": LIABILITY_METRIC["metric_id"],
        "kind": LIABILITY_METRIC["kind"],
        # 맞춰본 적이 없다는 사실이 값 옆에 늘 붙어 있어야 한다.
        "calibrated": False,
        "scope_note": LIABILITY_METRIC["scope_note"],
        "net_charge": net_charge(sequence),
        "max_hydrophobic_patch": max_hydrophobic_patch(sequence),
        "aggregation_prone_fraction": aggregation_prone_fraction(sequence),
        "motifs": motif_counts(sequence),
    }
