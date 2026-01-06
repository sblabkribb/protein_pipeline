from __future__ import annotations

from dataclasses import dataclass
import re


_HEADER_ID_RE = re.compile(r"^(\S+)")


@dataclass(frozen=True)
class FastaRecord:
    header: str
    sequence: str

    @property
    def id(self) -> str:
        m = _HEADER_ID_RE.match(self.header.strip())
        return (m.group(1) if m else self.header.strip()) or "seq"


def parse_fasta(text: str) -> list[FastaRecord]:
    records: list[FastaRecord] = []
    header: str | None = None
    seq_parts: list[str] = []

    def flush() -> None:
        nonlocal header, seq_parts
        if header is None:
            return
        seq = "".join(seq_parts).replace(" ", "").replace("\t", "").strip()
        if not seq:
            raise ValueError(f"Empty FASTA sequence for header: {header!r}")
        records.append(FastaRecord(header=header, sequence=seq))
        header = None
        seq_parts = []

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith(">"):
            flush()
            header = line[1:].strip()
            continue
        if header is None:
            raise ValueError("Invalid FASTA: sequence line before header")
        seq_parts.append(line)
    flush()

    if not records:
        raise ValueError("No FASTA records found")
    return records


def to_fasta(records: list[FastaRecord]) -> str:
    lines: list[str] = []
    for rec in records:
        header = rec.header.replace("\n", " ").strip()
        seq = rec.sequence.replace("\n", "").strip()
        lines.append(f">{header}")
        lines.append(seq)
    return "\n".join(lines) + "\n"

