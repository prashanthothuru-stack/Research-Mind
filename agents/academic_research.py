from __future__ import annotations

from app.agents.base import BaseAgent
from app.tools.academic import search_academic


class AcademicResearchAgent(BaseAgent):
    name = "academic_research"
    title = "Academic Research"

    async def run(self, queries: list[str]) -> list[dict]:
        await self.event("start", message="Querying OpenAlex / Semantic Scholar.")
        results: list[dict] = []
        for q in queries[:5]:
            await self.event("tool_call", tool="academic_search", message=q)
            batch = await search_academic(q, limit=6)
            await self.event("tool_result", tool="academic_search", message=f"{len(batch)} papers for “{q}”")
            results.extend(batch)
        await self.event("complete", message=f"Collected {len(results)} academic records.")
        return results
