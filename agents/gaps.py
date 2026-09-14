from __future__ import annotations

from app.agents.base import BaseAgent
from app.llm.factory import llm_json


class GapDetectionAgent(BaseAgent):
    name = "gaps"
    title = "Research Gap Detection"

    async def run(self, query: str, plan: dict, analysis: dict, evidence: list[dict]) -> dict:
        await self.event("start", message="Looking for unanswered questions and missing evidence.")
        fallback = {
            "gaps": [
                "Limited longitudinal or large-scale empirical evaluation in retrieved sources.",
                "Few sources jointly cover technical methods and real-world deployment constraints.",
            ],
            "future_work": [
                "Controlled user studies and open datasets.",
                "Standardized evaluation metrics for the topic.",
            ],
        }
        result = await llm_json(
            self.llm,
            system="Identify research gaps. JSON: gaps (array), future_work (array).",
            user=(
                f"Topic: {query}\nPlan questions: {plan.get('questions')}\n"
                f"Themes: {analysis.get('themes')}\nFindings: {analysis.get('key_findings')}\n"
                f"Evidence count: {len(evidence)}"
            ),
            fallback=fallback,
        )
        await self.event("complete", data=result)
        return result
