from __future__ import annotations

from urllib.parse import urlparse

from app.agents.base import BaseAgent


TRUSTED_DOMAINS = {
    "arxiv.org",
    "acm.org",
    "ieee.org",
    "nature.com",
    "sciencedirect.com",
    "springer.com",
    "nih.gov",
    "who.int",
    "edu",
    "gov",
    "openalex.org",
    "semanticscholar.org",
    "wikipedia.org",
    "ssrn.com",
    "pubmed.ncbi.nlm.nih.gov",
}


def domain_of(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return ""


def credibility_score(source: dict) -> float:
    score = 0.4
    st = source.get("source_type")
    if st == "academic":
        score += 0.35
    cited = float(source.get("cited_by") or 0)
    score += min(0.2, cited / 500.0)
    year = source.get("year")
    if isinstance(year, int) and year >= 2020:
        score += 0.1
    host = domain_of(source.get("url") or "")
    if any(host.endswith(d) or d in host for d in TRUSTED_DOMAINS):
        score += 0.15
    title = (source.get("title") or "") + " " + (source.get("snippet") or "")
    if len(title) > 80:
        score += 0.05
    return round(min(score, 0.99), 3)


class SourceDiscoveryAgent(BaseAgent):
    name = "source_discovery"
    title = "Source Discovery"

    async def run(self, sources: list[dict], plan: dict) -> list[dict]:
        await self.event("start", message="Ranking discovered sources by relevance and credibility.")
        ranked = []
        seen = set()
        for s in sources:
            key = (s.get("doi") or s.get("url") or s.get("title") or "").lower()
            if not key or key in seen:
                continue
            seen.add(key)
            s = dict(s)
            s["score"] = credibility_score(s)
            ranked.append(s)
        ranked.sort(key=lambda x: x.get("score", 0), reverse=True)
        await self.event(
            "decision",
            message=f"Kept {len(ranked)} unique sources after ranking.",
            data={"top": [{"title": s.get("title"), "score": s.get("score"), "type": s.get("source_type")} for s in ranked[:8]]},
        )
        await self.event("complete")
        return ranked
