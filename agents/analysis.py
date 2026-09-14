from __future__ import annotations

from app.agents.base import BaseAgent
from app.llm.factory import llm_json


class AnalysisAgent(BaseAgent):
    name = "analysis"
    title = "Research Analysis"

    async def run(self, query: str, evidence: list[dict]) -> dict:
        await self.event("start", message="Analyzing themes, methods, and findings.")
        bundle = "\n".join(f"- {e.get('claim')} ({e.get('title')})" for e in evidence[:24])
        fallback = {
            "themes": _unique_phrases(evidence),
            "methods": ["literature synthesis from retrieved sources"],
            "key_findings": [e.get("claim") for e in evidence[:8] if e.get("claim")],
            "stakeholders": [],
        }
        result = await llm_json(
            self.llm,
            system="You are a research analysis agent. JSON keys: themes, methods, key_findings, stakeholders (all arrays of strings).",
            user=f"Topic: {query}\nEvidence:\n{bundle}",
            fallback=fallback,
        )
        await self.event("complete", data=result)
        return result


def _unique_phrases(evidence: list[dict]) -> list[str]:
    seen = []
    for e in evidence:
        c = (e.get("claim") or "")[:90]
        if c and c not in seen:
            seen.append(c)
        if len(seen) >= 6:
            break
    return seen or ["Insufficient clustered themes"]
