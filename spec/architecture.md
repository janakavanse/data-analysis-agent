# Architecture

---

## System Overview

A single-origin local web app. The Next.js static-export frontend (served at `/app` by FastAPI) sends a plain-English question to `POST /runs`. FastAPI hands it to a LangGraph agent that (1) introspects the active dataset's schema and a small row sample from an **in-process DuckDB** engine, (2) asks **Gemini** to produce a single read-only `SELECT` plus a chart spec, (3) validates and executes that SELECT locally against DuckDB, and (4) returns columns + rows + the chart spec to the UI, which renders a table and a chart. The full dataset never leaves the machine; only schema + a bounded sample reach the LLM.

## Component Map

```
Browser (Next.js /app)
    │  POST /runs { input_text }
    ▼
FastAPI (src/api/runs.py)
    │  run_agent(input_text)
    ▼
LangGraph runner (src/graph/runner.py)  ──writes──►  SQLite RunRow (app-state)
    │
    ▼
agentic_ai graph
   plan_sql ──► execute_sql ──► finalize
       │             │
       └──(error)────┴──► handle_error
       │             │
       ▼             ▼
   Gemini       DuckDB (in-process, user data)
 (schema+sample  (schema introspect +
  → SQL+chart)    read-only SELECT)
```

## Layers

| Layer | Responsibility |
|-------|----------------|
| Frontend (Next.js static export) | Question box, SQL display, table, chart (Recharts), labelled stubs |
| API (FastAPI) | `/runs`, `/health`; `{data,error}` envelope; serves `frontend/out` at `/app` |
| Agent graph (LangGraph) | `plan_sql` (LLM) → `execute_sql` (DuckDB) → `finalize` / `handle_error` |
| Analytics engine (DuckDB, in-process) | Holds user data; schema introspection; sample extraction; read-only SELECT execution |
| SQL guard | Rejects anything that isn't a single read-only SELECT before execution |
| App-state store (SQLite + SQLAlchemy) | `RunRow` bookkeeping: status, input, structured output JSON, error |
| LLM client | `LLMClient().call_model(prompt, system=...)`; Gemini provider |
| Observability | structlog events per operation |

## Data Flow

1. **Trigger:** user submits a question in the browser → `POST /runs { input_text }`.
2. **Introspect:** the runner builds context from DuckDB — table/column names + types, and ≤ N sample rows (default 5) for the active dataset (Phase 1: the seeded `sales` table).
3. **Plan:** `plan_sql` sends the question + schema + sample to Gemini and parses a JSON reply `{ sql, chart_spec }`.
4. **Guard + execute:** `execute_sql` validates the SQL is a single read-only `SELECT` (via the SQL guard), then runs it against DuckDB, fetching bounded `columns` + `rows`.
5. **Finalize:** the structured payload `{ sql, columns, rows, chart_spec, error }` is serialized as JSON into `RunRow.output_text`; status set to `completed`/`failed`.
6. **Output:** `POST /runs` returns the run; the UI parses `output_text` JSON and renders the SQL block, table, and chart.

**Privacy boundary:** only step 3's payload (schema + ≤ N sample rows) crosses the process boundary to Gemini. The full DuckDB dataset and all query results stay local.

## External Dependencies

| Dependency | Purpose | Failure Mode |
|------------|---------|--------------|
| Gemini (`gemini-2.5-flash`) | NL → SQL + chart spec | `plan_sql` sets `error` → `handle_error` → UI shows "Could not understand the question" |
| DuckDB (in-process) | Hold user data; run read-only SELECT | In-process; query errors set `error` → graceful UI message |
| SQLite (app-state) | `RunRow` bookkeeping | Local file; standard SQLAlchemy errors surface as 500 |

## Stack

> This project's concrete technology choices. Generic rules (model-naming, DB driver, dev port, real-key test rule) live in `harness/patterns/tech-stack.md`.

- **Language:** Python 3.12 (backend) · TypeScript (frontend)
- **Agent framework:** LangGraph (extends the skeleton's compiled `agentic_ai` graph)
- **LLM provider + model:** Gemini / `gemini-2.5-flash` (key `AGENT_GEMINI_API_KEY`, env prefix `AGENT_`)
- **Backend:** FastAPI (single origin; serves the static frontend at `/app`)
- **Database + ORM:** SQLite + SQLAlchemy 2.0 for **app-state** (`RunRow`, and from Phase 3 `DatasetRow`); **DuckDB (in-process) for the user-data analytical engine** — the new piece
- **Frontend:** Next.js 15 static export (`pnpm build` → `frontend/out`) + React 19; Recharts for charts
- **Dependency management:** uv + `pyproject.toml` (Python) · pnpm (frontend)

| Key library | Version | Purpose |
|-------------|---------|---------|
| duckdb | latest (add to `[project.dependencies]`) | In-process analytical query engine over user data |
| langgraph | (existing) | Agent graph orchestration |
| google-genai | (existing) | Gemini provider |
| sqlalchemy | (existing) | App-state ORM |
| recharts | latest | Frontend charting library |

> **Assumed:** DuckDB runs as a single in-process connection over a file at `data/analytics.duckdb` (configurable), opened read-only for query execution and writable only for the seed/ingest paths. This keeps the engine durable across requests without a server process.

> **Assumed:** Charting library = **Recharts** (React-native, declarative, zero-canvas SSR-friendly, pairs cleanly with the React 19 / Next static export already in the skeleton). Chart.js would also work but needs a wrapper and imperative canvas handling; Recharts is the lower-friction fit.

**Avoid:** any cloud data warehouse or third-party data service (violates the privacy boundary); sending full result sets or full tables to the LLM; multi-statement or write SQL; Postgres for the analytical engine (DuckDB is the chosen in-process engine).

## Deployment Model

Local long-running service. `python agent.py --run` applies migrations, builds the frontend, and starts uvicorn on port 8001; the UI is served at `http://localhost:8001/app/`. Everything (LLM aside) runs on the user's machine.
