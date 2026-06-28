# Architecture

> DataChat — a personal, locally-run CSV/Excel data-analysis agent for a single owner-user. This file owns the HOW: system design, the privacy boundary, the local code-execution model, and the `## Stack`. The product narrative lives in [`roadmap.md`](roadmap.md) and the capability files; the agent graph lives in [`agent.md`](agent.md).

---

## System Overview

A single owner runs DataChat locally. They upload a CSV in the browser, the backend profiles it with pandas (no LLM), and the file is stored on local disk. The owner then asks plain-English questions in a chat panel. For each question the LangGraph agent **plans** a multi-step analysis, **generates pandas code** (the LLM sees only the schema + a few sample rows), **executes that code locally against the full dataframe**, and **synthesizes** a plain-English answer with the key numbers and a summary table, streamed back to the browser. Every run — question, plan, code, result, tokens, cost — is persisted to SQLite as an immutable audit trail and is browsable. The dataset's conversation thread persists across days. The full data never leaves the machine.

## The Privacy Boundary (hard constraint)

This is the load-bearing architectural rule. There are two zones:

| Goes to Gemini (leaves the process to the LLM API) | Stays 100% local (never sent anywhere) |
|----------------------------------------------------|-----------------------------------------|
| Column names + inferred dtypes (the schema) | The full dataset (all rows/cells) |
| Up to `AGENT_SAMPLE_ROWS` (default 20) sample rows | The uploaded file on disk |
| Per-column ranges / missing-value counts (the profile) | All computed results and intermediate frames |
| The user's question + trimmed conversation history | — |

- Profiling makes **no** LLM call at all — pure pandas.
- The plan / generate-code / synthesize nodes send **only** the schema + sample rows + profile + question; they never serialize the full frame into a prompt.
- The generated pandas code is what touches the full data, and it runs **locally** in this process.
- Enforcement: a single `build_llm_context(profile, question, history)` helper is the **only** path that assembles LLM input. Nodes must call it; they never read the full dataframe into a prompt string. A test asserts the assembled context length is bounded by the sample-row cap regardless of file size.

## Local Code Execution Model (safe, in-process)

The agent uses the **LLM-Generated Code Execution** pattern (agentic-ai #22): the LLM writes pandas code, the system runs it with the dataframe in scope. Execution is sandboxed defensively:

- A single function `execute_pandas(code: str, df: pd.DataFrame) -> ExecResult` in `src/execution/sandbox.py` runs the code.
- Restricted namespace: only `pd`, `np`, and the bound `df` are exposed; `__builtins__` is reduced to a safe allowlist (no `open`, `eval`, `exec`, `__import__`, `os`, `socket`).
- The generated code must assign its answer to a conventional variable (`result`); the executor reads `result` back out (a value, a `Series`, or a `DataFrame`) and normalizes it to `key_numbers` + `result_table`.
- Wall-clock timeout `AGENT_EXEC_TIMEOUT_S` (default 30 s) via a worker thread/`signal`; on timeout the run fails with a clear message.
- No filesystem writes, no network from generated code (allowlist excludes them).
- On exception, the **actual traceback + the offending code** are captured and surfaced — transparency over silent retries. The graph attempts at most one self-correction (feed the error back, regenerate once).

> **Assumed:** in-process restricted-namespace execution (not a container/subprocess) is acceptable for a single trusted local owner running their own code generator; this keeps latency low and the deployment a single `python -m src`. A subprocess/container jail is deferred — noted as a hardening item, not Phase 1.

## Component Map

```
Browser (Next.js static export @ :8001/app/)
    │  upload CSV / ask question (SSE stream) / browse history
    ▼
FastAPI (src/api/*)  ──ok()/api_error() envelopes──►  Browser
    │
    ├── upload route ──► profile (pandas, LOCAL) ──► datasets row + file on disk
    │
    └── analyze route (streaming) ──► LangGraph agent (src/graph/*)
                                          │
              profile/schema+samples ──► plan ──► generate_code ──► execute_local ──► synthesize
                                          │            │                  │
                                   Gemini (LLMClient)  Gemini        pandas sandbox (LOCAL, full data)
                                          │
                                   handle_error (on any node failure / exec failure)
                                          │
                                   messages row (audit: question, plan, code, result, tokens, cost)
```

## Layers

| Layer | Responsibility |
|-------|----------------|
| **Frontend** (`frontend/`) | Next.js static export served at `/app/`: upload + empty state, profile panel, chat with streamed answer + numbers + table + collapsible code + tokens/cost, history, and labelled stubs |
| **API** (`src/api/`) | FastAPI routes: upload, analyze (SSE stream), dataset get, message history. `ok()`/`api_error()` envelope |
| **Agent graph** (`src/graph/`) | LangGraph plan-execute graph — profile-context → plan → generate-code → execute-local → synthesize, with an error path. See [agent.md](agent.md) |
| **Execution** (`src/execution/`) | `sandbox.py` — safe local pandas execution; `profile.py` — local dataset profiling |
| **LLM** (`src/llm/`) | `LLMClient` wrapper over the Gemini provider; the **only** path to the model. Extended to return token usage |
| **Storage** (`src/db/`, disk) | SQLite (`datasets`, `messages`) via SQLAlchemy + Alembic; uploaded files under `data/uploads/` |
| **Observability** (`src/observability/`) | structlog JSON logs (input/plan/code/output/latency/tokens/cost/error per run); LangSmith tracing when enabled |

## Data Flow

1. **Trigger (upload):** owner uploads a CSV → file written to `data/uploads/<dataset_id>.csv` → `profile_dataset` runs pandas locally → `datasets` row created with `profile_json` → profile returned and rendered.
2. **Trigger (ask):** owner submits a question on the active dataset → analyze route loads the dataset + its trimmed thread → invokes the agent graph with an SSE stream.
3. **Agent:** `build_llm_context` (schema + samples + profile + history) → **plan** (Gemini) → **generate_code** (Gemini) → **execute_local** (pandas, full data) → **synthesize** (Gemini, streamed). On any failure → `handle_error` (one self-correction for exec failures, else surface error+code).
4. **Persist:** a `messages` row records question, plan, code, key numbers, result table, tokens, cost, status, error, timestamps.
5. **Output:** streamed plain-English answer + key numbers strip + summary table + collapsible code + per-question tokens/cost; run appears in browsable history.

## External Dependencies

| Dependency | Purpose | Failure Mode |
|------------|---------|--------------|
| Google Gemini (`google-genai`) | Plan, generate code, synthesize answer | Node sets `state.error` → `handle_error` → failed `messages` row + streamed error; no crash |
| pandas (local) | Profiling + executing generated code over full data | Profiling error → `400` malformed-file; exec error → one retry then surfaced error+code |
| SQLite (local file) | `datasets` + `messages` persistence / audit trail | DB error → `api_error(...)`; logged with context |
| Local filesystem | Uploaded-file storage | Write failure → `UPLOAD_FAILED` |

## Stack

> This project's concrete choices. Generic rules (model-naming, DB driver placement, dev port, real-key tests) live in [`harness/patterns/tech-stack.md`](../harness/patterns/tech-stack.md). The skeleton is already Gemini + FastAPI + LangGraph + SQLite + Next.js-static-export wired — **extend it in place; do not re-scaffold.**

- **Language:** Python 3.12+ (skeleton requires `>=3.11`; target 3.12) backend; TypeScript/React for the frontend.
- **Agent framework:** LangGraph (plan-execute graph — see [agent.md](agent.md)).
- **LLM provider + model:** Google Gemini via the `google-genai` SDK. Default model `gemini-2.0-flash` (low-cost, honors the cost constraint), env-configurable via `AGENT_LLM_MODEL`.
  > **Assumed:** the DataChat default model is `gemini-2.0-flash`. The skeleton's `GeminiProvider.DEFAULT_MODEL` is currently `gemini-2.5-flash`; the generator must change that default to `gemini-2.0-flash` (and `.env.example` sets `AGENT_LLM_MODEL=gemini-2.0-flash`). If `gemini-2.0-flash` is not available to this key at build time, fall back to `gemini-2.5-flash` and flag it — but verify availability via ListModels first per the model-name rule.
- **Backend:** FastAPI (existing `src/api/`), single-origin server via `uv run python -m src` on port `8001`.
- **Database + ORM:** SQLite (production DB for this single local user — correct, not a substitute) + SQLAlchemy 2.0 + Alembic migrations. Tests use SQLite too (same as production).
- **Frontend:** Next.js 15 + React 19, **static export** (`output: 'export'`, `basePath: '/app'`, `trailingSlash: true`), Tailwind v4 (`@tailwindcss/postcss` + `@source "../";` — never remove), served by FastAPI at `:8001/app/`.
- **Dependency management:** uv + `pyproject.toml` (backend); pnpm (frontend).

| Key library | Version | Purpose |
|-------------|---------|---------|
| langgraph | >=0.1 | Agent graph (already present) |
| google-genai | >=2.9.0 | Gemini SDK (already present) |
| pandas | >=2.2 | **ADD** — local profiling + code execution |
| numpy | >=1.26 | **ADD** — available in the sandbox namespace |
| openpyxl | >=3.1 | **ADD in Phase 4** — Excel/multi-sheet reads |
| sqlalchemy / alembic | >=2.0 / >=1.13 | DB + migrations (already present) |
| structlog | >=24.1 | Structured JSON logging (already present) |
| sse-starlette | >=2.1 | **ADD** — Server-Sent Events streaming of the answer |
| @playwright/test | ^1.61 | Frontend E2E (already installed in `frontend/`) |

**Avoid:** sending the full dataframe to the LLM (privacy violation); a hardcoded op-list interpreter instead of generated code (agentic-ai #22 anti-pattern — fails silently on unmapped questions); `eval`/`exec` of code with full builtins; SQLite-as-substitute reasoning (here SQLite **is** production); a hosted/multi-tenant DB; auth/login (single local owner, none required).

## Deployment Model

Long-running local single-origin service. Build the frontend once (`cd frontend && pnpm build` → `frontend/out/`), then run `uv run python -m src`; open `http://localhost:8001/app/`. SQLite file and uploaded CSVs live under `data/` on the owner's machine. No external services beyond the Gemini API.

## Skeleton Extension Notes (for generators — do not re-scaffold)

- `src/llm/client.py` `call_model` currently returns only text. **Extend** it to also return token usage (e.g. a `call_model_with_usage(prompt, system) -> (text, Usage)` returning `prompt_tokens`/`completion_tokens`), reading `response.usage_metadata` from the Gemini response. Nodes capture usage from here; nodes never call the SDK directly.
- `src/graph/*` (state, nodes, agent, edges, runner) currently implement the `transform_text` slot — **replace the capability logic** with the plan-execute nodes per [agent.md](agent.md); keep the graph/runner/error-edge structure.
- `src/db/models.py` + `alembic/versions/` — **add** `datasets` and `messages` tables (the `runs` table may be dropped or left unused — see [data.md](data.md)).
- `frontend/src/app/page.tsx` — **replace** the transform form with the DataChat UI ([ui.md](ui.md)); keep `next.config.ts`, `postcss.config.mjs`, and the `@source` line in `globals.css` untouched.
- Imports are bare-package (`from config.settings import ...`, `from llm.client import ...`) — `src/` is the package root (`pythonpath = ["src"]`).
