#!/usr/bin/env python3
"""CATH domain classification 을 받아 RAPID 타겟용 superfamily 매핑을 만든다.

원본 목록(약 43MB)은 gitignore 되어 있고, 추적하는 것은 sha256 과
1,472 엔트리짜리 파생 매핑이다.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
from pathlib import Path
import sys
import urllib.request

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from rapid_sr.splits import parse_cath_domain_list  # noqa: E402

DEFAULT_URL = (
    "http://download.cathdb.info/cath/releases/latest-release/"
    "cath-classification-data/cath-domain-list.txt"
)
CATH_DIR = PROJECT_ROOT / "public_data" / "cath"
_SPLIT_PREFIXES = ("cath_train_", "cath_val_", "cath_test_")


def collect_target_ids(*, cath_outputs: Path, pdb_dirs: list[Path]) -> set[str]:
    targets: set[str] = set()
    if cath_outputs.exists():
        for run in cath_outputs.iterdir():
            if not run.is_dir():
                continue
            for prefix in _SPLIT_PREFIXES:
                if run.name.startswith(prefix):
                    targets.add(run.name[len(prefix):])
    for pdb_dir in pdb_dirs:
        if pdb_dir.exists():
            targets |= {path.stem for path in pdb_dir.glob("*.pdb")}
    return targets


def grouping_summary(mapping: dict[str, str]) -> dict[str, dict[str, int]]:
    summary: dict[str, dict[str, int]] = {}
    for name, depth in (("class", 1), ("architecture", 2), ("topology", 3), ("superfamily", 4)):
        groups = collections.Counter(
            ".".join(code.split(".")[:depth]) for code in mapping.values()
        )
        sizes = sorted(groups.values(), reverse=True)
        summary[name] = {
            "depth": depth,
            "groups": len(groups),
            "largest_group": sizes[0] if sizes else 0,
            "singletons": sum(1 for size in sizes if size == 1),
        }
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--raw", default=str(CATH_DIR / "cath-domain-list.txt"))
    parser.add_argument("--cath-outputs", default=str(PROJECT_ROOT / "cath_outputs_s3"))
    parser.add_argument(
        "--pdb-dirs",
        default="/opt/protein_pipeline/cath_train,/opt/protein_pipeline/cath_val,"
        "/opt/protein_pipeline/cath_test",
    )
    parser.add_argument("--skip-download", action="store_true")
    args = parser.parse_args(argv)

    raw = Path(args.raw)
    raw.parent.mkdir(parents=True, exist_ok=True)
    if not args.skip_download or not raw.exists():
        with urllib.request.urlopen(args.url, timeout=300) as response:
            raw.write_bytes(response.read())

    payload = raw.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    (raw.parent / f"{raw.name}.sha256").write_text(f"{digest}  {raw.name}\n", encoding="utf-8")

    mapping = parse_cath_domain_list(raw)
    targets = collect_target_ids(
        cath_outputs=Path(args.cath_outputs),
        pdb_dirs=[Path(part) for part in args.pdb_dirs.split(",") if part.strip()],
    )
    resolved = {target: mapping[target] for target in sorted(targets) if target in mapping}

    out_path = raw.parent / "rapid_target_superfamily.json"
    out_path.write_text(json.dumps(resolved, indent=1), encoding="utf-8")

    report = {
        "source_url": args.url,
        "sha256": digest,
        "classification_entries": len(mapping),
        "targets_referenced": len(targets),
        "targets_resolved": len(resolved),
        "unresolved": sorted(targets - set(resolved))[:20],
        "grouping": grouping_summary(resolved),
    }
    (raw.parent / "classification_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
