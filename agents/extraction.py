from __future__ import annotations

from app.agents.base import BaseAgent
from app.embeddings.local import chunk_text, embed_text
from app.llm.factory import llm_json
from app.tools.fetch import fetch_url
from app.tools.pdf import extract_pdf_bytes


class ExtractionAgent(BaseAgent):
    name = "extraction"
    title = "Document Extraction"

    async def run(self, session_id: str, sources: list[dict], dim: int) -> list[dict]:
        await self.event("start", message="Fetching pages and extracting evidence.")
        evidence = []
        fetched = 0
        for i, src in enumerate(sources):
            url = src.get("url") or ""
            text = src.get("snippet") or ""
            if url and i < self.store.settings.max_fetch:
                await self.event("tool_call", tool="fetch_url", message=url)
                page = await fetch_url(url)
                if page.get("is_pdf") and page.get("bytes"):
                    try:
                        text = extract_pdf_bytes(page["bytes"]) or text
                    except Exception:
                        pass
                elif page.get("ok") and page.get("text"):
                    text = page["text"][:9000]
                fetched += 1
            source_id = self.store.add_source(session_id, src)
            for chunk in chunk_text(text or src.get("snippet") or src.get("title") or "", 900, 120)[:4]:
                vec = embed_text(chunk, dim)
                self.store.add_embedding(session_id, chunk, vec, source_id)
            if i >= self.store.settings.max_fetch:
                continue
            claims = await self._claims(src, text)
            for c in claims:
                excerpt = c.get("excerpt") or (text[:400] if text else src.get("snippet") or "")
                claim = c.get("claim") or excerpt[:240]
                vec = embed_text(claim + " " + excerpt, dim)
                eid = self.store.add_evidence(session_id, source_id, claim, excerpt[:800], vec)
                evidence.append(
                    {
                        "id": eid,
                        "source_id": source_id,
                        "claim": claim,
                        "excerpt": excerpt[:800],
                        "title": src.get("title"),
                        "url": url,
                    }
                )
        await self.event("complete", message=f"Fetched {fetched} documents, stored {len(evidence)} evidence items.")
        return evidence

    async def _claims(self, src: dict, text: str) -> list[dict]:
        snippet = (text or src.get("snippet") or "")[:2500]
        fallback = [{"claim": (src.get("snippet") or src.get("title") or "")[:280], "excerpt": snippet[:500]}]
        parsed = await llm_json(
            self.llm,
            system="Extract 2-4 research claims as JSON: {\"claims\":[{\"claim\":\"...\",\"excerpt\":\"...\"}]}",
            user=f"Title: {src.get('title')}\nURL: {src.get('url')}\nText:\n{snippet}",
            fallback={"claims": fallback},
        )
        claims = parsed.get("claims") if isinstance(parsed, dict) else None
        if not claims:
            return fallback
        return claims[:4]
