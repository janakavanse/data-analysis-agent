# Tech Stack

> The locked stack lives in [`harness/harness.md`](../harness/harness.md); this file records only the
> per-build decisions. Defaults below are the harness defaults — keep them unless the user overrides.
> This is the **reused tested-core** zone (code is truth, like a framework dependency — see
> `spec/constitution.md` § two-zone model); the per-build choices recorded here parameterize that core.
> **Verify the latest library + model versions before pinning** — a guessed/old version 404s, and a 404 at
> runtime almost always means a wrong/stale model name. Pin CURRENT versions at build time
> (`pip index versions <pkg>`, the provider's models list). Phase 1 is SQLite + `create_all` and dev port
> **8001**; alembic/Postgres move entirely into `/deploy`.

## Runtime LLM (the PRODUCT's model — separate from Claude Code, which builds this)

Claude Code builds this product. The PRODUCT's runtime LLM is **chosen at Q4 intake** (with the API key
collected in the same round — never mid-build) and **defaults to a CHEAP tier** (Haiku / Gemini-flash class)
so a non-technical owner can just hit enter. It is wired through LangChain's `init_chat_model` behind a thin
accessor (`agent/llm.py` — `harness/patterns/model-and-providers.md`); no bespoke SDK client lives in
the nodes. Switching tiers is two env vars, no code edit. **The runtime LLM is never stubbed** — even in v1,
the one real capability calls the real model (Decision #2).

- Provider: `google_genai` (Google AI / Gemini) — env `APP_LLM_PROVIDER`
- Runtime model: `gemini-2.5-flash` (cheap tier; verify ID against ai.google.dev/gemini-api/docs/models before first real call — stable alias, no date suffix; current as of 2026-06-20) — env `APP_LLM_MODEL`
- API key env var: `APP_LLM_API_KEY` (pydantic-settings `SecretStr`, prefix `APP_`; collected at Q4 intake; unwrapped with `.get_secret_value()` only at the use boundary in `agent/llm.py`; never logged/printed/repr'd)

> A wrong/stale model name surfaces as a **404 at first real call** while the build looks green — verify the
> exact ID against the provider's models list before pinning, and pin a current one (the cheap-tier alias
> below resolves to the latest snapshot, so prefer the alias unless you need to pin a frozen snapshot).

### Models table — VERIFY before pinning (do not paste a date suffix you guessed)

| Provider  | Cheap (default tier)         | Mid                  | Frontier            |
|-----------|------------------------------|----------------------|---------------------|
| Anthropic | `claude-haiku-4-5`           | `claude-sonnet-4-6`  | `claude-opus-4-8`   |
| OpenAI    | `gpt-5-nano`                 | `gpt-5-mini`         | `gpt-5.4`           |
| Google    | `gemini-2.5-flash`           | `gemini-3.5-flash`   | `gemini-3.5-pro`    |

The runtime model is wired via `init_chat_model` so the `APP_LLM_PROVIDER` / `APP_LLM_MODEL` strings above are
the only change needed to switch tiers — `harness/patterns/model-and-providers.md`.

> **Content coercion required for Google:** `gemini-2.5-flash` with thinking active returns
> `AIMessage.content` as a list of parts, not a plain string. Apply the list-coerce guard (see
> `harness/patterns/model-and-providers.md` § Content coercion) everywhere `.content` is read as a string:
> `finalize_node`, `guardrails.py`, `python_exec` result handling.

## Persistence

Local-first by default; the SAME async code runs on both — only the URL changes (`harness/patterns/durability.md`).
**Phase 1 = SQLite + `create_all`** (no alembic); the migration ladder is a `/deploy` concern only.

- Local (DEMO): SQLite via **aiosqlite** — `sqlite+aiosqlite:///./agent.db` (the `APP_DATABASE_URL` default), schema via `create_all`
- Prod (PRODUCTIONISE): PostgreSQL via **asyncpg** — `postgresql+asyncpg://...` (alembic introduced here, not before)
- ORM: async SQLAlchemy 2.0. **NEVER psycopg2** (sync — breaks the async stack).
- Tables: `runs`, `messages`, `spans` (+ domain entities below). The `runs` table carries
  `input_tokens` / `output_tokens` / `cost_usd` / `thread_id` as first-class columns from Phase 1
  (usage/cost accounting — read `usage_metadata` via a type-guarded `.get()`).
- Domain entities: `sessions` (session_id PK, filename, upload_path, created_at — tracks user-uploaded files per C-SESSION-SCOPE); no other custom tables needed beyond the standard `runs`/`messages`/`spans`

## Deploy target

- Target: TBD — chosen at PRODUCTIONISE (Railway / Fly.io / Modal all viable; see `harness/patterns/deploy.md`)
- Artifact: portable build (`langgraph build` / `langgraph.json`, Dockerfile) — `harness/patterns/deploy.md`
- Prod ladder: PostgreSQL + Redis (Layer 11 "Deploy & Operate").

## Tools

All four tools are in-process `@tool` functions (no MCP — no external process or trust boundary crossed).
See `harness/patterns/tools-and-mcp.md` for the 3-layer classification.

| Tool | Classification | Notes |
|------|---------------|-------|
| `file_load` | in-process `@tool` | reads session-scoped uploaded file from disk; enforces C-SESSION-SCOPE via `sessions.py` |
| `python_exec` | in-process `@tool` | AST-validated pandas/numpy execution; enforces C-ACTION-SAFETY via `guardrails.py`; no shell escape |
| `sql_explorer` | in-process `@tool` | P2 stub: returns fixed sentinel "SQL explorer coming in v2"; no real DB connection |
| `multi_source_fetch` | in-process `@tool` | P3 stub: returns fixed sentinel "Multi-source analysis coming in v3"; no external HTTP |
| `write_todos` | in-process `@tool` | writes structured TODO list to agent state |
| `finish` | in-process `@tool` | signals completion, returns final result |

**Guardrails required:**
- `guardrails.py` — C-ACTION-SAFETY: AST-walks submitted code before execution; blocks `import os`, `import subprocess`, `open(...)` with write mode, `eval`, `exec`, and any shell-escape patterns
- `sessions.py` — C-SESSION-SCOPE: enforces that `file_load` only accesses the file registered for the active session_id; no path traversal

## Interface

- Web framework: FastAPI (async, SSE streaming for agent token output)
- UI: self-contained HTML (single-file, no Node.js / no npm build step) — served as a static file from FastAPI
- Port: `8001` (env `APP_PORT`, default `8001`)
- File upload: multipart form via FastAPI `UploadFile`; stored to a temp session dir; path registered in `sessions` table

## Key libraries — pinned current versions (verified against PyPI 2026-06-20)

| Concern             | Library + pinned version                  | Notes |
|---------------------|-------------------------------------------|-------|
| Web / SSE           | `fastapi==0.138.0`, `uvicorn[standard]==0.49.0` | async, SSE streaming |
| Orchestration       | `langgraph==1.2.6`, `langchain==1.3.10`, `langchain-core==1.4.8` | StateGraph + ReAct; `init_chat_model` |
| LLM provider SDK    | `langchain-google-genai==4.2.5`           | Google Gemini via `init_chat_model`; model_provider=`google_genai` |
| DB (local)          | `sqlalchemy[asyncio]==2.0.51`, `aiosqlite==0.22.1` | local-first default; asyncpg is the prod driver |
| DB (prod)           | `asyncpg` — added at PRODUCTIONISE        | NEVER psycopg2 |
| Settings            | `pydantic-settings==2.14.2`               | env prefix `APP_`; `extra='ignore'` + inline-comment/whitespace strip on values |
| Data analysis       | `pandas==3.0.3`, `numpy==2.4.6`, `openpyxl==3.1.5` | pandas/numpy for `python_exec`; openpyxl for xlsx file_load |
| Observability       | `opentelemetry-api` / `-sdk`              | OTel-GenAI spans → SQLite; opt-in OTLP export |
| Tests               | `pytest==9.1.1`, `pytest-asyncio==1.1.0`  | FakeModel drives the loop with no API key |
| UI E2E              | `pytest-playwright==0.8.0`, `playwright==1.60.0` | gate check 2 runs `tests/e2e/`; self-contained HTML UI requires browser smoke test |

## Example `.env` (local dev — never commit the key)

```
APP_LLM_PROVIDER=google_genai
APP_LLM_MODEL=gemini-2.5-flash
APP_LLM_API_KEY=                          # funded Google AI Studio / Vertex key — injected via env / .env, never committed
APP_DATABASE_URL=sqlite+aiosqlite:///./agent.db   # local-first; swap to postgresql+asyncpg://... at /deploy
APP_PORT=8001
APP_MAX_ITERATIONS=6
```

## What to avoid (load-bearing — do not relitigate; full rationale in `harness/harness.md`)

- **No `psycopg2` / any sync DB driver** — the whole stack is async (aiosqlite / asyncpg only).
- **No MCP for internal tools** — all four tools (`file_load`, `python_exec`, `write_todos`, `finish`) are plain typed `@tool` in-process. MCP is for EXTERNAL integrations only, and with **OAuth 2.1 (no static secrets)** — `harness/patterns/tools-and-mcp.md`.
- **No guessed/old library or model versions** — a stale pin 404s. Verify latest, then pin.
- **No frontier model as the runtime default** — `gemini-2.5-flash` is the cheap/performant tier; escalate to `gemini-3.5-pro` only if a capability demonstrably needs it.
- **No Node.js / npm build step** — UI is a self-contained single HTML file served by FastAPI.
- **No secrets in code** — config via `APP_`-prefixed env / `.env` (pydantic-settings). `APP_LLM_API_KEY` is `SecretStr`, unwrapped with `get_secret_value()` only at the use boundary in `agent/llm.py`, never logged/printed/repr'd.
- **No raw env values trusted as-is** — pydantic-settings does NOT strip inline `#` comments or surrounding whitespace, so `sk-xxx # key` silently 401s on the real run while the build is green. Strip both in a validator, and set `extra='ignore'` so undeclared `.env` keys (`TEST_DATABASE_URL`, CI vars) don't raise.
- **Content coercion for Google provider** — `gemini-2.5-flash` may return `AIMessage.content` as a list of parts when thinking is active; always coerce before any string API (`harness/patterns/model-and-providers.md` § Content coercion).
