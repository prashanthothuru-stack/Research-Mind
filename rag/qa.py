from app.embeddings.local import embed_text
from app.llm.base import LLMProvider
from app.db.store import Store


async def rag_answer(llm: LLMProvider, store: Store, session_id: str, question: str) -> str:
    dim = store.settings.embedding_dim
    qvec = embed_text(question, dim)
    chunks = store.search_chunks(session_id, qvec, k=8)
    evidence = store.list_evidence(session_id)
    ctx_chunks = "\n\n".join(c["chunk_text"] for c in chunks)
    ctx_claims = "\n".join(f"- {e['claim']}" for e in evidence[:12])
    report = store.get_report(session_id)
    report_clip = (report.get("markdown") if report else "")[:2500]
    system = (
        "Answer using only the retrieved research context. Cite titles or URLs when present. "
        "If the context is insufficient, say so."
    )
    user = (
        f"Question: {question}\n\nClaims:\n{ctx_claims}\n\nRetrieved passages:\n{ctx_chunks}\n\n"
        f"Report excerpt:\n{report_clip}"
    )
    if llm.name == "none":
        if chunks:
            return "Retrieved context:\n\n" + "\n\n".join(c["chunk_text"][:400] for c in chunks[:3])
        return "No indexed passages yet. Run a research session first."
    try:
        return await llm.complete(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.2,
            max_tokens=900,
        )
    except Exception as exc:
        return f"RAG generation failed ({exc}). Top passage:\n{chunks[0]['chunk_text'] if chunks else 'none'}"
