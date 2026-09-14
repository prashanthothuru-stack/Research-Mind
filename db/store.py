from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import Settings


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uid() -> str:
    return str(uuid.uuid4())


class Store:
    """SQLite persistence. When Supabase env is set, rows are also mirrored."""

    def __init__(self, settings: Settings):
        self.settings = settings
        Path(settings.sqlite_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_sqlite()
        self.supabase = None
        if settings.supabase_url and settings.supabase_service_role_key:
            try:
                from supabase import create_client

                self.supabase = create_client(
                    settings.supabase_url, settings.supabase_service_role_key
                )
            except Exception:
                self.supabase = None

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.settings.sqlite_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_sqlite(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS user_preferences (
                    user_id TEXT PRIMARY KEY,
                    voice_enabled INTEGER DEFAULT 1,
                    llm_preference TEXT DEFAULT 'auto',
                    extra_json TEXT DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    query TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    query TEXT NOT NULL,
                    status TEXT NOT NULL,
                    plan_json TEXT,
                    result_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sources (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    title TEXT,
                    url TEXT,
                    source_type TEXT,
                    snippet TEXT,
                    meta_json TEXT,
                    score REAL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS evidence (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    source_id TEXT,
                    claim TEXT,
                    excerpt TEXT,
                    embedding_json TEXT
                );
                CREATE TABLE IF NOT EXISTS findings (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    kind TEXT,
                    payload_json TEXT
                );
                CREATE TABLE IF NOT EXISTS reports (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    markdown TEXT,
                    voice_script TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS embeddings (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    chunk_text TEXT,
                    embedding_json TEXT,
                    source_id TEXT
                );
                CREATE TABLE IF NOT EXISTS session_events (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    agent TEXT NOT NULL,
                    title TEXT,
                    kind TEXT NOT NULL,
                    message TEXT,
                    tool TEXT,
                    data_json TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS paper_monitors (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    frequency TEXT DEFAULT 'daily',
                    last_checked TEXT,
                    new_papers_json TEXT DEFAULT '[]',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS session_shares (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL UNIQUE,
                    token TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    view_count INTEGER DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS citation_edges (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    source_paper_title TEXT NOT NULL,
                    target_paper_title TEXT NOT NULL,
                    target_doi TEXT,
                    target_url TEXT,
                    relation TEXT DEFAULT 'cites',
                    created_at TEXT NOT NULL
                );
                """
            )

    def create_user(self, email: str, password_hash: str) -> dict:
        user_id = _uid()
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO users (id, email, password_hash, created_at) VALUES (?,?,?,?)",
                (user_id, email.lower().strip(), password_hash, _now()),
            )
            conn.execute(
                "INSERT INTO user_preferences (user_id) VALUES (?)",
                (user_id,),
            )
        row = {"id": user_id, "email": email.lower().strip()}
        self._sb_upsert("profiles", {"id": user_id, "email": row["email"]})
        return row

    def get_user_by_email(self, email: str) -> dict | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE email = ?", (email.lower().strip(),)
            ).fetchone()
        return dict(row) if row else None

    def get_user(self, user_id: str) -> dict | None:
        with self.connect() as conn:
            row = conn.execute("SELECT id, email, created_at FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None

    def create_project(self, user_id: str, title: str, query: str) -> dict:
        pid = _uid()
        rec = {"id": pid, "user_id": user_id, "title": title, "query": query, "created_at": _now()}
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO projects (id, user_id, title, query, created_at) VALUES (?,?,?,?,?)",
                (pid, user_id, title, query, rec["created_at"]),
            )
        self._sb_upsert("projects", rec)
        return rec

    def list_projects(self, user_id: str) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM projects WHERE user_id = ? ORDER BY created_at DESC",
                (user_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_project(self, project_id: str) -> dict | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        return dict(row) if row else None

    def create_session(self, project_id: str, user_id: str, query: str) -> dict:
        sid = _uid()
        now = _now()
        rec = {
            "id": sid,
            "project_id": project_id,
            "user_id": user_id,
            "query": query,
            "status": "running",
            "plan_json": None,
            "result_json": None,
            "created_at": now,
            "updated_at": now,
        }
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO sessions (id, project_id, user_id, query, status, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (sid, project_id, user_id, query, "running", now, now),
            )
        self._sb_upsert(
            "research_sessions",
            {k: v for k, v in rec.items() if k not in {"plan_json", "result_json"}},
        )
        return rec

    def update_session(self, session_id: str, **fields: Any) -> None:
        fields["updated_at"] = _now()
        keys = list(fields.keys())
        with self.connect() as conn:
            conn.execute(
                f"UPDATE sessions SET {', '.join(k + '=?' for k in keys)} WHERE id = ?",
                [*[fields[k] for k in keys], session_id],
            )

    def get_session(self, session_id: str) -> dict | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if not row:
            return None
        data = dict(row)
        for k in ("plan_json", "result_json"):
            if data.get(k):
                try:
                    data[k] = json.loads(data[k])
                except json.JSONDecodeError:
                    pass
        return data

    def list_sessions(self, user_id: str) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                """SELECT s.*, p.title as project_title FROM sessions s
                   JOIN projects p ON p.id = s.project_id
                   WHERE s.user_id = ? ORDER BY s.created_at DESC""",
                (user_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def add_source(self, session_id: str, source: dict) -> str:
        sid = _uid()
        meta = {k: v for k, v in source.items() if k not in {"title", "url", "snippet", "source_type", "score"}}
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO sources (id, session_id, title, url, source_type, snippet, meta_json, score)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (
                    sid,
                    session_id,
                    source.get("title"),
                    source.get("url"),
                    source.get("source_type"),
                    source.get("snippet"),
                    json.dumps(meta),
                    float(source.get("score") or 0),
                ),
            )
        return sid

    def list_sources(self, session_id: str) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM sources WHERE session_id = ? ORDER BY score DESC",
                (session_id,),
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["meta"] = json.loads(d.pop("meta_json") or "{}")
            out.append(d)
        return out

    def add_evidence(self, session_id: str, source_id: str | None, claim: str, excerpt: str, embedding: list[float]) -> str:
        eid = _uid()
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO evidence (id, session_id, source_id, claim, excerpt, embedding_json)
                   VALUES (?,?,?,?,?,?)""",
                (eid, session_id, source_id, claim, excerpt, json.dumps(embedding)),
            )
        return eid

    def list_evidence(self, session_id: str) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM evidence WHERE session_id = ?", (session_id,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["embedding"] = json.loads(d.pop("embedding_json") or "[]")
            out.append(d)
        return out

    def add_finding(self, session_id: str, kind: str, payload: dict) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO findings (id, session_id, kind, payload_json) VALUES (?,?,?,?)",
                (_uid(), session_id, kind, json.dumps(payload)),
            )

    def add_report(self, session_id: str, markdown: str, voice_script: str) -> str:
        rid = _uid()
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO reports (id, session_id, markdown, voice_script, created_at) VALUES (?,?,?,?,?)",
                (rid, session_id, markdown, voice_script, _now()),
            )
        return rid

    def get_report(self, session_id: str) -> dict | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM reports WHERE session_id = ? ORDER BY created_at DESC LIMIT 1",
                (session_id,),
            ).fetchone()
        return dict(row) if row else None

    def add_embedding(self, session_id: str, chunk: str, embedding: list[float], source_id: str | None) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO embeddings (id, session_id, chunk_text, embedding_json, source_id) VALUES (?,?,?,?,?)",
                (_uid(), session_id, chunk, json.dumps(embedding), source_id),
            )

    def search_chunks(self, session_id: str, query_vec: list[float], k: int = 8) -> list[dict]:
        from app.embeddings.local import cosine

        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM embeddings WHERE session_id = ?", (session_id,)
            ).fetchall()
        scored = []
        for r in rows:
            vec = json.loads(r["embedding_json"] or "[]")
            scored.append(
                {
                    "chunk_text": r["chunk_text"],
                    "source_id": r["source_id"],
                    "score": cosine(query_vec, vec),
                }
            )
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:k]

    def add_chat(self, session_id: str, user_id: str, role: str, content: str) -> dict:
        rec = {
            "id": _uid(),
            "session_id": session_id,
            "user_id": user_id,
            "role": role,
            "content": content,
            "created_at": _now(),
        }
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO chat_messages (id, session_id, user_id, role, content, created_at) VALUES (?,?,?,?,?,?)",
                (rec["id"], session_id, user_id, role, content, rec["created_at"]),
            )
        return rec

    def list_chat(self, session_id: str) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM chat_messages WHERE session_id = ? ORDER BY created_at ASC",
                (session_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_preferences(self, user_id: str) -> dict:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM user_preferences WHERE user_id = ?", (user_id,)
            ).fetchone()
        if not row:
            return {"voice_enabled": True, "llm_preference": "auto"}
        d = dict(row)
        d["voice_enabled"] = bool(d.get("voice_enabled"))
        return d

    def set_preferences(self, user_id: str, voice_enabled: bool, llm_preference: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO user_preferences (user_id, voice_enabled, llm_preference)
                   VALUES (?,?,?)
                   ON CONFLICT(user_id) DO UPDATE SET voice_enabled=excluded.voice_enabled,
                   llm_preference=excluded.llm_preference""",
                (user_id, 1 if voice_enabled else 0, llm_preference),
            )

    def add_event(self, session_id: str, event: dict) -> dict:
        eid = _uid()
        now = _now()
        data = event.get("data")
        data_json = json.dumps(data) if data is not None else None
        rec = {
            "id": eid,
            "session_id": session_id,
            "agent": event.get("agent", ""),
            "title": event.get("title") or event.get("agent", ""),
            "kind": event.get("kind", "info"),
            "message": event.get("message") or "",
            "tool": event.get("tool"),
            "data": data,
            "created_at": now,
        }
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO session_events (id, session_id, agent, title, kind, message, tool, data_json, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (
                    eid,
                    session_id,
                    rec["agent"],
                    rec["title"],
                    rec["kind"],
                    rec["message"],
                    rec["tool"],
                    data_json,
                    now,
                ),
            )
        return rec

    def list_events(self, session_id: str) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM session_events WHERE session_id = ? ORDER BY created_at ASC",
                (session_id,),
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            dj = d.pop("data_json", None)
            if dj:
                try:
                    d["data"] = json.loads(dj)
                except Exception:
                    d["data"] = None
            else:
                d["data"] = None
            out.append(d)
        return out

    # Paper Monitors
    def create_paper_monitor(self, user_id: str, topic: str, frequency: str = "daily") -> dict:
        mid = _uid()
        now = _now()
        rec = {
            "id": mid,
            "user_id": user_id,
            "topic": topic.strip(),
            "frequency": frequency,
            "last_checked": None,
            "new_papers": [],
            "created_at": now,
        }
        with self.connect() as conn:
            conn.execute(
                """INSERT INTO paper_monitors (id, user_id, topic, frequency, last_checked, new_papers_json, created_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (mid, user_id, rec["topic"], frequency, None, "[]", now),
            )
        return rec

    def list_paper_monitors(self, user_id: str) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM paper_monitors WHERE user_id = ? ORDER BY created_at DESC",
                (user_id,),
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["new_papers"] = json.loads(d.pop("new_papers_json") or "[]")
            out.append(d)
        return out

    def get_paper_monitor(self, monitor_id: str) -> dict | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM paper_monitors WHERE id = ?", (monitor_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["new_papers"] = json.loads(d.pop("new_papers_json") or "[]")
        return d

    def update_paper_monitor(self, monitor_id: str, **fields: Any) -> None:
        if "new_papers" in fields:
            fields["new_papers_json"] = json.dumps(fields.pop("new_papers"))
        keys = list(fields.keys())
        with self.connect() as conn:
            conn.execute(
                f"UPDATE paper_monitors SET {', '.join(k + '=?' for k in keys)} WHERE id = ?",
                [*[fields[k] for k in keys], monitor_id],
            )

    def delete_paper_monitor(self, monitor_id: str) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM paper_monitors WHERE id = ?", (monitor_id,))

    # Session Sharing (Public Read-Only)
    def create_or_get_share_token(self, session_id: str) -> str:
        with self.connect() as conn:
            row = conn.execute("SELECT token FROM session_shares WHERE session_id = ?", (session_id,)).fetchone()
            if row:
                return row["token"]
            token = uuid.uuid4().hex[:12]
            conn.execute(
                "INSERT INTO session_shares (id, session_id, token, created_at, view_count) VALUES (?,?,?,?,?)",
                (_uid(), session_id, token, _now(), 0),
            )
            return token

    def get_session_by_share_token(self, token: str) -> dict | None:
        with self.connect() as conn:
            row = conn.execute("SELECT session_id FROM session_shares WHERE token = ?", (token,)).fetchone()
            if not row:
                return None
            session_id = row["session_id"]
            conn.execute("UPDATE session_shares SET view_count = view_count + 1 WHERE token = ?", (token,))
            sess = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
            if not sess:
                return None
            d = dict(sess)
            for k in ("plan_json", "result_json"):
                if d.get(k):
                    try:
                        d[k] = json.loads(d[k])
                    except Exception:
                        pass
            return d

    # Citation Graph
    def add_citation_edges(self, session_id: str, edges: list[dict]) -> None:
        now = _now()
        with self.connect() as conn:
            for e in edges:
                conn.execute(
                    """INSERT INTO citation_edges (id, session_id, source_paper_title, target_paper_title, target_doi, target_url, relation, created_at)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (
                        _uid(),
                        session_id,
                        e.get("source_paper_title", ""),
                        e.get("target_paper_title", ""),
                        e.get("target_doi"),
                        e.get("target_url"),
                        e.get("relation", "cites"),
                        now,
                    ),
                )

    def list_citation_edges(self, session_id: str) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM citation_edges WHERE session_id = ? ORDER BY created_at ASC",
                (session_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def _sb_upsert(self, table: str, row: dict) -> None:
        if not self.supabase:
            return
        try:
            self.supabase.table(table).upsert(row).execute()
        except Exception:
            pass

