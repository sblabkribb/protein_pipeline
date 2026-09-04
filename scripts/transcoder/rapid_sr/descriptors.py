"""백본 구조 기술자 (게이트 0 사다리의 baseline B).

CA 좌표만으로 계산한다. DSSP 같은 외부 의존성을 두지 않는다.
"""

from __future__ import annotations

import numpy as np


def ca_coords(pdb_text: str) -> np.ndarray:
    """첫 MODEL 의 CA 좌표. 중복 잔기 키는 한 번만 센다."""
    seen: set[str] = set()
    rows: list[list[float]] = []
    for line in pdb_text.splitlines():
        if line.startswith("ENDMDL"):
            break
        if not line.startswith("ATOM") or line[12:16].strip() != "CA":
            continue
        key = line[21:27]
        if key in seen:
            continue
        seen.add(key)
        try:
            rows.append([float(line[30:38]), float(line[38:46]), float(line[46:54])])
        except ValueError:
            continue
    return np.asarray(rows, dtype=float)


def descriptors(coords: np.ndarray, *, contact_cutoff: float = 8.0) -> dict[str, float]:
    """길이·조밀도·접촉 구조를 요약한다.

    좌표가 3개 미만이면 계산이 무의미하므로 0 으로 채운 값을 돌려준다.
    """
    keys = (
        "n_residues", "radius_of_gyration", "rg_over_sqrt_n", "end_to_end",
        "end_to_end_over_rg", "contact_density", "mean_contact_order",
        "frac_high_contact", "asphericity", "mean_ca_ca_step",
    )
    if coords.shape[0] < 3:
        return {k: 0.0 for k in keys}

    n = coords.shape[0]
    centre = coords.mean(axis=0)
    centred = coords - centre
    rg = float(np.sqrt((centred ** 2).sum(axis=1).mean()))
    end_to_end = float(np.linalg.norm(coords[-1] - coords[0]))

    diff = coords[:, None, :] - coords[None, :, :]
    dist = np.sqrt((diff ** 2).sum(-1))
    idx = np.arange(n)
    sep = np.abs(idx[:, None] - idx[None, :])
    # 서열상 3 잔기 이내는 사슬 연결이라 접촉으로 세지 않는다.
    contact = (dist < contact_cutoff) & (sep > 3)
    n_contacts = int(contact.sum() // 2)
    contact_density = n_contacts / float(n)
    mean_contact_order = (
        float(sep[contact].mean() / n) if n_contacts else 0.0
    )
    per_residue = contact.sum(axis=1)
    frac_high_contact = float((per_residue >= 8).mean())

    # 관성 텐서 고유값으로 모양 비대칭성
    eig = np.linalg.eigvalsh(centred.T @ centred / n)
    eig = np.sort(eig)[::-1]
    asphericity = float((eig[0] - 0.5 * (eig[1] + eig[2])) / eig.sum()) if eig.sum() > 0 else 0.0

    steps = np.linalg.norm(np.diff(coords, axis=0), axis=1)
    return {
        "n_residues": float(n),
        "radius_of_gyration": rg,
        "rg_over_sqrt_n": rg / float(np.sqrt(n)),
        "end_to_end": end_to_end,
        "end_to_end_over_rg": end_to_end / rg if rg > 0 else 0.0,
        "contact_density": contact_density,
        "mean_contact_order": mean_contact_order,
        "frac_high_contact": frac_high_contact,
        "asphericity": asphericity,
        "mean_ca_ca_step": float(steps.mean()) if steps.size else 0.0,
    }


DESCRIPTOR_NAMES = tuple(descriptors(np.zeros((0, 3))).keys())
