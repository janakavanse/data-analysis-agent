# Architecture

## System Overview

The Data Analyst Agent is a single-server web application. The browser client sends REST requests to a FastAPI server, which runs a LangGraph agent that uses pandas to analyze uploaded CSV data and calls Google Gemini to interpret natural-language questions and format answers. Session metadata and dataset metadata are persisted in SQLite. Uploaded CSV files are stored on the local filesystem under `data/uploads/`. No data is forwarded to external services beyond the Gemini API call, which receives only column schema and aggregated statistics — never raw rows.

## Component Map

```
Browser (Next.js static export, served at /app)
        │
        │  REST — JSON + multipart/form-data
        ▼
FastAPI  (port 8001)
  ├── POST /sessions
  ├── POST /sessions/{session_id}/datasets     ← multipart CSV upload
  ├── GET  /sessions/{session_id}/datasets
  ├── POST /sessions/{session_id}/queries      ← NL question → answer
  └── GET  /health
        │
        ▼
LangGraph Agent (sync StateGraph, compiled once at startup)
  load_dataset
      → analyze_query  (Gemini call: schema + stats + question → answer text + table spec)
      → extract_table  (parse table spec from answer into list-of-dicts)
      → [generate_chart]  (Phase 2 only: matplotlib PNG → base64)
      → finalize
      ↘ handle_error   (on any exception in any node)
        │
        ├── pandas   (CSV ingestion, DataFrame analytics, schema/summary extraction)
        ├── Gemini   (NL question → structured text answer)
        └── matplotlib  (Phase 2: chart rendering)
        │
SQLite (via SQLAlchemy, sync)
  ├── sessions  — session lifecycle
  ├── datasets  — file metadata only (path, columns, row count)
  └── runs      — one record per query; stores answer + table JSON

Filesystem: data/uploads/<session_id>/<dataset_id>_<filename>
```

## Layers

| Layer | Responsibility |
|-------|----------------|
| API (`src/api/`) | HTTP surface — request validation, response serialization, route wiring |
| Domain (`src/domain/`) | Pydantic request/response types; one file per domain concept |
| Graph (`src/graph/`) | LangGraph state machine; pure-function nodes; edges; runner |
| LLM (`src/llm/`) | Provider abstraction; auto-detects Gemini from env key |
| DB (`src/db/`) | SQLAlchemy ORM models, session factory, Alembic migrations |
| Config (`src/config/`) | Pydantic-settings `Settings`; `extra="ignore"`; AGENT_ prefix |
| Frontend (`frontend/`) | Next.js 15 static export; chat UI; file upload; table/chart rendering |

## Data Flow

1. **Session creation:** Browser auto-calls `POST /sessions` on page load → server creates a `SessionRow`, returns `session_id`.
2. **CSV upload:** User drops a CSV onto the dropzone → browser calls `POST /sessions/{session_id}/datasets` with `multipart/form-data` → FastAPI writes the file to `data/uploads/<session_id>/`, reads it with pandas, extracts column names and row count, persists a `DatasetRow`, returns dataset metadata.
3. **NL query:** User types a question → browser calls `POST /sessions/{session_id}/queries` with `{question, dataset_id}` → FastAPI calls `run_agent(session_id, dataset_id, question)` → LangGraph graph executes: `load_dataset` loads the CSV into a DataFrame; `analyze_query` sends column schema + `.describe()` + `head(5)` + question to Gemini; `extract_table` parses a markdown/JSON table from the answer text into `table_data`; `finalize` persists a `RunRow`; runner returns `{answer_text, table_data, chart_b64}` → API returns the result to the browser.
4. **Output:** Browser renders the assistant message bubble with text, an HTML table (if `table_data` present), and (Phase 2) an inline PNG chart.

## External Dependencies

| Dependency | Purpose | Failure Mode |
|------------|---------|--------------|
| Google Gemini API (`AGENT_GEMINI_API_KEY`) | Natural-language question interpretation, answer generation | Returns HTTP error → graph routes to `handle_error` → API returns 422 with error message; displayed in chat |
| Local filesystem (`data/uploads/`) | CSV file storage | Write failure → upload endpoint returns 500; user sees error message |
| SQLite (`AGENT_DATABASE_URL`) | Session + dataset + run metadata | DB error at startup → process exits with a startup validation failure |

---

## Stack

> This project's concrete technology choices (captured at intake). Generic rules — model-naming, DB driver, dev port, test environment — live in `harness/patterns/tech-stack.md`.

- **Language:** Python 3.11+
- **Agent framework:** LangGraph (sync `StateGraph`); compiled once at module load
- **LLM provider + model:** Google Gemini via `google-genai` SDK; default model `gemini-2.5-flash`; env-configurable via `AGENT_LLM_MODEL`; key `AGENT_GEMINI_API_KEY`
- **Backend:** FastAPI
- **Database + ORM:** SQLite + SQLAlchemy (sync) + Alembic
- **Frontend:** Next.js 15 + React 19 + Tailwind v4
- **Dependency management:** uv (Python) + pnpm (frontend)

| Key library | Purpose |
|-------------|---------|
| `google-genai` | Official Google GenAI SDK — already wired in `src/llm/providers/gemini.py` |
| `pandas` | CSV ingestion, DataFrame analytics, schema/stat extraction |
| `numpy` | Numeric support for pandas |
| `matplotlib` | Chart rendering as base64 PNG (Phase 2) |
| `langgraph` | Agent graph orchestration |
| `sqlalchemy` | ORM and connection management |
| `alembic` | Schema migrations |
| `pydantic` / `pydantic-settings` | Domain types, config; `extra="ignore"` on Settings |
| `python-multipart` | FastAPI multipart file upload support |

**Avoid:**
- `langchain-google-genai` — the project uses `google-genai` directly; do not introduce a second Gemini SDK.
- `aiosqlite` / async SQLAlchemy — the existing skeleton is sync-only; do not introduce async DB.
- Raw `dict` at module boundaries — all boundaries use Pydantic models or typed `TypedDict`.
- Storing raw CSV rows in the database — only metadata goes into SQLite.

## Deployment Model

Single-process local server. `uv run python -m src` starts FastAPI on port 8001. The Next.js static export is pre-built (`cd frontend && pnpm build`) and served at `/app` by FastAPI's `StaticFiles` mount. No Docker, no cloud deployment in scope for Phases 1–3.

> **Assumed:** SQLite is appropriate (single-process server, no concurrency, metadata-only storage) — consistent with the brief and the existing `AGENT_DATABASE_URL` default.

> **Assumed:** `google-genai` is used directly (not `langchain-google-genai`), matching the existing `GeminiProvider` implementation.

> **Assumed:** Only schema + `.describe()` + `head(5)` of each DataFrame is sent to Gemini; no raw rows leave the server.

> **Assumed:** Uploaded files persist for the lifetime of the server process; no scheduled cleanup in Phases 1–3.
