# Code Style

> **Boilerplate status:** The tech-designer fills in the language-specific FILL-IN sections. The
> Universal Rules and Framework Gotchas below apply to all projects.

---

## Universal Rules

1. **Pragmatic typing** — type the public interfaces: every function crossing a module boundary uses
   typed inputs and outputs (Pydantic, TypeScript interfaces, Go structs). Plain dicts are fine for
   internal/local use where a model would be ceremony — don't force a type on everything, but never
   leak an untyped dict across a module boundary.
2. **One responsibility per file** — if a file does two things, split it.
3. **No comments explaining WHAT** — names carry that; comment only non-obvious WHY.
4. **No dead code** — remove unused imports/functions/variables immediately; don't comment them out.
5. **Fail loudly at startup** — validate required config/env at startup, not silently at runtime.
6. **No hardcoding** — values that could change (URLs, limits, credentials) live in config or env vars.

## Language-specific (this project: async Python backend + Next.js/React frontend)

### Naming conventions

**Python:** `snake_case` for modules, functions, variables; `PascalCase` for classes and Pydantic
models / TypedDicts (`AgentState`, `DatasetCreate`); `UPPER_SNAKE` for module-level constants
(`MAX_AGENT_ITERATIONS`, `ALLOWED_SQL_KEYWORDS`). Graph nodes are functions prefixed `node_`
(`node_plan_action`, `node_execute_action`, `node_finalize`). Async functions read as actions
(`run_agent`, `load_dataset`, `query_duckdb`). Settings fields lower_snake, env vars `APP_`-prefixed
(`APP_LLM_MODEL`, `APP_LLM_PROVIDER`) except provider-mandated keys (`GOOGLE_API_KEY`, `DATABASE_URL`).

**Frontend (TypeScript/React):** `PascalCase` components and files (`ChatPanel.tsx`), `camelCase`
hooks/functions/vars (`useChatStream`, `sendMessage`), `kebab-case` route segments. Tailwind utility
classes inline; no separate CSS modules unless a class set is reused.

### File organization

By layer, one responsibility per file (Universal Rule 2). Follow `project-layout.md`:
`graph/` (one file per node + `agent.py` assembly + `state.py`), `tools/` (MCP SQL-query and
schema-inspect tools + the read-only action-safety executor), `api/` (FastAPI routers + the response
envelope), `db/` (SQLAlchemy models, session, Alembic migrations — Postgres metadata), `data/` (DuckDB
engine + pandas CSV ingestion/schema inference), `config.py` (pydantic-settings), `llm.py` (the single
`init_chat_model` accessor). Frontend lives under `frontend/` (Next.js app router).

### Error handling pattern

- **Agent run errors** flow through `AgentState["error"]`, never a raised `HTTPException` from a node.
  Recoverable action errors (bad SQL, empty result) are appended to `action_history` and loop back to
  `plan_action` for self-correction; fatal errors (Gemini call fails, dataset missing) set `error` and
  route to `node_handle_error`. → [`patterns/react-agent.md`](patterns/react-agent.md).
- **API layer** surfaces `state["error"]` as JSON via `api_error("RUN_FAILED", ...)` — never an HTML
  error page (the Next.js frontend renders it). → [`code-style.md`](code-style.md) § Framework Gotchas.
- **Read-only SQL violations** are returned as a typed safety error from the executor (treated as a
  recoverable action error so the LLM can re-plan), never executed.
- **Lost session data** (DuckDB tables/DataFrames gone after a restart) returns a clear, actionable
  message ("Session data is no longer available — please re-upload your file"), not a generic 500.
- Validate config/env (`GOOGLE_API_KEY`, `DATABASE_URL`) at startup — fail loudly (Universal Rule 5).

### Logging pattern

**Structured JSON via `structlog`**, every log bound to `run_id` (and `session_id` where relevant).
Each node logs at least one event (`run.start`, `agent.plan`, `agent.act`, `run.error`,
`run.complete`). Always-included fields: `run_id`, `session_id`, `node`, and on completion
`tokens_input` / `tokens_output` / `estimated_cost_usd`. OTel GenAI spans wrap each Gemini call and
each tool call for token/cost tracing (baseline observability). Never log full dataset rows, raw CSV
contents, or the API key.

### Testing conventions

`pytest` + `pytest-asyncio` (`asyncio_mode = "auto"`), tests under `tests/` named `test_*.py`. The LLM
is **real** (real Gemini, `GOOGLE_API_KEY` from `.env`/CI secret); assert loosely (structure +
non-empty), never on exact model text. Tests run against **real PostgreSQL** (`_test` DB via
`TEST_DATABASE_URL`, auto-created/dropped in `conftest.py`) — same driver as production. DuckDB tests
run against real in-process DuckDB over small fixture CSVs. The Phase 1 ReAct gate drives ≥2 iterations
(one DuckDB query action, then `finish`) and a `force_finalize` past `max_agent_iterations`. Use
`httpx.AsyncClient` for API tests; Playwright for browser E2E (later phase). Use file-backed (not
in-memory) DBs; replace async `init_db` with an `async def` noop, not a sync lambda.

### What NOT to do (this stack)

- Don't build an `LLMClient` wrapper or import the Gemini SDK directly in nodes — go through the single
  `init_chat_model` accessor in `llm.py`.
- Don't add a repository layer — use async SQLAlchemy 2.0 sessions directly.
- Don't emit write/DDL SQL from the agent or run unsandboxed `eval`/`exec` on model output — all SQL is
  read-only, validated at the action-safety boundary before DuckDB runs it.
- Don't pass full datasets into the prompt — only schema + a small row sample.
- Don't mix sync and async SQLAlchemy sessions against the same engine; don't release session-scoped
  DuckDB resources in terminal nodes (causes `SESSION_DATA_LOST` on follow-up questions).
- Don't return errors as HTML or re-raise bare `HTTPException` from agent runs — use the JSON envelope.
- Don't hardcode the model name, port, or DB URL — config/env only (Universal Rule 6).

---

## See also (don't restate these here)

- **ReAct loop, AST safe-executor, reasoning trace** → [`patterns/react-agent.md`](patterns/react-agent.md).
- **LLM provider selection (real-first, no stubs), dirty-`.env` tolerance** →
  [`patterns/llm-providers.md`](patterns/llm-providers.md).
- **DB driver / test environment** → [`tech-stack.md`](tech-stack.md) § Database & Tests.

---

## Framework Gotchas (Python / async FastAPI — keep current)

The backend is **async** (async FastAPI + async SQLAlchemy) and serves a **Next.js/React frontend** — so
errors travel back as **JSON**, not server-rendered HTML.

### Errors are JSON — never an HTML error page

The API returns errors through the standard envelope (`api_error()` → [`../product/05-api.md`](../product/05-api.md))
as JSON; the Next.js frontend renders them. There is no `error.html` template. When an agent run fails,
the error propagates back via the run state's `error` field — surface it as JSON, never re-raise a bare
`HTTPException`:

```python
if state["error"]:
    log.error("run.error", run_id=run_id, error=state["error"])
    return api_error("RUN_FAILED", state["error"], status=500)
```

Every route that runs the agent follows this pattern; the frontend owns presentation.

### Pydantic-settings — `extra="ignore"` + `.env` auto-reload

- Set `extra="ignore"` in `model_config`. `pydantic-settings` reads the **entire** `.env` and validates
  every key; if `.env` carries variables the model doesn't declare (`TEST_DATABASE_URL`, `EDITOR`, CI
  vars), it raises `ValidationError: Extra inputs are not permitted` without it.
- **Dev server auto-restarts on `.env` change.** Run the dev server under a reloader that watches `.env`
  (uvicorn `--reload --reload-include .env`, or `watchfiles`), so editing the API key or a setting takes
  effect without a manual restart. Settings are read at startup (fail-loud, [`code-style.md`](code-style.md)
  Universal Rule 5) — the reload is what makes that ergonomic in dev.

### Async test footguns

- Use `pytest-asyncio`; mark async tests (`@pytest.mark.asyncio` or `asyncio_mode = "auto"`).
- Replace an async `init_db()` with an **async** noop, not a sync lambda:
  `async def _noop(): ...` then `monkeypatch.setattr("<pkg>.graph.runner.init_db", _noop)`. A sync lambda
  breaks `await`.
- Use a file-backed test DB (`tmp_path` for SQLite demos; a `_test` Postgres database for real projects),
  not an in-memory DB — in-memory has shared-state issues across the async engine/connection boundary.
- Drive the async DB with `create_async_engine` + an `AsyncSession`; don't mix sync and async sessions
  against the same engine.
