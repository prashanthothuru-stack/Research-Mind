from __future__ import annotations

from app.agents.base import BaseAgent
from app.llm.factory import llm_json


class ContradictionAgent(BaseAgent):
    name = "contradictions"
    title = "Contradiction Detection"

    async def run(self, query: str, evidence: list[dict], comparison: dict) -> dict:
        await self.event("start", message="Scanning claims for contradictions.")
        fallback = {
            "contradictions": comparison.get("disagreements") or [],
            "unresolved": [],
        }
        bundle = "\n".join(f"- {e.get('claim')}" for e in evidence[:20])
        result = await llm_json(
            self.llm,
            system="Find contradictions. JSON: contradictions (array of {claim_a, claim_b, why}), unresolved (array).",
            user=f"Topic: {query}\n{bundle}\nKnown disagreements: {comparison.get('disagreements')}",
            fallback=fallback,
        )
        await self.event("complete", data=result)
        return result
