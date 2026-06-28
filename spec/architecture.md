# Architecture

A local-first conversational data-analysis agent. A single user uploads a CSV/Excel file into a local web app and asks plain-English questions about it. The defining constraint is **privacy**: the dataset never leaves the machine. The LLM only ever sees the schema (column names + dtypes), a tiny sample (default 5 rows), the question, and prior chat turns — it writes pandas code; the code executes **locally** over the real DataFrame; results and (later) charts are produced locally.

---

## System Overview

One user, one browser tab, one local Python process. The browser talks to a FastAPI server on `:8001` (UI served from the same origin at `/app`). The server holds uploaded DataFrames in-process, runs a LangGraph analysis loop per question, calls Gemini only with privacy-safe context, executes the LLM-written pandas locally in a restricted sandbox, and persists chat/session/dataset metadata to SQLite.

## Component Map

```
Browser (Next.js static export at /app)
    │  upload CSV / ask question / load history
    ▼
FastAPI (src/api)  ──────────────►  Gemini API (schema + sample + question only)
    │                                        ▲
    │ load DataFrame                         │ writes pandas code
    ▼                                        │
DataFrame Store (in-process, src/analysis)   │
    │                                        │
    ▼                                        │
LangGraph analysis loop (src/graph) ─────────┘
    │  executes LLM-written pandas LOCALLY (restricted sandbox)
    ▼
SQLite (src/db)  ← sessions, messages (answer + code + result), dataset metadata (schema/sample only)
```

## Layers

| Layer | Responsibility |
|-------|----------------|
| UI (`frontend/`) | Drag/drop upload, chat transcript, collapsible "show the work" (code + result table), labelled stubs for later features |
| API (`src/api`) | Upload, ask, session-history endpoints; request validation; maps to the runner |
| DataFrame store (`src/analysis/store.py`) | Loads uploaded files into pandas; keeps the active DataFrame in-process keyed by `session_id`; derives schema + sample |
| Analysis loop (`src/graph`) | LangGraph graph: schema/sample → LLM plans pandas → local exec → format answer-with-work → finalize |
| Sandbox (`src/analysis/sandbox.py`) | Runs LLM-written pandas with restricted builtins, no imports/IO, wall-clock timeout; returns a result variable |
| LLM (`src/llm`) | Existing `LLMClient` → Gemini provider (`call_model`) |
| Storage (`src/db`) | SQLite via SQLAlchemy; sessions, messages, dataset metadata (schema + sample, never full rows) |

## Data Flow

1. **Trigger:** user drops a CSV into the web app → `POST /datasets`.
2. Server saves bytes under `data/uploads/`, loads with `pandas.read_csv`, derives schema + sample + row_count, creates a `Session` + `Dataset` row, keeps the DataFrame in the in-process store keyed by `session_id`.
3. User types a question → `POST /sessions/{id}/ask`.
4. Runner loads the DataFrame from the store, fetches prior turns, invokes the LangGraph loop.
5. **extract_schema** node reads schema + sample (privacy-safe) from the DataFrame.
6. **plan_analysis** node calls Gemini with schema + sample + question + prior turns → receives a pandas snippet.
7. **execute_analysis** node runs the snippet locally in the sandbox over the real DataFrame → result table/scalar; one auto-repair retry on error.
8. **format_answer** node composes the natural-language answer and attaches the code + result (show the work).
9. **finalize** node persists the user + assistant messages.
10. **Output:** answer + code + result table streamed back to the chat; persisted for replay.

## External Dependencies

| Dependency | Purpose | Failure Mode |
|------------|---------|--------------|
| Gemini API | Writes the pandas code from privacy-safe context | Surface a readable chat error; one repair retry on bad code; no successful answer persisted |
| Local filesystem | Store uploaded files under `data/uploads/`; SQLite DB file | 400 on unreadable upload; standard DB errors surfaced as 500 |

## Stack

> Concrete choices for this project. Generic rules (model-naming, DB driver, dev port, real-key tests) live in `harness/patterns/tech-stack.md`.

- **Language:** Python 3.12+
- **Agent framework:** LangGraph (extends the repo baseline `src/graph/`)
- **LLM provider + model:** Gemini, default **`gemini-2.5-flash`** (cheap + capable; chosen for the cost-conscious constraint over `gemini-2.5-pro`). Overridable via `AGENT_LLM_MODEL`. Key: `AGENT_GEMINI_API_KEY`. Provider auto-detects from the set key. **Phase-1 action:** change `GeminiProvider.DEFAULT_MODEL` in `src/llm/providers/gemini.py` from `gemini-2.5-pro` to `gemini-2.5-flash` so the cheap model is the default when `AGENT_LLM_MODEL` is unset.
- **Backend:** FastAPI (existing `src/api`), served on `:8001`, UI mounted at `/app`
- **Database + ORM:** SQLite (`sqlite:///./data/agent.db`) + SQLAlchemy 2.0; migrations via Alembic. SQLite is correct here — local-first, single user.
- **Frontend:** Next.js 15 + React 19 (static export) + Tailwind, served single-origin at `/app`
- **Dependency management:** uv + pyproject.toml (Python); pnpm (frontend)

| Key library | Version | Purpose |
|-------------|---------|---------|
| pandas | latest 2.x | ALL local data analysis (load, compute) |
| openpyxl | latest | Excel (`.xlsx`) reading — added in Phase 4 |
| langgraph | (baseline) | analysis loop orchestration |
| google-genai | (baseline) | Gemini provider |
| matplotlib | latest | server-side chart rendering to PNG — added in Phase 2 |

> **Assumed:** the privacy sandbox is implemented as a restricted `exec` with a curated globals dict (`df`, `pd` only), `__builtins__` reduced to a safe allow-list, no `import`/dunder/file/network access, and a wall-clock timeout — rather than pulling in a heavyweight sandboxing dependency, which is overkill for a single-user local tool.

> **Assumed:** the active DataFrame lives in an in-process dict keyed by `session_id` (single-user, single-process). On server restart the DataFrame is re-loaded lazily from the saved upload file on the next question, using the persisted file path — so history survives a restart.

**Avoid:** sending any full-dataset or raw row-level data (beyond the N-row sample) to the LLM — this violates the core privacy constraint. A hardcoded op-list interpreter (anti-pattern per `agentic-ai.md` #22) — always generate executable pandas. Switching the DB off SQLite — local-first single-user is the design point.

## Deployment Model

A long-running local process started with `uv run python -m src` from the repo root. Serves the API and (when `frontend/out/` exists) the UI at `http://localhost:8001/app/`. No cloud, no multi-tenant concerns.
