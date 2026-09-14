from __future__ import annotations

import json
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException

from app.db.store import Store
from app.deps import get_store

router = APIRouter(prefix="/api/public", tags=["public"])


@router.get("/sessions/{token}")
def get_public_session(token: str, store: Annotated[Store, Depends(get_store)]):
    sess = store.get_session_by_share_token(token)
    if not sess:
        raise HTTPException(404, "Shared session not found or link has expired")

    session_id = sess["id"]
    report = store.get_report(session_id)
    sources = store.list_sources(session_id)
    evidence = [{k: v for k, v in e.items() if k != "embedding"} for e in store.list_evidence(session_id)]
    events = store.list_events(session_id)
    citation_edges = store.list_citation_edges(session_id)

    # Extract critic findings if present
    critic = None
    with store.connect() as conn:
        row = conn.execute("SELECT payload_json FROM findings WHERE session_id = ? AND kind = 'critic' ORDER BY rowid DESC LIMIT 1", (session_id,)).fetchone()
        if row and row["payload_json"]:
            try:
                critic = json.loads(row["payload_json"])
            except Exception:
                pass

    return {
        "session": sess,
        "sources": sources,
        "evidence": evidence,
        "report": report,
        "events": events,
        "citation_edges": citation_edges,
        "critic": critic,
    }
