from __future__ import annotations


_MISSING_PDB_OUTPUTS_TOKEN = "no pdb outputs were found"


def af2_error_is_missing_pdb_outputs(value: object) -> bool:
    if not isinstance(value, str):
        return False
    return _MISSING_PDB_OUTPUTS_TOKEN in value.strip().lower()


def af2_payload_has_missing_pdb_failure(payload: object) -> bool:
    if not isinstance(payload, dict):
        return False
    return af2_error_is_missing_pdb_outputs(payload.get("error"))
