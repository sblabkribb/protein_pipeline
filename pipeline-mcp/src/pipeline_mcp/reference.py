"""참조 검색 — PDB·UniProt·InterPro·UniRef·Europe PMC.

소스마다 성격이 다르다: 구조(structural)는 좌표, 주석(curated)은 큐레이션,
군집(clusters)은 통계적 이웃, 문헌(published)은 누군가의 주장. 이 중 어느 것도
계획의 측정 근거가 되지는 않는다 — 참조 전용. 실패는 {"error": ...} 계약.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request

from . import literature as _literature

PDB_SEARCH_URL = "https://search.rcsb.org/rcsbsearch/v2/query"
UNIPROT_BASE = "https://rest.uniprot.org"
INTERPRO_BASE = "https://www.ebi.ac.uk/interpro/api"
REFERENCE_TIMEOUT_SECONDS = 10.0

ROW_KEYS = ("title", "detail", "identifier", "url", "source")


def _clamp_limit(limit) -> int:
    try:
        return max(1, min(int(limit), 25))
    except (TypeError, ValueError):
        return 8


def _row(title: str, detail: str, identifier: str, url: str, source: str) -> dict:
    return {"title": title, "detail": detail, "identifier": identifier,
            "url": url, "source": source}


def _get_json(url: str, source_label: str):
    request = urllib.request.Request(url)  # noqa: S310
    try:
        with urllib.request.urlopen(request, timeout=REFERENCE_TIMEOUT_SECONDS) as response:  # noqa: S310
            return json.loads(response.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{source_label} 요청 실패: {type(exc).__name__}"}


def _search_uniprot_family(subpath: str, query: str, limit: int, source_label: str) -> dict:
    """UniProt REST 공용 조립 (uniprotkb/uniref 가 같은 응답 골격을 쓴다)."""
    query = str(query or "").strip()
    if not query:
        return {"error": "query is required"}
    params = urllib.parse.urlencode({
        "query": query,
        "format": "json",
        "size": _clamp_limit(limit),
    })
    payload = _get_json(f"{UNIPROT_BASE}/{subpath}?{params}", source_label)
    if "error" in payload:
        return payload
    if not isinstance(payload, dict):
        return {"error": f"{source_label} 응답 형식 오류: {type(payload).__name__}"}
    return payload


def _pdb_title(entry: dict) -> str:
    """RCSB v2 full_text 응답의 본체는 identifier 다. 구조 이름이 딸려오는
    필드가 있으면 쓰고, 없으면 빈 문자열 — 폴백은 호출부가 identifier 로 만든다."""
    try:
        services = entry.get("services") or []
        nodes = services[0].get("nodes") or []
        contexts = nodes[0].get("match_context") or []
    except (AttributeError, IndexError, TypeError):
        return ""
    for context in contexts:
        if not isinstance(context, dict):
            continue
        for key in ("title", "rcsb_polymer_entity_container", "matched_string"):
            text = str(context.get(key) or "").strip()
            if text:
                return text[:120]
    return ""


def search_pdb(query: str, limit: int = 8) -> dict:
    """RCSB 실험 구조 검색. source=structural — 좌표 참조."""
    query = str(query or "").strip()
    if not query:
        return {"error": "query is required"}
    body = {
        "query": {"type": "terminal", "service": "full_text",
                  "parameters": {"value": query}},
        "request_options": {
            "paginate": {"start": 0, "rows": _clamp_limit(limit)},
            "results_content_type": ["experimental"],
        },
        "return_type": "entry",
    }
    request = urllib.request.Request(
        PDB_SEARCH_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )  # noqa: S310
    try:
        with urllib.request.urlopen(request, timeout=REFERENCE_TIMEOUT_SECONDS) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {"error": f"PDB 요청 실패: {type(exc).__name__}"}
    if not isinstance(payload, dict):
        return {"error": f"PDB 응답 형식 오류: {type(payload).__name__}"}
    items = []
    for entry in payload.get("result_set") or []:
        if not isinstance(entry, dict):
            continue
        identifier = str(entry.get("identifier") or "").strip()
        if not identifier:
            continue
        title = _pdb_title(entry) or f"PDB {identifier}"
        items.append(_row(title, "실험 구조 (PDB)", identifier,
                          f"https://www.rcsb.org/structure/{identifier}", "structural"))
    return {"items": items, "query": query}


def search_uniprot(query: str, limit: int = 8) -> dict:
    """UniProtKB 검색. source=curated — 큐레이션 주석 참조."""
    payload = _search_uniprot_family("uniprotkb/search", query, limit, "UniProt")
    if "error" in payload:
        return payload
    items = []
    for record in payload.get("results") or []:
        if not isinstance(record, dict):
            continue
        accession = str(record.get("primaryAccession") or "").strip()
        if not accession:
            continue
        description = record.get("proteinDescription") or {}
        if not isinstance(description, dict):
            description = {}
        # uniprotkb 응답은 recommendedName, uniref 계열 문서는 recommendedProteinName.
        recommended = (description.get("recommendedProteinName")
                       or description.get("recommendedName") or {})
        if not isinstance(recommended, dict):
            recommended = {}
        title = str((recommended.get("fullName") or {}).get("value") or "").strip()
        organism = record.get("organism") or {}
        if not isinstance(organism, dict):
            organism = {}
        sequence = record.get("sequence") or {}
        if not isinstance(sequence, dict):
            sequence = {}
        try:
            length = int(sequence.get("length") or record.get("length") or 0)
        except (TypeError, ValueError):
            length = 0
        detail_parts = [str(organism.get("scientificName") or "").strip()]
        if length:
            detail_parts.append(f"{length} aa")
        items.append(_row(title or accession, " · ".join(p for p in detail_parts if p),
                          accession, f"https://www.uniprot.org/uniprotkb/{accession}",
                          "curated"))
    return {"items": items, "query": str(query or "").strip()}


def search_interpro(query: str, limit: int = 8) -> dict:
    """InterPro 엔트리 검색. source=curated — 큐레이션 주석 참조."""
    query = str(query or "").strip()
    if not query:
        return {"error": "query is required"}
    params = urllib.parse.urlencode({
        "search": query,
        "page_size": _clamp_limit(limit),
    })
    payload = _get_json(f"{INTERPRO_BASE}/entry/interpro/?{params}", "InterPro")
    if "error" in payload:
        return payload
    if not isinstance(payload, dict):
        return {"error": f"InterPro 응답 형식 오류: {type(payload).__name__}"}
    items = []
    for record in payload.get("results") or []:
        if not isinstance(record, dict):
            continue
        metadata = record.get("metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}
        accession = str(metadata.get("accession") or "").strip()
        if not accession:
            continue
        name = metadata.get("name")
        if isinstance(name, dict):
            name = name.get("name")
        entry_type = str(metadata.get("type") or "").strip()
        source_db = str(metadata.get("source_database") or "").strip()
        detail = " · ".join(p for p in (entry_type, source_db) if p)
        items.append(_row(str(name or "").strip() or accession, detail, accession,
                          f"https://www.ebi.ac.uk/interpro/entry/InterPro/{accession}/",
                          "curated"))
    return {"items": items, "query": query}


def search_uniref(query: str, limit: int = 8) -> dict:
    """UniRef 군집 검색. source=clusters — 통계적 이웃 참조."""
    payload = _search_uniprot_family("uniref/search", query, limit, "UniRef")
    if "error" in payload:
        return payload
    items = []
    for record in payload.get("results") or []:
        if not isinstance(record, dict):
            continue
        uniref_id = str(record.get("id") or "").strip()
        if not uniref_id:
            continue
        try:
            # 최신 UniRef REST 응답은 memberCount 다 - proteinCount 는 구/문서 계열 폴백.
            protein_count = int(record.get("proteinCount") or record.get("memberCount") or 0)
        except (TypeError, ValueError):
            protein_count = 0
        items.append(_row(uniref_id, f"{protein_count} members", uniref_id,
                          f"https://www.uniprot.org/uniref/{uniref_id}", "clusters"))
    return {"items": items, "query": str(query or "").strip()}


def search_literature(query: str, limit: int = 8) -> dict:
    """Europe PMC 문헌 검색 재사용. source=published — 누군가의 주장 참조.

    기존 literature 행(authors/journal/year/...)을 균일 5키 행으로 맞춘다.
    """
    out = _literature.search_literature(query, limit)
    if "error" in out:
        return out
    items = []
    for row in out.get("items") or []:
        if not isinstance(row, dict):
            continue
        detail_parts = [str(row.get(k) or "").strip() for k in ("authors", "journal", "year")]
        detail = " · ".join(p for p in detail_parts if p)
        try:
            citations = int(row.get("citations") or 0)
        except (TypeError, ValueError):
            citations = 0
        if citations:
            detail = f"{detail} · 인용 {citations}" if detail else f"인용 {citations}"
        items.append(_row(str(row.get("title") or "").strip(), detail,
                          str(row.get("identifier") or ""), str(row.get("url") or ""),
                          "published"))
    return {"items": items, "query": out.get("query", query)}


SOURCES = {"pdb": search_pdb, "uniprot": search_uniprot, "interpro": search_interpro,
           "uniref": search_uniref, "literature": search_literature}


def search_reference(source: str, query: str, limit: int = 8) -> dict:
    fn = SOURCES.get(str(source or "").strip().lower())
    if fn is None:
        return {"error": f"unknown source: {source} (지원: {sorted(SOURCES)})"}
    return fn(query, limit)
