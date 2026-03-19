from __future__ import annotations

from dataclasses import dataclass
import gzip
from pathlib import Path
import shlex
import subprocess
import tempfile
from typing import Any


def _is_number_token(value: object) -> bool:
    try:
        float(value)
        return True
    except Exception:
        return False


def _parse_rosetta_scorefile(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise RuntimeError(f"Rosetta scorefile missing: {path}")
    text = path.read_text(encoding="utf-8", errors="replace")
    header: list[str] | None = None
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("SCORE:"):
            continue
        parts = stripped.split()
        if len(parts) < 3:
            continue
        values = parts[1:]
        if "description" in values and not _is_number_token(values[0]):
            header = values
            continue
        if header is None or len(values) < len(header):
            continue
        row: dict[str, Any] = {}
        for key, raw in zip(header, values):
            row[key] = float(raw) if _is_number_token(raw) else raw
        rows.append(row)
    if not rows:
        raise RuntimeError(f"No Rosetta score rows found in {path}")
    return rows


def _best_score_row(rows: list[dict[str, Any]]) -> dict[str, Any]:
    best_row: dict[str, Any] | None = None
    best_score: float | None = None
    for row in rows:
        raw = row.get("total_score", row.get("score"))
        if not isinstance(raw, (int, float)):
            continue
        value = float(raw)
        if best_score is None or value < best_score:
            best_score = value
            best_row = row
    if best_row is None:
        raise RuntimeError("Rosetta scorefile did not contain a numeric total_score")
    return best_row


def _read_pdb_text(path: Path) -> str:
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            return handle.read()
    return path.read_text(encoding="utf-8")


@dataclass(frozen=True)
class RosettaRelaxClient:
    docker_image: str | None = None
    docker_bin: str | None = None
    relax_binary: str | None = None
    score_binary: str | None = None
    database_path: str | None = None
    timeout_s: float = 60.0 * 60.0
    container_workdir: str = "/work"
    container_relax_binary: str = "/usr/local/bin/relax.default.linuxgccrelease"
    container_score_binary: str = "/usr/local/bin/score_jd2.default.linuxgccrelease"
    container_database_path: str = "/usr/local/database"

    def is_configured(self) -> bool:
        if self.relax_binary and self.score_binary and self.database_path:
            return True
        return bool(self.docker_bin and self.docker_image)

    def _mode(self) -> str:
        if self.relax_binary and self.score_binary and self.database_path:
            return "binary"
        if self.docker_bin and self.docker_image:
            return "docker"
        raise RuntimeError(
            "Rosetta relax is not configured. Set ROSETTA_DOCKER_IMAGE/ROSETTA_DOCKER_BIN or "
            "ROSETTA_RELAX_BIN/ROSETTA_SCORE_BIN/ROSETTA_DATABASE."
        )

    def _runtime_path(self, path: Path, *, root: Path, mode: str) -> str:
        if mode == "docker":
            rel = path.relative_to(root).as_posix()
            return f"{self.container_workdir}/{rel}"
        return str(path)

    def _runtime_prefix(self, *, root: Path, mode: str) -> list[str]:
        if mode == "docker":
            return [
                str(self.docker_bin),
                "run",
                "--rm",
                "-v",
                f"{root}:{self.container_workdir}",
                "-w",
                self.container_workdir,
                str(self.docker_image),
            ]
        return []

    def _database_arg(self, *, mode: str) -> str:
        if mode == "docker":
            return str(self.container_database_path)
        return str(self.database_path)

    def _run(
        self,
        args: list[str],
        *,
        workdir: Path,
        mode: str,
    ) -> subprocess.CompletedProcess[str]:
        cmd = self._runtime_prefix(root=workdir, mode=mode) + list(args)
        result = subprocess.run(
            cmd,
            cwd=(str(workdir) if mode == "binary" else None),
            capture_output=True,
            text=True,
            timeout=self.timeout_s,
            check=False,
        )
        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            stdout = (result.stdout or "").strip()
            tail = stderr or stdout or f"exit code {result.returncode}"
            raise RuntimeError(f"Rosetta command failed: {tail[-2000:]}")
        return result

    def relax(
        self,
        pdb_text: str,
        *,
        nstruct: int = 1,
        extra_flags: str | None = None,
    ) -> dict[str, Any]:
        mode = self._mode()
        with tempfile.TemporaryDirectory(prefix="rosetta_relax_") as tmpdir:
            root = Path(tmpdir)
            input_pdb = root / "input.pdb"
            relax_dir = root / "relax"
            relax_dir.mkdir(parents=True, exist_ok=True)
            relax_scorefile = relax_dir / "score.sc"
            input_scorefile = root / "input_score.sc"
            input_pdb.write_text(str(pdb_text or ""), encoding="utf-8")

            relax_binary = self.container_relax_binary if mode == "docker" else str(self.relax_binary)
            score_binary = self.container_score_binary if mode == "docker" else str(self.score_binary)
            database = self._database_arg(mode=mode)
            input_pdb_arg = self._runtime_path(input_pdb, root=root, mode=mode)
            relax_dir_arg = self._runtime_path(relax_dir, root=root, mode=mode)
            relax_scorefile_arg = self._runtime_path(relax_scorefile, root=root, mode=mode)
            input_scorefile_arg = self._runtime_path(input_scorefile, root=root, mode=mode)

            relax_args = [
                str(relax_binary),
                "-database",
                database,
                "-in:file:s",
                input_pdb_arg,
                "-nstruct",
                str(max(1, int(nstruct))),
                "-out:path:all",
                relax_dir_arg,
                "-out:file:scorefile",
                relax_scorefile_arg,
                "-relax:constrain_relax_to_start_coords",
                "-use_input_sc",
                "-overwrite",
            ]
            if extra_flags:
                relax_args.extend(shlex.split(str(extra_flags)))
            self._run(relax_args, workdir=root, mode=mode)

            relax_rows = _parse_rosetta_scorefile(relax_scorefile)
            best_row = _best_score_row(relax_rows)
            best_description = str(best_row.get("description") or "").strip()
            if not best_description:
                raise RuntimeError("Rosetta relax output did not include a pose description")

            relaxed_pdb_path: Path | None = None
            for candidate in (
                relax_dir / f"{best_description}.pdb",
                relax_dir / f"{best_description}.pdb.gz",
            ):
                if candidate.exists():
                    relaxed_pdb_path = candidate
                    break
            if relaxed_pdb_path is None:
                matches = sorted(relax_dir.glob(f"{best_description}*.pdb*"))
                if matches:
                    relaxed_pdb_path = matches[0]
            if relaxed_pdb_path is None:
                raise RuntimeError(f"Rosetta relax output PDB missing for {best_description}")

            input_score_args = [
                str(score_binary),
                "-database",
                database,
                "-in:file:s",
                input_pdb_arg,
                "-out:file:scorefile",
                input_scorefile_arg,
                "-overwrite",
            ]
            self._run(input_score_args, workdir=root, mode=mode)

            input_rows = _parse_rosetta_scorefile(input_scorefile)
            input_row = _best_score_row(input_rows)
            input_total_score = float(input_row.get("total_score", input_row.get("score")))
            total_score = float(best_row.get("total_score", best_row.get("score")))
            best_pdb_text = _read_pdb_text(relaxed_pdb_path)

            return {
                "description": best_description,
                "total_score": total_score,
                "input_total_score": input_total_score,
                "delta_total_score": total_score - input_total_score,
                "best_pdb_text": best_pdb_text,
                "nstruct": max(1, int(nstruct)),
                "extra_flags": str(extra_flags).strip() or None,
                "mode": mode,
            }
