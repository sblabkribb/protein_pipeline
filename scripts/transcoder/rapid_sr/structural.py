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
        out.append(CaRecord(len(out), line[21], resnum, line[26].strip(), xyz))
    return out


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


def positional_non_loop_rmsd(reference_pdb: str, model_pdb: str, non_loop) -> float | None:
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
    if len(reference) != len(model):
        raise ValueError(
            f"순서로 짝지으려면 잔기 수가 같아야 한다: 기준 {len(reference)}, 모델 {len(model)}"
        )
    keep = non_loop_indices(reference_pdb, non_loop)
    if len(keep) < MIN_MASKED_POSITIONS:
        return None

    a = np.array([reference[i].xyz for i in keep], dtype=float)
    b = np.array([model[i].xyz for i in keep], dtype=float)
    a -= a.mean(axis=0)
    b -= b.mean(axis=0)
    u, _s, vt = np.linalg.svd(a.T @ b)
    # 반사는 제외한다. 거울상은 같은 구조가 아니다.
    d = np.sign(np.linalg.det(u @ vt))
    rot = u @ np.diag([1.0, 1.0, d]) @ vt
    aligned = a @ rot
    return float(np.sqrt(((aligned - b) ** 2).sum(axis=1).mean()))
