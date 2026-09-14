from __future__ import annotations

from datetime import datetime, timezone

from app.agents.base import BaseAgent
from app.llm.factory import llm_json


class ReportGeneratorAgent(BaseAgent):
    name = "report"
    title = "Report Generator"

    async def run(self, query: str, plan: dict, synthesis: dict, gaps: dict, contradictions: dict, verification: dict) -> str:
        await self.event("start", message="Writing the cited research report.")
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        fallback = _markdown(query, date, plan, synthesis, gaps, contradictions, verification)
        parsed = await llm_json(
            self.llm,
            system="Write a markdown research report. JSON: {\"markdown\": \"...\"} with headings, citations, gaps, contradictions.",
            user=fallback[:6000],
            fallback={"markdown": fallback},
        )
        md = parsed.get("markdown") if isinstance(parsed, dict) else None
        report = md if isinstance(md, str) and len(md) > 200 else fallback
        await self.event("complete")
        return report


def _markdown(query, date, plan, synthesis, gaps, contradictions, verification) -> str:
    takes = "\n".join(f"- {t}" for t in (synthesis.get("takeaways") or [])[:8])
    gap_l = "\n".join(f"- {g}" for g in (gaps.get("gaps") or []))
    fut = "\n".join(f"- {g}" for g in (gaps.get("future_work") or []))
    contras = contradictions.get("contradictions") or []
    if contras and isinstance(contras[0], dict):
        c_l = "\n".join(
            f"- {c.get('claim_a')} vs {c.get('claim_b')} — {c.get('why')}" for c in contras[:8]
        )
    else:
        c_l = "\n".join(f"- {c}" for c in contras)
    cites = "\n".join(f"- {c}" for c in (synthesis.get("citations") or []))
    return f"""# ResearchMind Report

**Topic:** {query}  
**Generated:** {date} UTC  
**Pipeline:** Agentic multi-tool research (planner → discovery → web/academic → extraction → verification → analysis)

## Goal
{plan.get('research_goal')}

## Executive synthesis
{synthesis.get('narrative')}

## Key takeaways
{takes}

## Research gaps
{gap_l}

## Future work
{fut}

## Contradictions and tensions
{c_l or '- No strong contradictions were confidently identified from the retrieved set.'}

## Source verification summary
- Verified sources: {verification.get('verified_count')}
- Flagged sources: {verification.get('flagged_count')}

## Citations
{cites}

---
*Produced by ResearchMind. Claims should be checked against the original papers and pages.*
"""
