# ResearchMind

Autonomous **agentic** research assistant: a React + FastAPI lab that plans a topic, calls live web and academic tools, embeds evidence for RAG, then writes a cited report with a voice briefing.

This is not a single-prompt chatbot. The orchestrator runs separate agents. Each agent can emit `tool_call` / `tool_result` events that the UI shows in a live timeline.

## Architecture

```
User query
  → Research Planner
  → Web Research (DuckDuckGo) + Academic Research (OpenAlex / Semantic Scholar)
  → Source Discovery (rank / dedupe)
  → Document Extraction (fetch pages, local PDF, claims)
  → Verification
  → Analysis → Comparison → Gap detection → Contradiction detection
  → Synthesizer → Report generator → Voice script
  → RAG chat over session embeddings
```

- **Frontend:** React, Vite, TypeScript, Tailwind
- **Backend:** FastAPI
- **Default DB:** SQLite (₹0, works offline after install)
- **Optional DB:** Supabase (+ `pgvector` schema in `supabase/schema.sql`)
- **LLM:** `LLMProvider` switch via `LLM_PROVIDER` (`auto` | `groq` | `ollama` | `openai` | `none`)
- **Embeddings:** local hashing encoder (no model download)

## Zero-cost run

You can develop with no paid APIs:

1. SQLite storage
2. Free OpenAlex + DuckDuckGo search
3. `LLM_PROVIDER=none` (tools still run; writing is extractive) **or** free [Groq](https://console.groq.com) **or** local [Ollama](https://ollama.com)

`LLM_PROVIDER=auto` uses Groq if `GROQ_API_KEY` is set, otherwise OpenAI if that key is set, otherwise tool-only mode (`none`) so the pipeline never waits on a missing Ollama server. Set `LLM_PROVIDER=ollama` explicitly for local models.

## Setup

### Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
# Optional: set GROQ_API_KEY or run `ollama pull llama3.2`
uvicorn app.main:app --reload --app-dir .
```

From `backend/` the app package is `app`, so run:

```powershell
cd backend
.\.venv\Scripts\activate
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. Register a local account, start a research topic, watch agents and tool calls, then play **Voice explanation**.

### Optional Groq (free tier)

In `backend/.env`:

```
LLM_PROVIDER=groq
GROQ_API_KEY=gsk_...
GROQ_MODEL=llama-3.1-8b-instant
```

### Optional Ollama (fully local)

```
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2
```

### Optional Supabase

1. Create a free project
2. Run `supabase/schema.sql` in the SQL editor
3. Set `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` in `backend/.env`

The API still uses SQLite as the system of record and **mirrors** some rows to Supabase when those keys exist.

## API

- `POST /api/auth/register` `{ email, password }`
- `POST /api/research` `{ query }`
- `GET /api/research/{id}/stream?token=...` SSE agent events
- `POST /api/sessions/{id}/chat` RAG question
- `POST /api/sessions/{id}/upload` PDF → local extract + embed
- Docs: `http://127.0.0.1:8000/docs`

## Demo script (viva)

1. Register → New research → *Applications of Agentic AI in Smart Education*
2. Point at the timeline: planner JSON, `web_search`, `academic_search`, `fetch_url`
3. Open ranked sources (OpenAlex papers vs web pages)
4. Show gaps / contradictions sections in the report
5. Voice briefing (Web Speech API)
6. RAG chat: “What evaluation gaps remain?”
7. Upload a PDF and ask a question about it

## Project layout

```
backend/app/agents/   one module per agent + orchestrator
backend/app/llm/      LLMProvider abstraction
backend/app/tools/     web, academic, fetch, pdf
backend/app/embeddings local vectors
frontend/src/pages     lab UI
supabase/schema.sql    optional cloud schema
```
