# Tech Stack

Per-build decisions for the data analysis agent. Locked harness constraints live in
`harness/harness.md`; this file records only the choices and their one-line rationale.
All versions were verified against PyPI (`pip index versions`) and the Google AI docs on 2026-06-20.

## Runtime LLM (the PRODUCT's model — separate from Claude Code, which builds this)

- **Provider:** `google_genai` — user's explicit choice.
- **Runtime model:** `gemini-2.5-pro` — user's explicit choice.
  - This is the frontier/capable tier (not the cheap default). Rationale: a data analysis agent
    performs multi-step SQL generation, schema inference, chart spec synthesis, and multi-turn
    reasoning over arbitrary uploaded datasets — these tasks plausibly need the capable tier.
    Cheap-tier default (`gemini-2.5-flash`) noted for reference; user pinned `gemini-2.5-pro`.
  - Model ID verified as the stable API string per [Google AI model docs](https://ai.google.dev/gemini-api/docs/models/gemini) (2026-06-20).
- **API key env var:** `APP_LLM_API_KEY` (pydantic-settings, prefix `APP_`; funded key injected via env / `.env`, never committed).
- **Provider package to pin:** `langchain-google-genai==4.2.5`
- **Harness reference:** `harness/patterns/model-and-providers.md`

### Example `.env` lines

```
APP_LLM_PROVIDER=google_genai
APP_LLM_MODEL=gemini-2.5-pro
APP_LLM_API_KEY=                    # funded key — inject via env or .env, never commit
APP_DATABASE_URL=sqlite+aiosqlite:///./agent.db
APP_PORT=8001
APP_MAX_ITERATIONS=6
```

## Persistence

Local-first by default; the same async code runs on both rungs — only the URL changes.
Reference: `harness/patterns/persistence.md`.

- **Local (dev / demo gate):** SQLite via `aiosqlite` — `sqlite+aiosqlite:///./agent.db`
- **Prod (PRODUCTIONISE / deploy gate):** PostgreSQL via `asyncpg` — `postgresql+asyncpg://user:pw@host/db`
- **ORM:** async SQLAlchemy 2.0. **NEVER `psycopg2`** (sync; breaks the event loop).
- **Core tables:** `runs`, `messages`, `spans` (non-negotiable; power observability + evals).

### Domain entities (agent/domain.py — same `Base`, same engine)

| Table | Purpose | Key columns |
|-------|---------|-------------|
| `datasets` | Registry of every uploaded file | `id` (str PK), `name` (str), `table_name` (str — the dynamic `ds_<uuid>` SQLite table), `schema_json` (JSON — column definitions inferred from file), `file_type` (str: `csv` or `json`), `row_count` (int), `session_id` (str, nullable — for multi-turn session affinity), `created_at` (datetime) |
| `ds_<uuid>` (dynamic) | One table per uploaded dataset; columns inferred at upload time | schema driven by file content; created via `CREATE TABLE` in-process at upload, not via SQLAlchemy ORM `Base` (dynamic DDL) |

Notes:
- `datasets` is a standard SQLAlchemy `Base` model; `init_db()` creates it automatically.
- Dynamic `ds_<uuid>` tables are created with raw async DDL at upload time (not in `Base.metadata`);
  they are referenced by `datasets.table_name` and queried by the agent's SQL tools.
- All `datasets` rows tie to a `session_id` (nullable) for multi-turn continuity; the `runs.thread_id`
  column links runs to sessions.

## Deploy target

- **Target:** TBD — chosen at PRODUCTIONISE (`/deploy`). Options: Railway, Fly.io, Modal.
- **Artifacts shipped every build:**
  - `langgraph.json` + `langgraph build` (managed path, native LangGraph ops).
  - Plain `Dockerfile` + `uvicorn` (portable path, custom routes including `/traces`, `/upload`, domain endpoints).
- **Prod ladder:** PostgreSQL (`asyncpg`) + Redis (Layer 11).
- **Harness reference:** `harness/patterns/deploy.md`

## Interface

- **Backend:** FastAPI on `:8001` (async, SSE streaming, file upload via `python-multipart`).
- **Frontend:** Next.js (App Router) + React + Tailwind CSS on `:3001`.
- **Harness reference:** `harness/patterns/interface.md`

## Key libraries — pinned current versions (verified 2026-06-20)

### Python / backend

| Concern | Library | Pinned version | Notes |
|---------|---------|---------------|-------|
| Web / SSE | `fastapi` | `0.137.2` | Async, SSE streaming |
| Web server | `uvicorn[standard]` | `0.49.0` | ASGI server |
| File upload | `python-multipart` | `0.0.32` | FastAPI multipart/form-data |
| Orchestration | `langgraph` | `1.2.6` | StateGraph + ReAct loop |
| LangChain core | `langchain` | `1.3.10` | `init_chat_model` dispatcher |
| LangChain core | `langchain-core` | `1.4.8` | `@tool`, base primitives |
| LLM provider | `langchain-google-genai` | `4.2.5` | Google Gemini via `init_chat_model` |
| Checkpointer | `langgraph-checkpoint-sqlite` | `3.1.0` | Short-term memory; SQLite-backed checkpointer for multi-turn |
| DB (local) | `sqlalchemy[asyncio]` | `2.0.51` | Async SQLAlchemy 2.0 ORM |
| DB (local driver) | `aiosqlite` | `0.22.1` | SQLite async driver |
| DB (prod driver) | `asyncpg` | `0.31.0` | Postgres async driver; added at PRODUCTIONISE; **never** `psycopg2` |
| Settings | `pydantic-settings` | `2.14.2` | Env prefix `APP_`; `.env` support |
| Data parsing | `pandas` | `3.0.3` | CSV/JSON ingestion and schema inference |
| Chart specs | `plotly` | `6.8.0` | Chart spec generation (server produces JSON; frontend renders) |
| Tests | `pytest` | `9.1.1` | Test runner |
| Tests async | `pytest-asyncio` | `1.1.0` | Async test support |
| Tests HTTP | `httpx` | `0.28.1` | Async HTTP client for FastAPI test client |

### Frontend (Node / npm — pin in `frontend/package.json`)

| Concern | Package | Notes |
|---------|---------|-------|
| Framework | `next` (App Router) | Server + client components, streaming |
| UI runtime | `react`, `react-dom` | React 19+ |
| Styling | `tailwindcss` | Utility-first CSS |
| Markdown | `react-markdown`, `remark-gfm` | Render agent text answers with GFM tables/code |
| Charts | `plotly.js-dist` | Client-side chart rendering from server-produced Plotly JSON specs |

Pin exact versions in `frontend/package.json` at build time via `npm install <pkg>@latest`.

## Tools classification (3-layer model — `harness/patterns/tools-and-mcp.md`)

All agent capabilities are owned, in-process, and cross no external trust boundary — therefore all tools
are **Layer 1 in-process `@tool`** functions in `agent/tools.py`. No MCP server is needed.

| Tool | Layer | Rationale |
|------|-------|-----------|
| `upload_dataset` | In-process `@tool` | Parses CSV/JSON (pandas), creates dynamic `ds_<uuid>` table, writes `datasets` row |
| `list_datasets` | In-process `@tool` | Reads `datasets` table; returns name → table_name index for the session |
| `run_sql` | In-process `@tool` | Executes a read-only SQL query against a `ds_<uuid>` table; returns row data |
| `generate_chart` | In-process `@tool` | Produces a Plotly JSON spec from query results; client renders inline |
| `describe_schema` | In-process `@tool` | Returns `schema_json` for a named dataset so the model knows column types |

MCP is not used — no external service boundary is crossed. If a future capability integrates a
third-party API (e.g., a remote data warehouse), that integration would become an MCP server with
OAuth 2.1 (no static secrets) per `harness/patterns/tools-and-mcp.md`.

## What to avoid (load-bearing — do not relitigate)

- **No `psycopg2` / any sync DB driver** — the whole stack is async (`aiosqlite` / `asyncpg` only).
- **No MCP for internal tools** — all tools above are in-process `@tool`; MCP is for external integrations only.
- **No guessed/old library or model versions** — all versions above verified at build time.
- **No secrets in code** — config via `APP_`-prefixed env / `.env` (pydantic-settings).
- **No second `DeclarativeBase`** — `datasets` and all domain models join the same `Base` from `agent/db.py`; `init_db()` creates them automatically.
