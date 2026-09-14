from __future__ import annotations

from app.agents.base import BaseAgent
from app.llm.factory import llm_json


class ComparisonAgent(BaseAgent):
    name = "comparison"
    title = "Comparison"

    async def run(self, query: str, evidence: list[dict]) -> dict:
        await self.event("start", message="Comparing viewpoints across sources.")
        bundle = "\n".join(f"- {e.get('claim')} | {e.get('url')}" for e in evidence[:20])
        fallback = {
            "agreements": ["Multiple sources discuss the same core problem space."],
            "disagreements": [],
            "method_differences": [],
        }
        result = await llm_json(
            self.llm,
            system="Compare sources. JSON: agreements, disagreements, method_differences (arrays of short strings).",
            user=f"Topic: {query}\n{bundle}",
            fallback=fallback,
        )
        await self.event("complete", data=result)
        return result
