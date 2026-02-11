from __future__ import annotations

import re

from .models import PipelineRequest


_STOP_WORDS = ("까지만", "stop", "중단", "까지만 실행")
_CONTIG_RE = re.compile(r"(?:rfd3_)?contig\s*[:=]?\s*([A-Za-z]\s*:?[0-9]+\s*-\s*[0-9]+)")


def route_prompt(prompt: str) -> dict[str, object]:
    p = (prompt or "").strip().lower()
    stop_after: str | None = None
    if any(w in p for w in _STOP_WORDS):
        if "msa" in p or "mmseqs" in p:
            stop_after = "msa"
        elif "design" in p or "proteinmpnn" in p:
            stop_after = "design"
        elif "soluprot" in p:
            stop_after = "soluprot"
        elif "af2" in p or "alphafold" in p:
            stop_after = "af2"
        elif "novel" in p or "search" in p or "검색" in p:
            stop_after = "novelty"

    tiers = None
    if "30" in p and "50" in p and "70" in p:
        tiers = [0.3, 0.5, 0.7]

    num = None
    m = re.search(r"(\d+)\s*(개|seq|sequences?)", p)
    if m:
        try:
            num = int(m.group(1))
        except Exception:
            num = None

    partial_t = None
    m = re.search(r"(?:diffuser\.partial[_\s-]*t|partial[_\s-]*t)\s*[:=]?\s*(\d+)", p)
    if m:
        try:
            partial_t = int(m.group(1))
        except Exception:
            partial_t = None

    out: dict[str, object] = {}
    if partial_t is not None:
        out["rfd3_partial_t"] = partial_t
    if stop_after:
        out["stop_after"] = stop_after
    if tiers:
        out["conservation_tiers"] = tiers
    if num is not None:
        out["num_seq_per_tier"] = num
    return out


def request_from_prompt(*, prompt: str, target_fasta: str, target_pdb: str) -> PipelineRequest:
    routed = route_prompt(prompt)
    kwargs = dict(routed)
    return PipelineRequest(target_fasta=target_fasta or "", target_pdb=target_pdb or "", **kwargs)  # type: ignore[arg-type]


def _normalize_contig(raw: str) -> str:
    value = re.sub(r"\s+", "", raw or "")
    return value.replace(":", "")


def plan_from_prompt(
    *,
    prompt: str,
    target_fasta: str | None = None,
    target_pdb: str | None = None,
    rfd3_input_pdb: str | None = None,
    rfd3_contig: str | None = None,
    diffdock_ligand_smiles: str | None = None,
    diffdock_ligand_sdf: str | None = None,
) -> dict[str, object]:
    raw_prompt = str(prompt or "")
    p = raw_prompt.strip().lower()
    routed = dict(route_prompt(raw_prompt))

    if rfd3_contig and not routed.get("rfd3_contig"):
        routed["rfd3_contig"] = _normalize_contig(rfd3_contig)

    if "rfd3_contig" not in routed:
        m = _CONTIG_RE.search(raw_prompt)
        if m:
            routed["rfd3_contig"] = _normalize_contig(m.group(1))

    wants_rfd3 = bool(re.search(r"rfd3|rfdiff|diffusion", p))
    wants_diffdock = bool(re.search(r"diffdock|ligand|substrate", p))

    has_target = bool(str(target_fasta or "").strip() or str(target_pdb or "").strip())
    has_rfd3_pdb = bool(str(rfd3_input_pdb or "").strip())
    has_rfd3_contig = bool(str(routed.get("rfd3_contig") or "").strip())
    has_diffdock_ligand = bool(str(diffdock_ligand_smiles or "").strip() or str(diffdock_ligand_sdf or "").strip())

    missing: list[str] = []
    questions: list[dict[str, object]] = []

    if not has_target and not has_rfd3_pdb:
        missing.append("target_input")
        questions.append(
            {
                "id": "target_input",
                "question": "Provide target_pdb or target_fasta (raw text).",
                "required": True,
            }
        )

    if wants_rfd3:
        if not has_rfd3_pdb:
            missing.append("rfd3_input_pdb")
            questions.append(
                {
                    "id": "rfd3_input_pdb",
                    "question": "Provide rfd3_input_pdb text (raw PDB).",
                    "required": True,
                }
            )
        if not has_rfd3_contig:
            missing.append("rfd3_contig")
            questions.append(
                {
                    "id": "rfd3_contig",
                    "question": "Provide rfd3_contig (format: A1-221, no colon).",
                    "required": True,
                }
            )

    if wants_diffdock and not has_diffdock_ligand:
        missing.append("diffdock_ligand")
        questions.append(
            {
                "id": "diffdock_ligand",
                "question": "Provide diffdock_ligand_smiles or diffdock_ligand_sdf if ligand coords are missing.",
                "required": False,
            }
        )

    if "stop_after" not in routed:
        questions.append(
            {
                "id": "stop_after",
                "question": "Where to stop? (msa/design/soluprot/af2/novelty)",
                "required": False,
                "default": "design",
            }
        )

    if "design" in p and "design_chains" not in routed and has_target:
        questions.append(
            {
                "id": "design_chains",
                "question": "Which chains to design? (default: all)",
                "required": False,
            }
        )

    return {
        "routed_request": routed,
        "missing": missing,
        "questions": questions,
    }
