#!/usr/bin/env python3
"""폴드 산출물을 S3 에 올리고, 올라갔다는 것을 확인한다.

왜 필요한가
-----------
지표 정의 때문에 재폴딩한 것이 세 번이다. 그 고리를 끊으려고 모델 좌표를
저장하기 시작했는데, .gitignore 의 `*.pdb.gz` 규칙에 걸려 좌표가 이 디스크에만
있다. 디스크가 유일한 사본이면 보관한 것이 아니다.

왜 NCPStorage.upload_file 을 그대로 쓰지 않는가
-----------------------------------------------
그 함수는 예외를 잡아 출력하고 False 를 돌려준다. 호출자가 반환값을 안 보면
실패가 성공처럼 지나간다. 보관 보장을 그 위에 세울 수 없어서, client 를 직접
쓰고 올린 뒤 head_object 로 크기를 대조한다. 확인되지 않으면 실패로 센다.

무엇을 남기는가
---------------
파일마다 sha256 과 원격 key 를 manifest 에 적는다. 나중에 지표가 또 바뀌면
이 manifest 로 좌표를 찾고, 받은 파일이 올릴 때와 같은지 대조할 수 있다.
자격증명은 환경변수에서만 읽고 manifest 에 적지 않는다.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "pipeline-mcp" / "src"))

BASE = PROJECT_ROOT / "public_data" / "benchmark" / "gate0"
#: 원격 접두사. 프로토콜이 바뀌면 접두사도 바꿔서 섞이지 않게 한다.
REMOTE_PREFIX = "rapid_sr/gate0_frozen_metric_v1"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def archive(storage, files: list[Path], *, root: Path, prefix: str,
            manifest_path: Path, dry_run: bool) -> dict:
    client = storage.client
    if client is None and not dry_run:
        raise SystemExit(
            "S3 자격증명이 없다. --env-file 로 .env 를 주거나 환경변수를 설정한다. "
            "자격증명은 저장소에 기록하지 않는다."
        )
    bucket = storage.bucket

    entries = {}
    if manifest_path.exists():
        prior = json.loads(manifest_path.read_text(encoding="utf-8"))
        entries = {e["local"]: e for e in prior.get("files", [])}

    uploaded = skipped = failed = 0
    for index, path in enumerate(files, start=1):
        rel = path.relative_to(root).as_posix()
        key = f"{prefix}/{rel}"
        size = path.stat().st_size

        prior = entries.get(rel)
        if prior and prior.get("size") == size and prior.get("verified"):
            skipped += 1
            continue

        if dry_run:
            print(f"  [dry-run] {rel} -> s3://{bucket}/{key} ({size} B)")
            uploaded += 1
            continue

        digest = sha256_file(path)
        try:
            client.upload_file(str(path), bucket, key)
            head = client.head_object(Bucket=bucket, Key=key)
            remote_size = int(head["ContentLength"])
            if remote_size != size:
                raise RuntimeError(f"크기 불일치: 로컬 {size} 원격 {remote_size}")
            verified = True
            error = None
        except Exception as exc:
            verified = False
            error = f"{type(exc).__name__}: {exc}"
            failed += 1
            print(f"  [실패] {rel}: {error}"[:200], flush=True)
        else:
            uploaded += 1

        entries[rel] = {"local": rel, "key": key, "size": size,
                        "sha256": digest, "verified": verified}
        if error:
            entries[rel]["error"] = error

        if index % 100 == 0 or index == len(files):
            print(f"  {index}/{len(files)} · 올림 {uploaded} 건너뜀 {skipped} "
                  f"실패 {failed}", flush=True)
            _write_manifest(manifest_path, entries, bucket, prefix, root)

    if not dry_run:
        _write_manifest(manifest_path, entries, bucket, prefix, root)
    return {"uploaded": uploaded, "skipped": skipped, "failed": failed,
            "n_files": len(files)}


def _write_manifest(path: Path, entries: dict, bucket: str, prefix: str,
                    root: Path) -> None:
    verified = sum(1 for e in entries.values() if e.get("verified"))
    path.write_text(json.dumps({
        "purpose": "폴드 산출물의 원격 사본 목록. 지표가 또 바뀌면 여기서 좌표를 찾는다.",
        "bucket": bucket,
        "prefix": prefix,
        "local_root": str(root.relative_to(PROJECT_ROOT)),
        "endpoint": os.getenv("NCP_S3_ENDPOINT", ""),
        "credentials": "환경변수에서만 읽는다. 저장소에 기록하지 않는다.",
        "n_files": len(entries),
        "n_verified": verified,
        "verification": "올린 뒤 head_object 로 크기를 대조한 것만 verified 다.",
        "code_sha": subprocess.run(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT,
                                   capture_output=True, text=True).stdout.strip(),
        "updated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "files": sorted(entries.values(), key=lambda e: e["local"]),
    }, indent=2, ensure_ascii=False), encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", action="append", default=[],
                        help="올릴 디렉터리. 여러 번 줄 수 있다. 기본은 세 패널.")
    parser.add_argument("--prefix", default=REMOTE_PREFIX)
    parser.add_argument("--manifest", default=str(BASE / "fold_artifact_archive.json"))
    parser.add_argument("--env-file", default="/opt/protein_pipeline/pipeline-mcp/.env")
    parser.add_argument("--include", default=".pdb.gz,.csv,.json",
                        help="이 확장자로 끝나는 파일만 올린다")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    env_file = Path(args.env_file)
    if env_file.exists():
        from dotenv import load_dotenv
        load_dotenv(str(env_file), override=False)
        print(f"env_file={env_file} (자격증명은 출력하지 않는다)")

    def _resolve(value: str) -> Path:
        """상대 경로도 받는다. 저장소 밖을 가리키면 거부한다."""
        path = Path(value)
        path = path if path.is_absolute() else (PROJECT_ROOT / path)
        path = path.resolve()
        if not path.is_relative_to(BASE):
            raise SystemExit(f"게이트 0 산출물 디렉터리가 아니다: {path}")
        return path

    dirs = [_resolve(d) for d in args.dir] or [
        BASE / "temperature_sweep", BASE / "temperature_panel2", BASE / "holdout_grid",
    ]
    suffixes = tuple(s.strip() for s in args.include.split(",") if s.strip())

    files: list[Path] = []
    for directory in dirs:
        if not directory.exists():
            print(f"없음, 건너뜀: {directory.relative_to(PROJECT_ROOT)}")
            continue
        found = sorted(p for p in directory.rglob("*")
                       if p.is_file() and p.name.endswith(suffixes))
        print(f"{directory.relative_to(PROJECT_ROOT)}: {len(found)} 파일")
        files.extend(found)

    if not files:
        print("올릴 파일이 없다")
        return 0

    total_mb = sum(p.stat().st_size for p in files) / 1e6
    print(f"\n총 {len(files)} 파일 · {total_mb:.1f} MB · 접두사 {args.prefix}")

    from pipeline_mcp.s3 import NCPStorage  # noqa: E402
    result = archive(NCPStorage(), files, root=BASE, prefix=args.prefix,
                     manifest_path=Path(args.manifest), dry_run=args.dry_run)

    print(f"\n올림 {result['uploaded']} · 건너뜀 {result['skipped']} "
          f"· 실패 {result['failed']} / {result['n_files']}")
    if result["failed"]:
        print("실패가 있다. manifest 의 error 를 보고 다시 실행하면 실패한 것만 재시도한다.")
        return 1
    print(f"manifest: {args.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
