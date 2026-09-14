from __future__ import annotations

from app.agents.base import BaseAgent
from app.llm.factory import llm_json


class ResearchPlannerAgent(BaseAgent):
    name = "planner"
    title = "Research Planner"

    async def run(self, query: str) -> dict:
        await self.event("start", message="Decomposing the research objective into a plan.")
        fallback = heuristic_plan(query)
        plan = await llm_json(
            self.llm,
            system=(
                "You are a research planner agent. Return JSON only with keys: "
                "research_goal, subtopics (array of strings), questions (array), "
                "required_sources (array), research_strategy (array of steps), "
                "search_queries (array of 4-8 web search queries), "
                "academic_queries (array of 3-6 scholarly search queries), "
                "tools_to_use (array). Be specific and academic."
            ),
            user=f"Research topic: {query}",
            fallback=fallback,
        )
        for key, val in fallback.items():
            if not plan.get(key):
                plan[key] = val
        await self.event("decision", message="Selected tools and subtopics.", data=plan)
        await self.event("complete", message="Plan ready.")
        return plan


def heuristic_plan(query: str) -> dict:
    q = query.strip()
    return {
        "research_goal": f"Produce a sourced research briefing on: {q}",
        "subtopics": [
            f"Foundations and definitions of {q}",
            f"Current methods and systems for {q}",
            f"Applications, case studies, and datasets related to {q}",
            f"Limitations, ethics, and open problems in {q}",
        ],
        "questions": [
            f"What is the current state of research on {q}?",
            f"Which methods dominate the literature on {q}?",
            f"Where are empirical gaps or contradictions on {q}?",
        ],
        "required_sources": ["peer-reviewed papers", "recent web articles", "official reports"],
        "research_strategy": [
            "Discover academic and web sources in parallel",
            "Extract evidence and embed for RAG",
            "Verify credibility, compare claims, detect gaps and contradictions",
            "Synthesize a cited report and voice script",
        ],
        "search_queries": [
            q,
            f"{q} recent research",
            f"{q} challenges limitations",
            f"{q} applications case study",
        ],
        "academic_queries": [q, f"{q} survey", f"{q} systematic review"],
        "tools_to_use": ["web_search", "academic_search", "fetch_url", "rag"],
    }
