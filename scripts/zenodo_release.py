#!/usr/bin/env python3
"""기존 Zenodo 레코드의 새 버전을 만든다. 초안 생성과 발행을 분리한다.

토큰은 pipeline-mcp/.env 의 ZENODO_TOKEN 에서 읽고, 화면에 출력하지 않는다.

    # 1단계: 초안 생성과 파일 업로드 (지울 수 있다)
    python3 scripts/zenodo_release.py draft \\
        --archive dist/protein_pipeline-1.1.0.tar.gz --version 1.1.0

    # Zenodo 웹에서 초안을 확인한 뒤
    # 2단계: 발행 (되돌릴 수 없다. DOI 가 영구 발급된다)
    python3 scripts/zenodo_release.py publish --draft-id <초안 ID>

    # 초안을 버리려면
    python3 scripts/zenodo_release.py discard --draft-id <초안 ID>
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import sys
from pathlib import Path

import requests

API = "https://zenodo.org/api"
ENV = Path("/opt/protein_pipeline/pipeline-mcp/.env")
LATEST_RECORD = "21215253"          # 1.0.20 (concept 20619413)


def token() -> str:
    for line in ENV.read_text("utf-8").splitlines():
        if line.startswith("ZENODO_TOKEN="):
            v = line.split("=", 1)[1].strip().strip('"').strip("'")
            if v:
                return v
    sys.exit(f"ZENODO_TOKEN 이 비어 있다: {ENV}")


def call(method, url, tok, **kw):
    r = requests.request(method, url, headers={"Authorization": f"Bearer {tok}"},
                         timeout=kw.pop("timeout", 120), **kw)
    if r.status_code >= 400:
        sys.exit(f"{method} {url.replace(API, '')} 실패 {r.status_code}: {r.text[:400]}")
    return r.json() if r.content else {}


def md5(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def draft(a, tok):
    archive = Path(a.archive)
    if not archive.is_file():
        sys.exit(f"묶음이 없다: {archive}")

    res = call("POST", f"{API}/deposit/depositions/{a.record}/actions/newversion", tok)
    draft_url = res["links"]["latest_draft"]
    d = call("GET", draft_url, tok)
    did = d["id"]
    print(f"초안 생성: id {did}")

    for f in d.get("files", []):
        call("DELETE", f["links"]["self"], tok)
        print(f"  이전 파일 제거: {f['filename']}")

    bucket = d["links"]["bucket"]
    with archive.open("rb") as fh:
        up = call("PUT", f"{bucket}/{archive.name}", tok, data=fh, timeout=3600)
    local = md5(archive)
    remote = (up.get("checksum") or "").replace("md5:", "")
    print(f"  업로드: {archive.name} · md5 {'일치' if local == remote else '불일치 ' + remote}")
    if local != remote:
        sys.exit("업로드 무결성 확인 실패. 초안을 확인하거나 discard 하라.")

    meta = d["metadata"]
    meta["version"] = a.version
    meta["publication_date"] = dt.date.today().isoformat()
    note = (f"<p><b>{a.version}</b>: solubility scores were recomputed with the official "
            "SoluProt 1.0.1.0 release (TMHMM-independent model) and all benchmark "
            "analyses were re-run. Includes a reproduction script "
            "(scripts/reproduce_paper_tables_figures.sh) and SoluProt rescoring script "
            "(scripts/score_soluprot.py). See docs/reproducibility.md.</p>")
    meta["description"] = note + (meta.get("description") or "")
    call("PUT", f"{API}/deposit/depositions/{did}", tok, json={"metadata": meta})
    print(f"  메타데이터: version {a.version}, date {meta['publication_date']}")
    print()
    print(f"초안 확인: https://zenodo.org/uploads/{did}")
    print(f"발행:      python3 scripts/zenodo_release.py publish --draft-id {did}")


def publish(a, tok):
    d = call("POST", f"{API}/deposit/depositions/{a.draft_id}/actions/publish", tok)
    print(f"발행 완료. 버전 DOI {d.get('doi')} · concept DOI {d.get('conceptdoi')}")
    print(f"레코드: {d.get('links', {}).get('record_html') or d.get('links', {}).get('html')}")


def discard(a, tok):
    call("DELETE", f"{API}/deposit/depositions/{a.draft_id}", tok)
    print(f"초안 {a.draft_id} 를 버렸다.")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("draft")
    p.add_argument("--archive", required=True)
    p.add_argument("--version", required=True)
    p.add_argument("--record", default=LATEST_RECORD)
    for name in ("publish", "discard"):
        q = sub.add_parser(name)
        q.add_argument("--draft-id", required=True)
    a = ap.parse_args(argv)
    tok = token()
    {"draft": draft, "publish": publish, "discard": discard}[a.cmd](a, tok)
    return 0


if __name__ == "__main__":
    sys.exit(main())
