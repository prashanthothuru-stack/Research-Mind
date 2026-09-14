from __future__ import annotations

from datetime import datetime, timezone

import httpx


OPENALEX = "https://api.openalex.org/works"
S2 = "https://api.semanticscholar.org/graph/v1/paper/search"


async def search_openalex(query: str, per_page: int = 6) -> list[dict]:
    params = {
        "search": query,
        "per_page": per_page,
        "sort": "relevance_score:desc",
        "mailto": "researchmind@local.dev",
    }
    out: list[dict] = []
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.get(OPENALEX, params=params)
            res.raise_for_status()
            data = res.json()
        for work in data.get("results") or []:
            loc = work.get("primary_location") or {}
            source = loc.get("source") or {}
            doi = (work.get("doi") or "").replace("https://doi.org/", "")
            url = loc.get("landing_page_url") or (f"https://doi.org/{doi}" if doi else work.get("id"))
            year = work.get("publication_year")
            out.append(
                {
                    "title": (work.get("display_name") or "").strip(),
                    "url": url or "",
                    "snippet": (work.get("abstract_inverted_index") and _rebuild_abstract(work["abstract_inverted_index"]))
                    or "",
                    "source_type": "academic",
                    "venue": source.get("display_name") or "",
                    "year": year,
                    "cited_by": work.get("cited_by_count") or 0,
                    "doi": doi,
                    "openalex_id": work.get("id"),
                    "authors": [
                        a.get("author", {}).get("display_name")
                        for a in (work.get("authorships") or [])[:8]
                        if a.get("author")
                    ],
                    "retrieved_at": datetime.now(timezone.utc).isoformat(),
                    "query": query,
                }
            )
    except Exception:
        return []
    return out


async def search_semantic_scholar(query: str, limit: int = 5) -> list[dict]:
    params = {
        "query": query,
        "limit": limit,
        "fields": "title,abstract,year,citationCount,url,externalIds,venue,authors",
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            res = await client.get(S2, params=params)
            if res.status_code >= 400:
                return []
            data = res.json()
    except Exception:
        return []
    out = []
    for paper in data.get("data") or []:
        ext = paper.get("externalIds") or {}
        doi = ext.get("DOI") or ""
        url = paper.get("url") or (f"https://doi.org/{doi}" if doi else "")
        authors = [a.get("name") for a in (paper.get("authors") or [])[:8] if a.get("name")]
        out.append(
            {
                "title": paper.get("title") or "",
                "url": url,
                "snippet": paper.get("abstract") or "",
                "source_type": "academic",
                "venue": paper.get("venue") or "",
                "year": paper.get("year"),
                "cited_by": paper.get("citationCount") or 0,
                "doi": doi,
                "authors": authors,
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "query": query,
            }
        )
    return out


async def search_academic(query: str, limit: int = 8) -> list[dict]:
    oa = await search_openalex(query, per_page=limit)
    if len(oa) >= 4:
        return oa
    s2 = await search_semantic_scholar(query, limit=limit)
    merged = { (r.get("doi") or r.get("url") or r.get("title")): r for r in oa + s2 }
    return list(merged.values())[:limit]


def _rebuild_abstract(inverted: dict) -> str:
    positions: list[tuple[int, str]] = []
    for word, idxs in inverted.items():
        for i in idxs:
            positions.append((i, word))
    positions.sort()
    return " ".join(w for _, w in positions)[:1800]
