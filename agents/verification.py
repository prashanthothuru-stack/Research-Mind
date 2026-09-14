from __future__ import annotations

from app.agents.base import BaseAgent
from app.agents.source_discovery import credibility_score


class VerificationAgent(BaseAgent):
    name = "verification"
    title = "Evidence & Source Verification"

    async def run(self, sources: list[dict], evidence: list[dict]) -> dict:
        await self.event("start", message="Scoring credibility and flagging weak evidence.")
        verified = []
        flagged = []
        for s in sources:
            item = {
                "title": s.get("title"),
                "url": s.get("url"),
                "type": s.get("source_type"),
                "score": s.get("score") or credibility_score(s),
                "year": s.get("year"),
                "cited_by": s.get("cited_by"),
            }
            if item["score"] >= 0.55:
                verified.append(item)
            else:
                flagged.append({**item, "reason": "Low credibility / incomplete metadata"})
        report = {
            "verified_count": len(verified),
            "flagged_count": len(flagged),
            "verified": verified[:20],
            "flagged": flagged[:20],
            "notes": [
                "Academic records from OpenAlex/Semantic Scholar are preferred.",
                "Web snippets without a resolvable URL were down-ranked.",
                "Verification is heuristic (venue, citations, domain, recency) plus agent ranking.",
            ],
        }
        await self.event("decision", message=f"{len(verified)} sources pass the credibility bar.", data=report)
        await self.event("complete")
        return report
