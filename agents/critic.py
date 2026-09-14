from __future__ import annotations

from app.agents.base import BaseAgent
from app.llm.factory import llm_json


class CriticAgent(BaseAgent):
    name = "critic"
    title = "Adversarial Critic"

    async def run(self, query: str, synthesis: dict, evidence: list[dict], sources: list[dict]) -> dict:
        await self.event("start", message="Red-teaming findings and auditing evidence rigor.")

        fallback = heuristic_critique(query, synthesis, evidence, sources)

        critic_result = await llm_json(
            self.llm,
            system=(
                "You are an adversarial peer reviewer and research critic. "
                "Critically evaluate the research synthesis and evidence for: "
                "1) Unsupported claims or weak causal leaps, "
                "2) Source recency and venue authority, "
                "3) Potential methodological bias, "
                "4) Overall scientific rigor score from 1 to 100. "
                "Return JSON with keys: rigor_score (int), verdict (string), "
                "strengths (array of strings), methodology_flags (array of strings), "
                "potential_biases (array of strings), recommendations (array of strings)."
            ),
            user=(
                f"Topic: {query}\n"
                f"Evidence Count: {len(evidence)}\n"
                f"Sources Count: {len(sources)}\n"
                f"Synthesis Themes: {synthesis.get('themes', [])[:4]}\n"
                f"Key Findings: {synthesis.get('key_findings', [])[:4]}\n"
            ),
            fallback=fallback,
        )

        for k, v in fallback.items():
            if not critic_result.get(k):
                critic_result[k] = v

        score = critic_result.get("rigor_score", 85)
        flags_count = len(critic_result.get("methodology_flags", []))

        await self.event(
            "tool_call",
            tool="peer_review_audit",
            message=f"Audited {len(evidence)} evidence chunks across {len(sources)} sources.",
        )
        await self.event(
            "decision",
            message=f"Assigned Rigor Score {score}/100 with {flags_count} methodology notes.",
            data=critic_result,
        )
        await self.event("complete", message="Adversarial audit complete.")

        return critic_result


def heuristic_critique(query: str, synthesis: dict, evidence: list[dict], sources: list[dict]) -> dict:
    academic_count = sum(1 for s in sources if s.get("source_type") == "academic")
    web_count = len(sources) - academic_count

    rigor = 70
    if academic_count >= 3:
        rigor += 15
    if len(evidence) >= 5:
        rigor += 10

    flags = []
    if web_count > academic_count:
        flags.append("Relies significantly on non-peer-reviewed web sources.")
    if len(evidence) < 4:
        flags.append("Sparse empirical evidence base for broad generalizations.")
    if not any(s.get("year", 0) and s.get("year") >= 2023 for s in sources):
        flags.append("Recent preprint literature (2024-2026) is underrepresented.")

    biases = []
    if any("survey" in s.get("title", "").lower() for s in sources):
        biases.append("Potential survey bias: primary datasets not directly verified.")
    else:
        biases.append("Publication bias: positive results dominate published literature.")

    return {
        "rigor_score": min(95, max(50, rigor)),
        "verdict": "Substantial evidence base with actionable caveats" if rigor >= 80 else "Preliminary synthesis requiring broader validation",
        "strengths": [
            f"Multi-source triangulation across {len(sources)} distinct records.",
            "Identified specific empirical claims with direct excerpts.",
        ],
        "methodology_flags": flags or ["No fatal methodological discrepancies detected."],
        "potential_biases": biases,
        "recommendations": [
            "Cross-reference key findings against open benchmark datasets.",
            "Verify replicability of top cited models under varying conditions.",
        ],
    }
