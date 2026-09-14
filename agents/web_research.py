from __future__ import annotations

import asyncio

from app.agents.base import BaseAgent
from app.tools.web_search import search_web


class WebResearchAgent(BaseAgent):
    name = "web_research"
    title = "Web Research"

    async def run(self, queries: list[str]) -> list[dict]:
        await self.event("start", message="Searching the live web with multiple queries.")
        results: list[dict] = []
        for q in queries[:6]:
            await self.event("tool_call", tool="web_search", message=q)
            batch = await asyncio.to_thread(search_web, q, 6)
            await self.event("tool_result", tool="web_search", message=f"{len(batch)} hits for “{q}”")
            results.extend(batch)
        await self.event("complete", message=f"Collected {len(results)} web results.")
        return results
