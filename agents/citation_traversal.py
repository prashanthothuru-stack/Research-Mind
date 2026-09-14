from __future__ import annotations

import httpx
from app.agents.base import BaseAgent


OPENALEX_WORKS = "https://api.openalex.org/works"


class CitationTraversalAgent(BaseAgent):
    name = "citation_traversal"
    title = "Citation Traversal"

    async def run(self, session_id: str, ranked_sources: list[dict]) -> tuple[list[dict], list[dict]]:
        await self.event("start", message="Traversing academic citation trees and reference networks.")

        academic_sources = [s for s in ranked_sources if s.get("source_type") == "academic" and s.get("openalex_id")]
        if not academic_sources:
            # Check by DOI if openalex_id not explicit
            academic_sources = [s for s in ranked_sources if s.get("doi")]

        edges: list[dict] = []
        new_discovered_sources: list[dict] = []

        async with httpx.AsyncClient(timeout=15.0) as client:
            for s in academic_sources[:4]:
                openalex_id = s.get("openalex_id")
                doi = s.get("doi")
                source_title = s.get("title", "Paper")

                target_identifier = openalex_id or (f"https://doi.org/{doi}" if doi else None)
                if not target_identifier:
                    continue

                await self.event("tool_call", tool="citation_graph_query", message=f"Inspecting references for: {source_title[:60]}")

                try:
                    url = f"{OPENALEX_WORKS}/{target_identifier.split('/')[-1]}"
                    res = await client.get(url, params={"mailto": "researchmind@local.dev"})
                    if res.status_code != 200:
                        continue
                    data = res.json()

                    # Check referenced works
                    ref_ids = data.get("referenced_works") or []
                    if ref_ids:
                        # Fetch the top 3 referenced papers
                        batch_ids = "|".join([r.split("/")[-1] for r in ref_ids[:3]])
                        ref_res = await client.get(
                            OPENALEX_WORKS,
                            params={"filter": f"openalex_id:{batch_ids}", "per_page": 3, "mailto": "researchmind@local.dev"},
                        )
                        if ref_res.status_code == 200:
                            ref_data = ref_res.json().get("results") or []
                            for ref in ref_data:
                                ref_title = (ref.get("display_name") or "").strip()
                                ref_doi = (ref.get("doi") or "").replace("https://doi.org/", "")
                                ref_url = ref.get("doi") or ref.get("id")

                                if ref_title:
                                    edges.append({
                                        "source_paper_title": source_title,
                                        "target_paper_title": ref_title,
                                        "target_doi": ref_doi,
                                        "target_url": ref_url,
                                        "relation": "cites",
                                    })
                                    new_discovered_sources.append({
                                        "title": ref_title,
                                        "url": ref_url,
                                        "snippet": f"Foundational reference cited by: {source_title[:80]}",
                                        "source_type": "academic",
                                        "venue": (ref.get("primary_location") or {}).get("source", {}).get("display_name") or "",
                                        "year": ref.get("publication_year"),
                                        "cited_by": ref.get("cited_by_count") or 0,
                                        "doi": ref_doi,
                                        "openalex_id": ref.get("id"),
                                        "score": 0.95,
                                    })
                except Exception:
                    continue

        # Persist edges to SQLite
        if edges:
            self.store.add_citation_edges(session_id, edges)

        await self.event(
            "decision",
            message=f"Discovered {len(edges)} citation connections and {len(new_discovered_sources)} foundational references.",
            data={"edge_count": len(edges), "references_found": len(new_discovered_sources)},
        )
        await self.event("complete", message="Citation network graph constructed.")

        return edges, new_discovered_sources
