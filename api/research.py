from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from app.agents.orchestrator import Orchestrator
from app.db.store import Store
from app.deps import get_current_user, get_llm, get_store
from app.embeddings.local import chunk_text, embed_text
from app.rag.qa import rag_answer
from app.tools.audio import generate_audio_file
from app.tools.crawler import crawl_research_site
from app.tools.export import generate_bibtex, generate_markdown, generate_pdf
from app.tools.pdf import extract_pdf_bytes

router = APIRouter(prefix="/api", tags=["research"])


class ProjectIn(BaseModel):
    title: str = Field(min_length=2)
    query: str = Field(min_length=3)


class SessionIn(BaseModel):
    project_id: str | None = None
    query: str = Field(min_length=3)
    title: str | None = None


class ChatIn(BaseModel):
    message: str = Field(min_length=1)


class PrefIn(BaseModel):
    voice_enabled: bool = True
    llm_preference: str = "auto"


class AudioIn(BaseModel):
    voice: str = "en-US-ChristopherNeural"
    mode: str = "solo"


class CrawlIn(BaseModel):
    url: str = Field(min_length=5)
    max_pages: int = 6


@router.get("/health")
def health(store: Annotated[Store, Depends(get_store)]):
    llm = get_llm()
    return {
        "ok": True,
        "llm": llm.name,
        "supabase": bool(store.supabase),
        "app": "ResearchMind",
    }


@router.get("/me")
def me(user: Annotated[dict, Depends(get_current_user)], store: Annotated[Store, Depends(get_store)]):
    return {"user": user, "preferences": store.get_preferences(user["id"])}


@router.put("/me/preferences")
def prefs(body: PrefIn, user: Annotated[dict, Depends(get_current_user)], store: Annotated[Store, Depends(get_store)]):
    store.set_preferences(user["id"], body.voice_enabled, body.llm_preference)
    return store.get_preferences(user["id"])


@router.get("/projects")
def projects(user: Annotated[dict, Depends(get_current_user)], store: Annotated[Store, Depends(get_store)]):
    return store.list_projects(user["id"])


@router.post("/projects")
def create_project(body: ProjectIn, user: Annotated[dict, Depends(get_current_user)], store: Annotated[Store, Depends(get_store)]):
    return store.create_project(user["id"], body.title, body.query)


@router.get("/sessions")
def sessions(user: Annotated[dict, Depends(get_current_user)], store: Annotated[Store, Depends(get_store)]):
    return store.list_sessions(user["id"])


@router.get("/sessions/{session_id}")
def get_session(session_id: str, user: Annotated[dict, Depends(get_current_user)], store: Annotated[Store, Depends(get_store)]):
    sess = store.get_session(session_id)
    if not sess or sess["user_id"] != user["id"]:
        raise HTTPException(404, "Session not found")
    report = store.get_report(session_id)
    citation_edges = store.list_citation_edges(session_id)

    # Check for critic review in findings
    critic = None
    with store.connect() as conn:
        row = conn.execute(
            "SELECT payload_json FROM findings WHERE session_id = ? AND kind = 'critic' ORDER BY rowid DESC LIMIT 1",
            (session_id,),
        ).fetchone()
        if row and row["payload_json"]:
            try:
                critic = json.loads(row["payload_json"])
            except Exception:
                pass

    # Check if neural audio exists on disk
    audio_path = _audio_path(store, session_id)
    has_audio = audio_path.exists()

    return {
        "session": sess,
        "sources": store.list_sources(session_id),
        "evidence": [{k: v for k, v in e.items() if k != "embedding"} for e in store.list_evidence(session_id)],
        "report": report,
        "chat": store.list_chat(session_id),
        "events": store.list_events(session_id),
        "citation_edges": citation_edges,
        "critic": critic,
        "has_audio": has_audio,
    }



@router.post("/research")
async def start_research(
    body: SessionIn,
    user: Annotated[dict, Depends(get_current_user)],
    store: Annotated[Store, Depends(get_store)],
):
    title = body.title or body.query[:80]
    project_id = body.project_id
    if not project_id:
        project_id = store.create_project(user["id"], title, body.query)["id"]
    else:
        project = store.get_project(project_id)
        if not project or project["user_id"] != user["id"]:
            raise HTTPException(404, "Project not found")
    sess = store.create_session(project_id, user["id"], body.query)
    _start_research_task(sess["id"], sess["query"], store)
    return {"session_id": sess["id"], "project_id": project_id}


_bus: dict[str, list[asyncio.Queue]] = {}
_tasks: dict[str, asyncio.Task] = {}


def _audio_path(store: Store, session_id: str) -> Path:
    return Path(store.settings.sqlite_path).parent / "audio" / f"{session_id}.mp3"


def _start_research_task(session_id: str, query: str, store: Store) -> None:
    if session_id in _tasks and not _tasks[session_id].done():
        return

    async def emit(event: dict) -> None:
        try:
            persisted = store.add_event(session_id, event)
            event_to_send = {**event, "id": persisted.get("id")}
        except Exception:
            event_to_send = event
        for listener in list(_bus.get(session_id, [])):
            await listener.put(event_to_send)

    async def runner():
        try:
            orch = Orchestrator(get_llm(), store)
            await orch.run(session_id, query, emit)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            store.update_session(session_id, status="failed")
            await emit({"agent": "orchestrator", "kind": "error", "message": f"Error: {exc}"})
        finally:
            for listener in list(_bus.get(session_id, [])):
                await listener.put(None)
            _bus.pop(session_id, None)
            _tasks.pop(session_id, None)

    _tasks[session_id] = asyncio.create_task(runner())


@router.post("/research/{session_id}/restart")
async def restart_research(
    session_id: str,
    user: Annotated[dict, Depends(get_current_user)],
    store: Annotated[Store, Depends(get_store)],
):
    sess = store.get_session(session_id)
    if not sess or sess["user_id"] != user["id"]:
        raise HTTPException(404, "Session not found")
    # Cancel existing task if running
    existing = _tasks.get(session_id)
    if existing and not existing.done():
        existing.cancel()
    _tasks.pop(session_id, None)
    store.update_session(session_id, status="running")
    _start_research_task(session_id, sess["query"], store)
    return {"status": "restarted"}


@router.get("/research/{session_id}/stream")
async def stream_research(
    session_id: str,
    token: str,
    store: Annotated[Store, Depends(get_store)],
):
    from app.config import get_settings
    from app.security import decode_token

    payload = decode_token(token, get_settings())
    sess = store.get_session(session_id)
    if not payload or not sess or sess["user_id"] != payload["sub"]:
        raise HTTPException(401, "Unauthorized")

    past_events = store.list_events(session_id)

    if sess["status"] == "completed" or (sess["status"] == "failed" and session_id not in _tasks):
        async def past_only():
            for pe in past_events:
                yield _sse(pe)
            final_kind = "complete" if sess["status"] == "completed" else "error"
            yield _sse({"agent": "orchestrator", "kind": final_kind, "message": f"Session {sess['status']}."})

        return StreamingResponse(
            past_only(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    queue: asyncio.Queue[dict | None] = asyncio.Queue()
    _bus.setdefault(session_id, []).append(queue)
    seen_ids = {e.get("id") for e in past_events if e.get("id")}

    if session_id not in _tasks:
        _start_research_task(session_id, sess["query"], store)

    async def gen():
        try:
            for pe in past_events:
                yield _sse(pe)
            while True:
                item = await queue.get()
                if item is None:
                    break
                if item.get("id") and item["id"] in seen_ids:
                    continue
                yield _sse(item)
        finally:
            listeners = _bus.get(session_id, [])
            if queue in listeners:
                listeners.remove(queue)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )



@router.post("/sessions/{session_id}/chat")
async def chat(
    session_id: str,
    body: ChatIn,
    user: Annotated[dict, Depends(get_current_user)],
    store: Annotated[Store, Depends(get_store)],
):
    sess = store.get_session(session_id)
    if not sess or sess["user_id"] != user["id"]:
        raise HTTPException(404, "Session not found")
    store.add_chat(session_id, user["id"], "user", body.message)
    answer = await rag_answer(get_llm(), store, session_id, body.message)
    rec = store.add_chat(session_id, user["id"], "assistant", answer)
    return rec


@router.post("/sessions/{session_id}/upload")
async def upload_pdf(
    session_id: str,
    user: Annotated[dict, Depends(get_current_user)],
    store: Annotated[Store, Depends(get_store)],
    file: UploadFile = File(...),
):
    sess = store.get_session(session_id)
    if not sess or sess["user_id"] != user["id"]:
        raise HTTPException(404, "Session not found")
    data = await file.read()
    try:
        text = extract_pdf_bytes(data, max_pages=20)
    except Exception as exc:
        raise HTTPException(400, f"Could not read PDF: {exc}") from exc
    src_id = store.add_source(
        session_id,
        {
            "title": file.filename,
            "url": f"upload://{file.filename}",
            "snippet": text[:500],
            "source_type": "upload",
            "score": 0.7,
        },
    )
    dim = store.settings.embedding_dim
    n = 0
    for chunk in chunk_text(text)[:30]:
        store.add_embedding(session_id, chunk, embed_text(chunk, dim), src_id)
        n += 1
    store.add_evidence(session_id, src_id, f"Uploaded PDF: {file.filename}", text[:800], embed_text(text[:1000], dim))
    return {"source_id": src_id, "chunks": n, "chars": len(text)}


@router.get("/sessions/{session_id}/export")
def export_session(
    session_id: str,
    user: Annotated[dict, Depends(get_current_user)],
    store: Annotated[Store, Depends(get_store)],
    format: str = Query("pdf", pattern="^(pdf|bibtex|markdown)$"),
):
    sess = store.get_session(session_id)
    if not sess or sess["user_id"] != user["id"]:
        raise HTTPException(404, "Session not found")

    report = store.get_report(session_id)
    sources = store.list_sources(session_id)
    clean_title = (sess.get("query", "report")[:30]).replace(" ", "_").lower()

    if format == "bibtex":
        content = generate_bibtex(sources)
        return Response(
            content=content,
            media_type="text/plain",
            headers={"Content-Disposition": f'attachment; filename="researchmind_{clean_title}.bib"'},
        )
    elif format == "markdown":
        content = generate_markdown(sess, report, sources)
        return Response(
            content=content,
            media_type="text/markdown",
            headers={"Content-Disposition": f'attachment; filename="researchmind_{clean_title}.md"'},
        )
    else:  # pdf
        pdf_bytes = generate_pdf(sess, report, sources)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="researchmind_{clean_title}.pdf"'},
        )


@router.post("/sessions/{session_id}/audio")
async def create_audio_briefing(
    session_id: str,
    body: AudioIn,
    user: Annotated[dict, Depends(get_current_user)],
    store: Annotated[Store, Depends(get_store)],
):
    sess = store.get_session(session_id)
    if not sess or sess["user_id"] != user["id"]:
        raise HTTPException(404, "Session not found")

    report = store.get_report(session_id)
    if not report or not report.get("voice_script"):
        raise HTTPException(400, "No voice script available for this session.")

    audio_path = _audio_path(store, session_id)
    audio_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        await generate_audio_file(report["voice_script"], str(audio_path), voice=body.voice, mode=body.mode)
    except Exception as exc:
        raise HTTPException(500, f"Neural audio generation failed: {exc}") from exc

    return {"ok": True, "audio_url": f"/api/sessions/{session_id}/audio"}


@router.get("/sessions/{session_id}/audio")
def get_audio_briefing(
    session_id: str,
    token: str,
    store: Annotated[Store, Depends(get_store)],
):
    from app.config import get_settings
    from app.security import decode_token

    payload = decode_token(token, get_settings())
    sess = store.get_session(session_id)
    if not payload or not sess or sess["user_id"] != payload["sub"]:
        raise HTTPException(401, "Unauthorized")

    audio_path = _audio_path(store, session_id)
    if not audio_path.exists():
        raise HTTPException(404, "Audio file not found. Generate it first.")
    return FileResponse(str(audio_path), media_type="audio/mpeg", filename=f"researchmind-{session_id[:8]}.mp3")


@router.post("/sessions/{session_id}/share")
def share_session(
    session_id: str,
    user: Annotated[dict, Depends(get_current_user)],
    store: Annotated[Store, Depends(get_store)],
):
    sess = store.get_session(session_id)
    if not sess or sess["user_id"] != user["id"]:
        raise HTTPException(404, "Session not found")

    token = store.create_or_get_share_token(session_id)
    return {"token": token, "share_url": f"/share/{token}"}


@router.post("/sessions/{session_id}/crawl")
async def crawl_site(
    session_id: str,
    body: CrawlIn,
    user: Annotated[dict, Depends(get_current_user)],
    store: Annotated[Store, Depends(get_store)],
):
    sess = store.get_session(session_id)
    if not sess or sess["user_id"] != user["id"]:
        raise HTTPException(404, "Session not found")

    discovered = await crawl_research_site(body.url, max_pages=body.max_pages)
    if not discovered:
        raise HTTPException(400, "No readable research articles or papers found at the provided URL.")

    dim = store.settings.embedding_dim
    added_sources = 0

    for s in discovered:
        src_id = store.add_source(session_id, s)
        added_sources += 1
        snippet = s.get("snippet", "")
        if len(snippet) > 50:
            store.add_embedding(session_id, snippet, embed_text(snippet, dim), src_id)
            store.add_evidence(session_id, src_id, f"Crawled from {s.get('venue')}", snippet[:800], embed_text(snippet[:1000], dim))

    # Also log an event to session timeline
    store.add_event(session_id, {
        "agent": "crawler",
        "title": "Research Crawler",
        "kind": "complete",
        "tool": "web_crawler",
        "message": f"Crawled {body.url} and ingested {added_sources} documents.",
    })

    return {"crawled_url": body.url, "sources_added": added_sources}


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"
