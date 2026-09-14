from __future__ import annotations

from app.agents.base import BaseAgent
from app.llm.factory import llm_json


class SynthesizerAgent(BaseAgent):
    name = "synthesizer"
    title = "Research Synthesizer"

    async def run(self, query: str, analysis: dict, gaps: dict, contradictions: dict, evidence: list[dict]) -> dict:
        await self.event("start", message="Synthesizing a coherent research narrative.")
        cites = [f"[{i+1}] {e.get('title')} — {e.get('url')}" for i, e in enumerate(evidence[:12])]
        fallback = {
            "narrative": (
                f"This briefing surveys “{query}” using live web and academic retrieval. "
                f"Dominant themes include: {', '.join((analysis.get('themes') or [])[:4])}. "
                f"Open gaps: {'; '.join((gaps.get('gaps') or [])[:2])}."
            ),
            "takeaways": (analysis.get("key_findings") or [])[:6],
            "citations": cites,
        }
        result = await llm_json(
            self.llm,
            system="Synthesize research. JSON: narrative (string, 3-6 paragraphs), takeaways (array), citations (array of strings).",
            user=f"Topic: {query}\nAnalysis: {analysis}\nGaps: {gaps}\nContradictions: {contradictions}\nSources:\n" + "\n".join(cites),
            fallback=fallback,
        )
        if not result.get("citations"):
            result["citations"] = cites
        await self.event("complete")
        return result
