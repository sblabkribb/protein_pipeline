from __future__ import annotations

from dataclasses import dataclass
import math


_WATER_RESNAMES = {"HOH", "WAT", "H2O"}
_AA3_TO_AA1: dict[str, str] = {
    "ALA": "A",
    "ARG": "R",
    "ASN": "N",
    "ASP": "D",
    "CYS": "C",
    "GLN": "Q",
    "GLU": "E",
    "GLY": "G",
    "HIS": "H",
    "ILE": "I",
    "LEU": "L",
    "LYS": "K",
    "MET": "M",
    "PHE": "F",
    "PRO": "P",
    "SER": "S",
    "THR": "T",
    "TRP": "W",
    "TYR": "Y",
    "VAL": "V",
    # Common variants / modified residues
    "MSE": "M",  # selenomethionine
    "SEC": "U",  # selenocysteine
    "PYL": "O",  # pyrrolysine
    "HSD": "H",
    "HSE": "H",
    "HSP": "H",
    "CYX": "C",
    "ASX": "B",
    "GLX": "Z",
    "UNK": "X",
}


@dataclass(frozen=True)
class Atom:
    record: str  # ATOM or HETATM
    atom_name: str
    resname: str
    chain_id: str
    resseq: int
    icode: str
    x: float
    y: float
    z: float
    element: str


@dataclass(frozen=True)
class Residue:
    chain_id: str
    index: int  # 1-based within chain
    resname: str
    resseq: int
    icode: str
    atoms: tuple[Atom, ...]


def _parse_int(value: str, default: int = 0) -> int:
    try:
        return int(value.strip())
    except Exception:
        return default


def _parse_float(value: str, default: float = 0.0) -> float:
    try:
        return float(value.strip())
    except Exception:
        return default


def iter_atoms(pdb_text: str):
    for raw in pdb_text.splitlines():
        if not raw:
            continue
        rec = raw[:6].strip().upper()
        if rec not in {"ATOM", "HETATM"}:
            continue
        atom_name = raw[12:16].strip()
        resname = raw[17:20].strip()
        chain_id = raw[21:22].strip() or "_"
        resseq = _parse_int(raw[22:26])
        icode = raw[26:27].strip()
        x = _parse_float(raw[30:38])
        y = _parse_float(raw[38:46])
        z = _parse_float(raw[46:54])
        element = raw[76:78].strip() or (atom_name[:1].strip().upper() if atom_name else "")
        yield Atom(
            record=rec,
            atom_name=atom_name,
            resname=resname,
            chain_id=chain_id,
            resseq=resseq,
            icode=icode,
            x=x,
            y=y,
            z=z,
            element=element.upper(),
        )


def residues_by_chain(pdb_text: str, *, only_atom_records: bool = True) -> dict[str, list[Residue]]:
    residues: dict[str, list[Residue]] = {}
    current_key: tuple[str, int, str] | None = None
    current_atoms: list[Atom] = []
    current_resname = ""
    current_chain = ""
    current_resseq = 0
    current_icode = ""
    chain_indices: dict[str, int] = {}

    def flush() -> None:
        nonlocal current_key, current_atoms, current_resname, current_chain, current_resseq, current_icode
        if current_key is None:
            return
        chain = current_chain
        chain_indices[chain] = chain_indices.get(chain, 0) + 1
        idx = chain_indices[chain]
        residues.setdefault(chain, []).append(
            Residue(
                chain_id=chain,
                index=idx,
                resname=current_resname,
                resseq=current_resseq,
                icode=current_icode,
                atoms=tuple(current_atoms),
            )
        )
        current_key = None
        current_atoms = []
        current_resname = ""
        current_chain = ""
        current_resseq = 0
        current_icode = ""

    for atom in iter_atoms(pdb_text):
        if only_atom_records and atom.record != "ATOM":
            continue
        key = (atom.chain_id, atom.resseq, atom.icode)
        if current_key is None:
            current_key = key
            current_chain = atom.chain_id
            current_resseq = atom.resseq
            current_icode = atom.icode
            current_resname = atom.resname
            current_atoms = [atom]
            continue
        if key != current_key:
            flush()
            current_key = key
            current_chain = atom.chain_id
            current_resseq = atom.resseq
            current_icode = atom.icode
            current_resname = atom.resname
            current_atoms = [atom]
            continue
        current_atoms.append(atom)
    flush()
    return residues


def sequence_by_chain(
    pdb_text: str,
    *,
    chains: list[str] | None = None,
    unknown: str = "X",
) -> dict[str, str]:
    residues = residues_by_chain(pdb_text, only_atom_records=True)
    chain_set = set(chains) if chains is not None else None

    out: dict[str, str] = {}
    for chain_id, res_list in residues.items():
        if chain_set is not None and chain_id not in chain_set:
            continue
        seq = "".join(_AA3_TO_AA1.get(res.resname.upper(), unknown) for res in res_list)
        if seq:
            out[chain_id] = seq
    return out


def _is_heavy(atom: Atom) -> bool:
    return atom.element not in {"H", "D"}


def ligand_atoms_present(
    pdb_text: str,
    *,
    chains: list[str] | None = None,
    ligand_resnames: list[str] | None = None,
    ligand_atom_chains: list[str] | None = None,
) -> bool:
    ligand_set = {name.strip().upper() for name in ligand_resnames or [] if name.strip()} or None
    atom_chain_set = {c.strip() for c in (ligand_atom_chains or []) if str(c).strip()} or None
    masked_chain_set = set(chains) if chains is not None else set()

    for atom in iter_atoms(pdb_text):
        if atom.record == "HETATM":
            if atom.resname.upper() in _WATER_RESNAMES:
                continue
            if ligand_set is not None and atom.resname.upper() not in ligand_set:
                continue
            if _is_heavy(atom):
                return True
            continue

        if atom.record == "ATOM" and atom_chain_set is not None:
            if atom.chain_id not in atom_chain_set:
                continue
            if atom.chain_id in masked_chain_set:
                continue
            if _is_heavy(atom):
                return True
    return False


def ligand_proximity_mask(
    pdb_text: str,
    *,
    chains: list[str] | None = None,
    distance_angstrom: float = 6.0,
    ligand_resnames: list[str] | None = None,
    ligand_atom_chains: list[str] | None = None,
) -> dict[str, list[int]]:
    ligand_set = {name.strip().upper() for name in ligand_resnames or [] if name.strip()} or None
    atom_chain_set = {c.strip() for c in (ligand_atom_chains or []) if str(c).strip()} or None
    masked_chain_set = set(chains) if chains is not None else set()

    ligand_atoms: list[Atom] = []
    for atom in iter_atoms(pdb_text):
        if atom.record == "HETATM":
            if atom.resname.upper() in _WATER_RESNAMES:
                continue
            if ligand_set is not None and atom.resname.upper() not in ligand_set:
                continue
            if _is_heavy(atom):
                ligand_atoms.append(atom)
            continue

        if atom.record == "ATOM" and atom_chain_set is not None:
            if atom.chain_id not in atom_chain_set:
                continue
            if atom.chain_id in masked_chain_set:
                continue
            if _is_heavy(atom):
                ligand_atoms.append(atom)

    if not ligand_atoms:
        return {chain: [] for chain in (chains or [])} if chains else {}

    dist2 = float(distance_angstrom) ** 2
    residues = residues_by_chain(pdb_text, only_atom_records=True)

    mask: dict[str, list[int]] = {}
    for chain_id, res_list in residues.items():
        if chains is not None and chain_id not in set(chains):
            continue
        hits: list[int] = []
        for res in res_list:
            close = False
            for at in res.atoms:
                if not _is_heavy(at):
                    continue
                for lig in ligand_atoms:
                    dx = at.x - lig.x
                    dy = at.y - lig.y
                    dz = at.z - lig.z
                    if (dx * dx + dy * dy + dz * dz) <= dist2:
                        close = True
                        break
                if close:
                    break
            if close:
                hits.append(res.index)
        if hits:
            mask[chain_id] = hits
    return mask


def _rewrite_pdb_resseq_icode(raw: str, *, resseq: int, icode: str) -> str:
    line = raw.rstrip("\n")
    if len(line) < 27:
        line = line.ljust(27)
    res_field = f"{int(resseq):4d}"
    icode_field = (str(icode or " ")[:1] or " ")
    return f"{line[:22]}{res_field}{icode_field}{line[27:]}"


def preprocess_pdb(
    pdb_text: str,
    *,
    chains: list[str] | None = None,
    strip_nonpositive_resseq: bool = False,
    renumber_resseq_from_1: bool = False,
) -> tuple[str, dict[str, list[dict[str, object]]]]:
    chain_set = set(chains) if chains is not None else None

    renumber_map: dict[str, dict[tuple[int, str], int]] = {}
    next_renum: dict[str, int] = {}
    residue_index: dict[str, int] = {}
    last_resseq: dict[str, int] = {}

    mapping: dict[str, list[dict[str, object]]] = {}
    seen_residue: set[tuple[str, int, str]] = set()

    out_lines: list[str] = []

    for raw in pdb_text.splitlines():
        rec = raw[:6].strip().upper()
        if rec not in {"ATOM", "HETATM", "TER"}:
            out_lines.append(raw)
            continue

        chain_id = raw[21:22].strip() or "_"
        if chain_set is not None and chain_id not in chain_set:
            out_lines.append(raw)
            continue

        resseq = _parse_int(raw[22:26])
        icode = raw[26:27].strip()

        if strip_nonpositive_resseq and rec in {"ATOM", "HETATM"} and int(resseq) <= 0:
            continue

        if rec == "TER":
            if renumber_resseq_from_1 and chain_id in last_resseq:
                out_lines.append(_rewrite_pdb_resseq_icode(raw, resseq=last_resseq[chain_id], icode=" "))
            else:
                out_lines.append(raw)
            continue

        key = (int(resseq), str(icode))
        new_resseq = int(resseq)
        new_icode = str(icode)
        if renumber_resseq_from_1:
            per_chain = renumber_map.setdefault(chain_id, {})
            if key not in per_chain:
                per_chain[key] = int(next_renum.get(chain_id, 1))
                next_renum[chain_id] = per_chain[key] + 1
            new_resseq = per_chain[key]
            new_icode = " "

        residue_key = (chain_id, int(resseq), str(icode))
        if residue_key not in seen_residue:
            seen_residue.add(residue_key)
            idx = int(residue_index.get(chain_id, 0)) + 1
            residue_index[chain_id] = idx
            mapping.setdefault(chain_id, []).append(
                {
                    "index": idx,
                    "original_resseq": int(resseq),
                    "original_icode": str(icode or ""),
                    "processed_resseq": int(new_resseq),
                    "processed_icode": str(new_icode or "").strip(),
                }
            )

        last_resseq[chain_id] = int(new_resseq)
        if renumber_resseq_from_1:
            out_lines.append(_rewrite_pdb_resseq_icode(raw, resseq=new_resseq, icode=new_icode))
        else:
            out_lines.append(raw)

    return ("\n".join(out_lines) + ("\n" if pdb_text.endswith("\n") else "")), mapping


def _ca_coords_by_chain(pdb_text: str, *, chains: list[str] | None = None) -> dict[str, dict[int, tuple[float, float, float]]]:
    residues = residues_by_chain(pdb_text, only_atom_records=True)
    chain_set = set(chains) if chains is not None else None
    out: dict[str, dict[int, tuple[float, float, float]]] = {}
    for chain_id, res_list in residues.items():
        if chain_set is not None and chain_id not in chain_set:
            continue
        coords: dict[int, tuple[float, float, float]] = {}
        for res in res_list:
            ca = None
            for atom in res.atoms:
                if atom.atom_name.strip().upper() == "CA":
                    ca = (atom.x, atom.y, atom.z)
                    break
            if ca is not None:
                coords[res.index] = ca
        if coords:
            out[chain_id] = coords
    return out


def _match_ca_coords(
    ref_coords: dict[str, dict[int, tuple[float, float, float]]],
    mob_coords: dict[str, dict[int, tuple[float, float, float]]],
    *,
    chains: list[str] | None = None,
) -> tuple[list[tuple[float, float, float]], list[tuple[float, float, float]]]:
    chain_order = chains or sorted(set(ref_coords) & set(mob_coords))
    ref: list[tuple[float, float, float]] = []
    mob: list[tuple[float, float, float]] = []
    for chain_id in chain_order:
        ref_chain = ref_coords.get(chain_id) or {}
        mob_chain = mob_coords.get(chain_id) or {}
        if not ref_chain or not mob_chain:
            continue
        for idx in sorted(set(ref_chain) & set(mob_chain)):
            ref.append(ref_chain[idx])
            mob.append(mob_chain[idx])
    return ref, mob


def _centroid(coords: list[tuple[float, float, float]]) -> tuple[float, float, float]:
    if not coords:
        return (0.0, 0.0, 0.0)
    inv = 1.0 / float(len(coords))
    sx = sum(p[0] for p in coords)
    sy = sum(p[1] for p in coords)
    sz = sum(p[2] for p in coords)
    return (sx * inv, sy * inv, sz * inv)


def _center_coords(
    coords: list[tuple[float, float, float]],
    center: tuple[float, float, float],
) -> list[tuple[float, float, float]]:
    cx, cy, cz = center
    return [(x - cx, y - cy, z - cz) for (x, y, z) in coords]


def _covariance_matrix(
    mob: list[tuple[float, float, float]],
    ref: list[tuple[float, float, float]],
) -> list[list[float]]:
    sxx = syy = szz = sxy = sxz = syx = syz = szx = szy = 0.0
    for (mx, my, mz), (rx, ry, rz) in zip(mob, ref):
        sxx += mx * rx
        sxy += mx * ry
        sxz += mx * rz
        syx += my * rx
        syy += my * ry
        syz += my * rz
        szx += mz * rx
        szy += mz * ry
        szz += mz * rz
    return [
        [sxx, sxy, sxz],
        [syx, syy, syz],
        [szx, szy, szz],
    ]


def _quat_from_covariance(cov: list[list[float]]) -> tuple[float, float, float, float] | None:
    sxx, sxy, sxz = cov[0]
    syx, syy, syz = cov[1]
    szx, szy, szz = cov[2]
    n = [
        [sxx + syy + szz, syz - szy, szx - sxz, sxy - syx],
        [syz - szy, sxx - syy - szz, sxy + syx, szx + sxz],
        [szx - sxz, sxy + syx, -sxx + syy - szz, syz + szy],
        [sxy - syx, szx + sxz, syz + szy, -sxx - syy + szz],
    ]
    v = [1.0, 0.0, 0.0, 0.0]
    for _ in range(32):
        w0 = n[0][0] * v[0] + n[0][1] * v[1] + n[0][2] * v[2] + n[0][3] * v[3]
        w1 = n[1][0] * v[0] + n[1][1] * v[1] + n[1][2] * v[2] + n[1][3] * v[3]
        w2 = n[2][0] * v[0] + n[2][1] * v[1] + n[2][2] * v[2] + n[2][3] * v[3]
        w3 = n[3][0] * v[0] + n[3][1] * v[1] + n[3][2] * v[2] + n[3][3] * v[3]
        norm = math.sqrt(w0 * w0 + w1 * w1 + w2 * w2 + w3 * w3)
        if norm <= 0.0:
            return None
        v = [w0 / norm, w1 / norm, w2 / norm, w3 / norm]
    return (v[0], v[1], v[2], v[3])


def _rotation_from_quat(q: tuple[float, float, float, float]) -> list[list[float]]:
    w, x, y, z = q
    ww = w * w
    xx = x * x
    yy = y * y
    zz = z * z
    wx = w * x
    wy = w * y
    wz = w * z
    xy = x * y
    xz = x * z
    yz = y * z
    return [
        [ww + xx - yy - zz, 2.0 * (xy - wz), 2.0 * (xz + wy)],
        [2.0 * (xy + wz), ww - xx + yy - zz, 2.0 * (yz - wx)],
        [2.0 * (xz - wy), 2.0 * (yz + wx), ww - xx - yy + zz],
    ]


def _apply_rotation(
    vec: tuple[float, float, float],
    rot: list[list[float]],
) -> tuple[float, float, float]:
    x, y, z = vec
    return (
        rot[0][0] * x + rot[0][1] * y + rot[0][2] * z,
        rot[1][0] * x + rot[1][1] * y + rot[1][2] * z,
        rot[2][0] * x + rot[2][1] * y + rot[2][2] * z,
    )


def ca_rmsd(
    pdb_ref: str,
    pdb_mobile: str,
    *,
    chains: list[str] | None = None,
) -> float | None:
    ref_coords = _ca_coords_by_chain(pdb_ref, chains=chains)
    mob_coords = _ca_coords_by_chain(pdb_mobile, chains=chains)
    ref, mob = _match_ca_coords(ref_coords, mob_coords, chains=chains)
    if len(ref) < 3 or len(mob) < 3:
        return None
    ref_center = _centroid(ref)
    mob_center = _centroid(mob)
    ref_c = _center_coords(ref, ref_center)
    mob_c = _center_coords(mob, mob_center)
    cov = _covariance_matrix(mob_c, ref_c)
    quat = _quat_from_covariance(cov)
    if quat is None:
        return None
    rot = _rotation_from_quat(quat)
    total = 0.0
    for r, m in zip(ref_c, mob_c):
        mx, my, mz = _apply_rotation(m, rot)
        dx = r[0] - mx
        dy = r[1] - my
        dz = r[2] - mz
        total += dx * dx + dy * dy + dz * dz
    return math.sqrt(total / float(len(ref_c)))
