from __future__ import annotations

from datetime import datetime, timezone

from ddgs import DDGS


def search_web(query: str, max_results: int = 8) -> list[dict]:
    rows: list[dict] = []
    try:
        with DDGS() as ddgs:
            for item in ddgs.text(query, max_results=max_results):
                rows.append(
                    {
                        "title": item.get("title") or "",
                        "url": item.get("href") or item.get("url") or "",
                        "snippet": item.get("body") or item.get("snippet") or "",
                        "source_type": "web",
                        "retrieved_at": datetime.now(timezone.utc).isoformat(),
                        "query": query,
                    }
                )
    except Exception as exc:
        rows.append(
            {
                "title": "Web search unavailable",
                "url": "",
                "snippet": str(exc),
                "source_type": "error",
                "query": query,
            }
        )
    return [r for r in rows if r.get("url")]
