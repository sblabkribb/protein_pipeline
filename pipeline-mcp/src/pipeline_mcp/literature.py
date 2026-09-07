"""Europe PMC 문헌 검색. 결과는 published 참조용이다.

근거 철학: 계획의 결정 근거는 우리가 측정한 값이거나 검증된 문헌이다. 이 도구가
돌려주는 검색 결과는 그보다 약한 '누군가의 주장'이다 - 참조로 보여주되, 계획의
측정 근거와 같은 칸에 두지 않는다. UI 도 출처 라벨로 이 둘을 섞지 않는다.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request

EUROPEPMC_BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest"
LITERATURE_TIMEOUT_SECONDS = 10.0


def _clamp_limit(limit) -> int:
    try:
        return max(1, min(int(limit), 25))
    except (TypeError, ValueError):
        return 8


def _row(record: dict) -> dict:
    doi = str(record.get("doi") or "").strip()
    pmid = str(record.get("pmid") or "").strip()
    identifier = doi or pmid or str(record.get("id") or "")
    if doi:
        url = f"https://doi.org/{doi}"
    elif pmid:
        url = f"https://europepmc.org/article/{record.get('source', 'MED')}/{pmid}"
    else:
        url = f"https://europepmc.org/article/{record.get('source', 'MED')}/{record.get('id')}"
    try:
        citations = int(record.get("citedByCount") or 0)
    except (TypeError, ValueError):
        citations = 0
    return {
        "title": str(record.get("title") or "").strip(),
        "authors": str(record.get("authorString") or "")[:80],
        "journal": str(record.get("journalTitle") or "").strip(),
        "year": str(record.get("pubYear") or "").strip(),
        "citations": citations,
        "open_access": record.get("isOpenAccess") == "Y",
        "identifier": identifier,
        "url": url,
    }


def search_literature(query: str, limit: int = 8) -> dict:
    """문헌 검색. 실패는 예외 대신 {"error": ...} 계약으로 돌려준다."""
    query = str(query or "").strip()
    if not query:
        return {"error": "query is required"}
    params = urllib.parse.urlencode({
        "query": query,
        "format": "json",
        "pageSize": _clamp_limit(limit),
        "resultType": "lite",
        "sort": "CITED desc",
    })
    request = urllib.request.Request(f"{EUROPEPMC_BASE}/search?{params}")  # noqa: S310
    try:
        with urllib.request.urlopen(request, timeout=LITERATURE_TIMEOUT_SECONDS) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {"error": f"Europe PMC 요청 실패: {type(exc).__name__}"}
    # 응답이 객체가 아니어도 오류 계약으로 돌아간다.
    if not isinstance(payload, dict):
        return {"error": f"Europe PMC 응답 형식 오류: {type(payload).__name__}"}
    records = (payload.get("resultList") or {}).get("result") or []
    rows = [record for record in records
            if isinstance(record, dict)
            and any(str(record.get(k) or "").strip() for k in ("doi", "pmid", "id"))]
    return {"items": [_row(record) for record in rows], "query": query}
