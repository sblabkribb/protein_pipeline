from __future__ import annotations

from dataclasses import dataclass
import math


_WATER_RESNAMES = {"HOH", "WAT", "H2O"}


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


def _is_heavy(atom: Atom) -> bool:
    return atom.element not in {"H", "D"}


def ligand_proximity_mask(
    pdb_text: str,
    *,
    chains: list[str] | None = None,
    distance_angstrom: float = 6.0,
    ligand_resnames: list[str] | None = None,
) -> dict[str, list[int]]:
    ligand_set = {name.strip().upper() for name in ligand_resnames or [] if name.strip()} or None

    ligand_atoms: list[Atom] = []
    for atom in iter_atoms(pdb_text):
        if atom.record != "HETATM":
            continue
        if atom.resname.upper() in _WATER_RESNAMES:
            continue
        if ligand_set is not None and atom.resname.upper() not in ligand_set:
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

