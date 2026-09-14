from __future__ import annotations

from app.agents.base import BaseAgent
from app.llm.factory import llm_json


class VoiceExplanationAgent(BaseAgent):
    name = "voice"
    title = "Voice Explanation"

    async def run(self, query: str, synthesis: dict, gaps: dict) -> str:
        await self.event("start", message="Writing a spoken briefing script.")
        fallback = (
            f"Here is a short research briefing on {query}. "
            f"{(synthesis.get('narrative') or '')[:900]} "
            f"The main gaps are: {'; '.join((gaps.get('gaps') or [])[:2])}. "
            "Please review the full report for citations."
        )
        parsed = await llm_json(
            self.llm,
            system="Write a 60-90 second spoken script. JSON: {\"script\": \"...\"}. No markdown, no URLs.",
            user=f"Topic: {query}\nNarrative: {synthesis.get('narrative')}\nTakeaways: {synthesis.get('takeaways')}\nGaps: {gaps.get('gaps')}",
            fallback={"script": fallback},
        )
        script = parsed.get("script") if isinstance(parsed, dict) else None
        text = script if isinstance(script, str) and script.strip() else fallback
        await self.event("complete")
        return text.strip()
