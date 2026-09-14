from __future__ import annotations

import json
from typing import Awaitable, Callable

from app.agents.academic_research import AcademicResearchAgent
from app.agents.analysis import AnalysisAgent
from app.agents.citation_traversal import CitationTraversalAgent
from app.agents.comparison import ComparisonAgent
from app.agents.contradictions import ContradictionAgent
from app.agents.critic import CriticAgent
from app.agents.extraction import ExtractionAgent
from app.agents.gaps import GapDetectionAgent
from app.agents.planner import ResearchPlannerAgent
from app.agents.report import ReportGeneratorAgent
from app.agents.source_discovery import SourceDiscoveryAgent
from app.agents.synthesizer import SynthesizerAgent
from app.agents.verification import VerificationAgent
from app.agents.voice import VoiceExplanationAgent
from app.agents.web_research import WebResearchAgent
from app.db.store import Store
from app.llm.base import LLMProvider


class Orchestrator:
    def __init__(self, llm: LLMProvider, store: Store):
        self.llm = llm
        self.store = store

    async def run(self, session_id: str, query: str, emit: Callable[[dict], Awaitable[None]]) -> dict:
        def agent(cls):
            return cls(self.llm, self.store, emit)

        plan = await agent(ResearchPlannerAgent).run(query)
        self.store.update_session(session_id, plan_json=json.dumps(plan))
        self.store.add_finding(session_id, "plan", plan)

        web = await agent(WebResearchAgent).run(plan.get("search_queries") or [query])
        academic = await agent(AcademicResearchAgent).run(plan.get("academic_queries") or [query])
        ranked = await agent(SourceDiscoveryAgent).run(web + academic, plan)
        ranked = ranked[: self.store.settings.max_sources]

        # Multi-Hop Citation Traversal
        citation_edges, foundational_papers = await agent(CitationTraversalAgent).run(session_id, ranked)
        if foundational_papers:
            # Register newly discovered foundational papers as sources
            for fp in foundational_papers[:4]:
                if not any(s.get("url") == fp.get("url") for s in ranked):
                    ranked.append(fp)

        evidence = await agent(ExtractionAgent).run(session_id, ranked, self.store.settings.embedding_dim)
        verification = await agent(VerificationAgent).run(ranked, evidence)
        analysis = await agent(AnalysisAgent).run(query, evidence)
        comparison = await agent(ComparisonAgent).run(query, evidence)
        gaps = await agent(GapDetectionAgent).run(query, plan, analysis, evidence)
        contradictions = await agent(ContradictionAgent).run(query, evidence, comparison)
        synthesis = await agent(SynthesizerAgent).run(query, analysis, gaps, contradictions, evidence)

        # Adversarial Critic Peer-Review
        critic_review = await agent(CriticAgent).run(query, synthesis, evidence, ranked)

        markdown = await agent(ReportGeneratorAgent).run(
            query, plan, synthesis, gaps, contradictions, verification
        )
        voice_script = await agent(VoiceExplanationAgent).run(query, synthesis, gaps)

        for kind, payload in [
            ("verification", verification),
            ("analysis", analysis),
            ("comparison", comparison),
            ("gaps", gaps),
            ("contradictions", contradictions),
            ("synthesis", synthesis),
            ("critic", critic_review),
            ("citation_edges", citation_edges),
        ]:
            self.store.add_finding(session_id, kind, payload)

        report_id = self.store.add_report(session_id, markdown, voice_script)
        result = {
            "plan": plan,
            "source_count": len(ranked),
            "evidence_count": len(evidence),
            "verification": verification,
            "analysis": analysis,
            "comparison": comparison,
            "gaps": gaps,
            "contradictions": contradictions,
            "synthesis": synthesis,
            "critic": critic_review,
            "citation_edge_count": len(citation_edges),
            "report_id": report_id,
            "llm": self.llm.name,
        }
        self.store.update_session(
            session_id, status="completed", result_json=json.dumps(result)
        )
        await emit({"agent": "orchestrator", "title": "Orchestrator", "kind": "complete", "message": "Pipeline finished."})
        return result

