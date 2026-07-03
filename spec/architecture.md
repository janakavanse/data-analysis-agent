# Architecture

---

## System Overview

A single-process local application: a FastAPI backend serves both a REST API and a Next.js static-export single-page UI from one origin (`:8001`). A user uploads a spreadsheet once per session; the backend profiles it locally with pandas (schema + column stats only — never raw rows) and stores that profile in SQLite. The user then asks natural-language questions in the same session; each question is answered by a single Gemini call that generates pandas code from the stored schema (never the data itself), which is executed locally in a restricted sandbox against the real uploaded file. Exactly one automatic retry is allowed if the generated code fails to execute. Every query — question, generated code, result, token usage, timestamps — is durably logged to SQLite as an audit trail. The frontend polls a status endpoint to show a live "generating code… / running analysis…" indicator while a question is being answered.

## Component Map

```
[Browser: Next.js SPA @ :8001/app/]
        │  fetch (JSON) + polling (GET /queries/{id})
        ▼
[FastAPI app @ :8001]
   ├─ api/sessions.py   — create session, upload + profile dataset
   ├─ api/queries.py    — ask question, poll status, session history, export
   │
   ├─ graph/ (LangGraph) — generate_code ⇄ execute_code (≤1 retry) → finalize | handle_error
   │      │  schema-only prompt                    │  local execution, real file
   │      ▼                                        ▼
   │  [Gemini API — google-genai]         [pandas + restricted-exec sandbox]
   │
   ├─ analysis/ — profiling.py, storage.py, codegen.py, sandbox.py, export.py
   ├─ db/ (SQLAlchemy) ───────────────────────────▶ [SQLite: data/agent.db]
   └─ local disk ─────────────────────────────────▶ [data/uploads/<session_id>/<dataset_id>/<file>]
```

## Layers

| Layer | Responsibility |
|-------|----------------|
| API (FastAPI routers) | HTTP contract, request validation, session/dataset/query orchestration, background-task kickoff |
| Graph (LangGraph) | The bounded generate → execute → (retry once) → finalize state machine for one question |
| Analysis (profiling / codegen / sandbox / export) | Schema profiling, schema-only prompt construction, restricted code execution, cleaned-data export |
| LLM client (`src/llm/`) | Gemini/Anthropic provider abstraction — the single, structurally-enforced boundary the LLM ever crosses |
| Data (SQLAlchemy + SQLite) | `Session`, `Dataset`, `Query` persistence — the permanent audit trail |
| Local disk | Uploaded file bytes, per-session directory, never touched by the LLM |

## Data Flow

1. **Trigger:** the user uploads a file via `POST /sessions/{id}/datasets`.
2. The backend profiles the file locally with pandas/openpyxl (`analysis/profiling.py`) and stores a `DatasetSchema` (column names, dtypes, null counts, min/max, sample distinct values for low-cardinality columns) plus the file's disk path in SQLite. Raw content never leaves the local filesystem at this step.
3. The user submits a question via `POST /sessions/{id}/queries`. A `Query` row is created (`status="pending"`) and a background task starts the LangGraph pipeline for that query.
4. `generate_code` builds a prompt from the **stored schema JSON** + the question + up to the last 5 prior Q&A pairs (text only) +, on retry, the prior execution error text — never the dataframe — calls Gemini, and records the generated code plus prompt/completion/total token usage. Status is written to the `Query` row as `"generating_code"` before this call starts.
5. `execute_code` loads the real file into a pandas `DataFrame` **locally** and runs the generated code inside a restricted-exec sandbox, producing an `answer` string and an optional `table` (or raising a concise execution error). Status is written as `"running_analysis"` before this step starts.
6. On an execution error, exactly one retry: the error text (never data) is fed back into a second `generate_code` call, then `execute_code` runs again.
7. `finalize`/`handle_error` writes the final status, answer, table, code, token usage, retry count, and timestamps to the `Query` row.
8. **Output:** the frontend polls `GET /queries/{id}` and renders the plain-language answer, table, collapsible code, and token usage once `status` is `"completed"` (or a clear human-readable error if `"failed"`).

## External Dependencies

| Dependency | Purpose | Failure Mode |
|------------|---------|--------------|
| Gemini API (`google-genai`) | Generates pandas code (and, from Phase 2, structured status/followups) from schema-only context | A failure of the `generate_code` LLM call itself (network/5xx/timeout) is **not** retried by the execution-retry mechanism — it surfaces immediately as a failed query. Only an **execution** failure of already-generated code triggers the one automatic retry. |
| SQLite (`data/agent.db`) | Durable audit log + schema/session/query persistence | Write failure → the API returns a structured `api_error()` (500); this is a known acceptable limitation of local SQLite for a personal single-user tool |
| Local filesystem (`data/uploads/`) | Raw uploaded file storage, read by the sandbox at execution time | Disk full / permission error → the upload endpoint returns a structured 400/500 with a human-readable message |

## Stack

> This project's concrete technology choices. The generic, every-project rules (model-naming, DB driver, dev port, test environment) live in `harness/patterns/tech-stack.md`.

- **Language:** Python 3.11+ (per the existing `pyproject.toml` `requires-python`).
- **Agent framework:** LangGraph — extends the skeleton's existing `src/graph/` in place. A tiny, bounded 4-node graph (`generate_code`, `execute_code`, `handle_error`, `finalize`), **not** a full open-ended ReAct loop — see `spec/agent.md` for the full justification against `harness/patterns/agentic-ai.md`.
- **LLM provider + model:** Google Gemini via the existing `src/llm/providers/gemini.py`. Default model `gemini-3.1-pro` (env-configurable via `AGENT_LLM_MODEL`, per the harness's current safe default for Gemini). `AGENT_GEMINI_API_KEY` is the confirmed key already present in `.env`.
  > **Assumed:** the existing Anthropic provider (`src/llm/providers/anthropic.py`) stays in the codebase as an alternative (the `LLMClient` factory already auto-selects by whichever key is set) but is not the provider this project's prompts are tuned for; Gemini is the one exercised by every gate.
- **Backend:** FastAPI (existing skeleton, extended with new routers).
- **Database + ORM:** SQLite via SQLAlchemy 2.0 + Alembic (existing skeleton). `AGENT_DATABASE_URL=sqlite:///./data/agent.db` per `.env`.
  > **Assumed:** SQLite is the genuine production database for this project (not a substitute) — the brief calls this tool "local-first" and the `.env` already points at SQLite; the "never SQLite-as-a-substitute-for-Postgres" rule does not apply because Postgres was never the chosen stack here.
- **Frontend:** Next.js 15 + React 19, static export (`output: 'export'`, `basePath: '/app'`) served by FastAPI at `/app/` (existing skeleton convention).
- **Dependency management:** uv (Python, `pyproject.toml`), pnpm (frontend, existing `pnpm-lock.yaml`).

| Key library | Version | Purpose | Added in |
|-------------|---------|---------|----------|
| `pandas` | latest 2.x | Load/profile/analyze the uploaded file; the DataFrame the generated code operates on | Phase 1, `[project.dependencies]` |
| `openpyxl` | latest 3.x | Read/write `.xlsx` files (pandas engine) | Phase 1, `[project.dependencies]` |
| `plotly` | latest 5.x | Generated code optionally builds a `plotly.graph_objects.Figure`; the sandbox serializes it to JSON (`fig.to_json()`) for the frontend | Phase 2, `[project.dependencies]` |
| `react-plotly.js` + `plotly.js` | latest | Frontend renders the Plotly JSON figure directly, client-side, as an interactive chart | Phase 2, `frontend/package.json` dependencies |

**Chart pipeline decision:** the generated pandas code, when a chart is appropriate, assigns a `plotly.graph_objects.Figure` to a conventional variable name (`chart`); the sandbox calls `.to_json()` on it and stores that JSON string in `Query.chart_spec_json`; the frontend renders it with `react-plotly.js`'s `<Plot data={...} layout={...} />` by parsing that JSON — no server-side image rendering, no second LLM call to describe the chart. This round-trips a single JSON chart spec end-to-end and keeps chart generation inside the same one-LLM-call model as everything else.

**Avoid:**
- Sending the dataframe, full file bytes, or any raw row to the LLM under any circumstance — see the Privacy Boundary below.
- Unrestricted `exec`/`eval` of generated code — always run through the restricted-globals sandbox (`src/analysis/sandbox.py`).
- A second LLM SDK/client — reuse and extend `src/llm/` (do not hand-roll a separate Gemini call site anywhere else).
- WebSockets/SSE for the status indicator — simple polling of a status field (`GET /queries/{id}`) is sufficient given latency is not a constraint for this tool.
- A message queue or task runner — FastAPI `BackgroundTasks` is sufficient at this scale.

## Privacy Boundary (architectural enforcement, not just a rule)

The hard constraint — **raw data rows must never be sent to the LLM** — is enforced structurally, not just by convention:

- `analysis/codegen.py`'s prompt-builder function is typed to accept only a `DatasetSchema` (a Pydantic model of column-level metadata) plus plain strings (question, history, prior error). It has no parameter through which a `pandas.DataFrame` or raw file bytes could be passed — there is no code path by which `execute_code`'s in-memory dataframe could reach `generate_code`'s LLM call.
- `execute_code` loads the dataframe as a **local variable inside its own function** — it is never written into `AgentState` (the LangGraph state dict), so it can never appear in a state snapshot, a log line, or a LangSmith trace.
- `LLMClient.call_model()` (and its Phase-2 structured variant) is only ever invoked from `generate_code` — `execute_code` never imports or calls anything in `src/llm/`.
- Structured request/response logging logs the **prompt text** (schema + question + history — all already scrubbed of raw data by construction) and the **generated code**, never the dataframe or file contents.

## Deployment Model

Local, single-process: `uv run python agent.py --run` (applies Alembic migrations, builds the Next.js static export, starts `uvicorn` on port 8001) serves both the API and the built frontend from one origin at `http://localhost:8001/app/`. No containerization is required for a personal local tool. `data/` (SQLite DB + uploaded files) is local-only and gitignored.
