"""Resolve a structure input that may be a PDB ID or URL into raw PDB text.

Lets MCP/API callers pass a 4-character PDB ID (e.g. ``4KL5``) or a structure
URL instead of the full PDB text, so large structures don't have to be sent
over the wire. Raw PDB text is passed through unchanged.

Security: a bare 4-char ID is fetched only from RCSB (fixed host). A URL is
fetched only when its host is on a small allowlist (RCSB/wwPDB/AlphaFold), to
avoid SSRF against internal services.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

import requests


_PDB_ID_RE = re.compile(r"^[0-9][A-Za-z0-9]{3}$")
_RCSB_DOWNLOAD = "https://files.rcsb.org/download/{}.pdb"
_ALLOWED_HOSTS = frozenset(
    {"files.rcsb.org", "files.wwpdb.org", "alphafold.ebi.ac.uk"}
)
# A real structure file is multi-line and long; anything short and single-line
# is treated as an identifier/URL, never as raw content.
_RAW_CONTENT_MIN_LEN = 64


def looks_like_pdb_id(value: str) -> bool:
    return bool(_PDB_ID_RE.match(str(value or "").strip()))


def _is_raw_structure(text: str) -> bool:
    if "\n" in text or "\r" in text:
        return True
    if len(text) >= _RAW_CONTENT_MIN_LEN:
        return True
    upper = text.lstrip()[:6].upper()
    return upper.startswith(("ATOM", "HETATM", "HEADER", "MODEL", "CRYST"))


def _fetch(url: str, timeout_s: float) -> str:
    resp = requests.get(url, timeout=timeout_s)
    resp.raise_for_status()
    body = resp.text or ""
    if not body.strip():
        raise ValueError(f"fetched structure is empty: {url}")
    return body


def resolve_structure_input(
    value: object,
    *,
    timeout_s: float = 30.0,
    allowed_hosts: frozenset[str] = _ALLOWED_HOSTS,
) -> object:
    """Return raw PDB text. Pass through raw content; fetch a PDB ID from RCSB
    or an allowlisted URL. Non-id, non-url short strings are returned as-is."""
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text or _is_raw_structure(text):
        return value
    if looks_like_pdb_id(text):
        return _fetch(_RCSB_DOWNLOAD.format(text.upper()), timeout_s)
    low = text.lower()
    if low.startswith(("http://", "https://")):
        host = (urlparse(text).hostname or "").lower()
        if host in allowed_hosts:
            return _fetch(text, timeout_s)
        raise ValueError(
            f"structure URL host not allowed: {host!r} "
            f"(allowed: {', '.join(sorted(allowed_hosts))})"
        )
    return value
