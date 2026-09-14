from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.db.store import Store
from app.deps import get_current_user, get_store
from app.tools.academic import search_openalex

router = APIRouter(prefix="/api/monitors", tags=["monitors"])


class MonitorIn(BaseModel):
    topic: str = Field(min_length=2)
    frequency: str = "daily"


async def fetch_recent_papers(topic: str) -> list[dict]:
    """Fetch the latest papers from OpenAlex for a given monitoring topic."""
    raw = await search_openalex(topic, per_page=10)
    current_year = datetime.now(timezone.utc).year
    # Sort by publication year descending
    papers = []
    for r in raw:
        y = r.get("year") or 0
        papers.append({
            "title": r.get("title") or "Untitled Paper",
            "url": r.get("url") or "",
            "venue": r.get("venue") or "",
            "year": y,
            "cited_by": r.get("cited_by") or 0,
            "doi": r.get("doi") or "",
            "snippet": (r.get("snippet") or "")[:350],
            "authors": r.get("authors") or [],
            "is_recent": (y >= current_year - 1),
        })
    papers.sort(key=lambda p: (p["year"], p["cited_by"]), reverse=True)
    return papers[:8]


@router.get("")
def list_monitors(user: Annotated[dict, Depends(get_current_user)], store: Annotated[Store, Depends(get_store)]):
    return store.list_paper_monitors(user["id"])


@router.post("")
async def create_monitor(
    body: MonitorIn,
    user: Annotated[dict, Depends(get_current_user)],
    store: Annotated[Store, Depends(get_store)],
):
    rec = store.create_paper_monitor(user["id"], body.topic, body.frequency)
    # Check initial papers
    try:
        papers = await fetch_recent_papers(body.topic)
        now = datetime.now(timezone.utc).isoformat()
        store.update_paper_monitor(rec["id"], last_checked=now, new_papers=papers)
        rec["last_checked"] = now
        rec["new_papers"] = papers
    except Exception:
        pass
    return rec


@router.post("/{monitor_id}/check")
async def check_monitor(
    monitor_id: str,
    user: Annotated[dict, Depends(get_current_user)],
    store: Annotated[Store, Depends(get_store)],
):
    mon = store.get_paper_monitor(monitor_id)
    if not mon or mon["user_id"] != user["id"]:
        raise HTTPException(404, "Paper monitor not found")

    papers = await fetch_recent_papers(mon["topic"])
    now = datetime.now(timezone.utc).isoformat()
    store.update_paper_monitor(monitor_id, last_checked=now, new_papers=papers)
    mon["last_checked"] = now
    mon["new_papers"] = papers
    return mon


@router.delete("/{monitor_id}")
def delete_monitor(
    monitor_id: str,
    user: Annotated[dict, Depends(get_current_user)],
    store: Annotated[Store, Depends(get_store)],
):
    mon = store.get_paper_monitor(monitor_id)
    if not mon or mon["user_id"] != user["id"]:
        raise HTTPException(404, "Paper monitor not found")
    store.delete_paper_monitor(monitor_id)
    return {"ok": True}
