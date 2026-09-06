"""기준 백본과 AF2 모델 사이의 구조 지표.

대응을 무엇으로 잡을 것인가
---------------------------
동결 정의(V1)는 잔기 번호로 짝지었다. 캠페인 코드가 그렇게 하기 때문이었는데,
그것이 AF2 모델에 대해 맞는 대응인지는 확인하지 않았다. 맞지 않는다.

CATH 도메인 PDB 는 원래 사슬의 번호를 그대로 갖는다. 1af7A01 은 11..284,
1bctA00 은 163..231 이다. AF2 는 접은 서열을 늘 1..N 으로 번호매긴다. 그래서
번호로 짝지으면 겹치는 구간이 통째로 밀리거나(1af7A01) 아예 비어버린다
(1bctA00 은 32 개 폴드 전부 RMSD 가 없었다). 157 개 백본 중 36 개가 1 번에서
시작하지 않는다.

같은 모델(pLDDT 92.98)에서 잰 값:

    번호 대응 + non-loop   29.58 A
    순서 대응 + 전체 CA     2.44 A

ProteinMPNN 은 백본의 잔기 순서대로 서열을 만들고 AF2 는 그 서열을 순서대로
접는다. 그러므로 대응은 **순서** 다. 번호는 기준 구조가 어디서 잘려 나왔는지를
말할 뿐 모델과는 관계가 없다.

무엇을 재는가는 그대로다: DSSP non-loop 위치에서만 CA RMSD 를 잰다. 게이트 0 의
2.0 A 임계값이 그 위에서 정해졌고, 유연한 loop 를 넣으면 임계값이 다른 것을
뜻하게 된다.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

#: 강체 정합에는 6 자유도가 들어간다. 그보다 조금이라도 많은 점이 있어야 RMSD 가
#: 구조 일치를 재기 시작한다.
MIN_MASKED_POSITIONS = 4


@dataclass(frozen=True)
class CaRecord:
    index: int
    chain: str
    resnum: int
    icode: str
    xyz: tuple[float, float, float]


def ca_records(pdb_text: str) -> list[CaRecord]:
    """CA 원자를 파일 순서 그대로 읽는다. 순서가 곧 대응이다."""
    out: list[CaRecord] = []
    # 대체 위치(altLoc)는 한 잔기가 두 벌로 기록된 것이다. 그대로 세면 잔기 수가
    # 부풀어 모델과 길이가 달라진다 - 1c8zA00 은 CA 284 개에 고유 잔기 265 개다.
    # 첫 벌만 남긴다.
    seen: set[tuple[str, int, str]] = set()
    for line in (pdb_text or "").splitlines():
        # HETATM 은 받지 않는다. "CA" 는 알파탄소이기도 하고 칼슘이기도 하며,
        # 리간드도 CA 라는 이름의 원자를 가질 수 있다 (1af7A01 의 SAH 가 그렇다).
        # 설계 서열은 폴리펩타이드에 대응하므로 ATOM 만이 대응 대상이다.
        if not line.startswith("ATOM"):
            continue
        if line[12:16].strip() != "CA":
            continue
        try:
            xyz = (float(line[30:38]), float(line[38:46]), float(line[46:54]))
            resnum = int(line[22:26])
        except ValueError:
            continue
        key = (line[21], resnum, line[26].strip())
        if key in seen:
            continue
        seen.add(key)
        out.append(CaRecord(len(out), line[21], resnum, line[26].strip(), xyz))
    return out


def sequence_indices(reference_pdb: str) -> list[int]:
    """각 기준 CA 가 **설계 서열에서** 차지하는 인덱스.

    ProteinMPNN 은 파일 순서가 아니라 잔기 번호 구간 전체에 걸쳐 서열을 만들고,
    빠진 자리를 X 로 채운다. 확인된 예: 1bxmA00 은 잔기 -1..98 에서 0 번이 없어
    서열이 100 자이고 X 가 인덱스 1 에, 2wejA00 은 3..261 에서 126 번이 없어
    259 자이고 X 가 인덱스 123 에 있다.

    그러므로 인덱스는 `잔기번호 - 최소잔기번호` 다. 이 값은 번호를 통째로 옮겨도
    변하지 않으므로, CATH 오프셋과 무관하다.
    """
    records = ca_records(reference_pdb)
    if not records:
        return []
    chains = {r.chain for r in records}
    if len(chains) > 1:
        # 여러 사슬은 ProteinMPNN 이 어떤 순서로 이어 붙였는지 알아야 한다.
        # 짐작하면 그 순간 대응이 틀린다.
        raise ValueError(f"여러 사슬({sorted(chains)})의 서열 인덱스는 짐작할 수 없다")
    base = min(r.resnum for r in records)
    return [r.resnum - base for r in records]


def designed_length(reference_pdb: str) -> int:
    """이 백본에서 나온 설계 서열의 길이. 빈 자리를 포함한 번호 구간의 폭이다."""
    indices = sequence_indices(reference_pdb)
    return (max(indices) + 1) if indices else 0


def non_loop_indices(reference_pdb: str, non_loop) -> list[int]:
    """DSSP 가 고른 위치를 기준 구조의 **파일 순서 인덱스** 로 바꾼다.

    마스크는 (사슬, 잔기번호) 로 오지만 모델과 짝지을 때 쓰는 것은 순서다.
    그래서 마스크를 한 번 인덱스로 옮겨 두고, 그 인덱스로 양쪽을 자른다.
    """
    wanted = {
        (chain, int(num), str(icode or "").strip())
        for chain, positions in (non_loop or {}).items()
        for num, icode in positions
    }
    return [
        record.index for record in ca_records(reference_pdb)
        if (record.chain, record.resnum, record.icode) in wanted
    ]


def model_positions(reference_pdb: str, model_pdb: str, *, sequence: str | None = None) -> list[int]:
    """기준의 각 CA 에 대응하는 모델 인덱스.

    두 가지 관례가 섞여 있다. ProteinMPNN 은 번호 구간 전체에 서열을 만들고 빈
    자리를 X 로 채우지만, AF2 는 그 X 를 빼고 접는다 - 1bxmA00 은 서열 100 자
    (X 1 개)인데 모델은 99 잔기로 돌아왔다.

    서열을 주면 정확히 정해진다: X 가 아닌 자리들이 순서대로 기준 잔기에
    대응하고, 모델 길이가 그 개수면 파일 순서, 서열 전체 길이면 구간 인덱스다.
    서열이 없으면 길이로 판별하고, 어느 쪽도 아니면 거부한다 - 짐작해서 맞추면
    그 뒤가 통째로 밀린 채 그럴듯한 숫자가 나온다.
    """
    records = ca_records(reference_pdb)
    model_n = len(ca_records(model_pdb))
    span = designed_length(reference_pdb)

    if sequence is not None:
        kept = sum(1 for residue in sequence if residue != "X")
        if kept != len(records):
            raise ValueError(
                f"서열의 비-X 잔기 {kept} 개가 기준 잔기 {len(records)} 개와 다르다. "
                f"이 서열은 이 백본의 것이 아니다."
            )
        if model_n == kept:
            return list(range(len(records)))
        if model_n == len(sequence):
            return sequence_indices(reference_pdb)
        raise ValueError(
            f"모델 길이 {model_n} 이 서열({len(sequence)})과도 비-X 잔기({kept})와도 다르다"
        )

    if model_n == len(records):
        return list(range(len(records)))
    if model_n == span:
        return sequence_indices(reference_pdb)
    raise ValueError(
        f"모델 길이 {model_n} 이 기준 잔기({len(records)})와도 번호 구간({span})과도 다르다"
    )


def positional_non_loop_rmsd(reference_pdb: str, model_pdb: str, non_loop,
                             *, sequence: str | None = None) -> float | None:
    """기준의 non-loop 위치에서, 순서로 짝지은 CA RMSD.

    길이가 다르면 거부한다. 앞쪽 공통 길이만 잘라 쓰면 뒤쪽이 어긋난 채로
    숫자가 나오고, 그 숫자는 조용히 틀린다.

    마스크된 점이 너무 적으면 None 이다. 강체 정합의 자유도를 재는 것과
    구조 일치를 재는 것은 다르다.
    """
    reference = ca_records(reference_pdb)
    model = ca_records(model_pdb)
    if not reference or not model:
        return None
    positions = model_positions(reference_pdb, model_pdb, sequence=sequence)
    keep_rows = non_loop_indices(reference_pdb, non_loop)
    if len(keep_rows) < MIN_MASKED_POSITIONS:
        return None

    a = np.array([reference[i].xyz for i in keep_rows], dtype=float)
    b = np.array([model[positions[i]].xyz for i in keep_rows], dtype=float)
    a -= a.mean(axis=0)
    b -= b.mean(axis=0)
    u, _s, vt = np.linalg.svd(a.T @ b)
    # 반사는 제외한다. 거울상은 같은 구조가 아니다.
    d = np.sign(np.linalg.det(u @ vt))
    rot = u @ np.diag([1.0, 1.0, d]) @ vt
    aligned = a @ rot
    return float(np.sqrt(((aligned - b) ** 2).sum(axis=1).mean()))
