# Roadmap

---

## What This Agent Does

A personal, local-first data-analysis agent for a single user. The user uploads a CSV or Excel spreadsheet once and then asks a series of natural-language questions about it in the same session. The agent answers in plain language with the key numbers, alongside a summary table and (from Phase 2) an interactive chart, and can export a cleaned/filtered version of the data on request. It is used ad hoc, whenever the user has a spreadsheet they want to understand quickly, without writing pandas code themselves.

## Who Uses It

One person, locally, on their own machine — no team, no shared accounts. They are typically looking at a spreadsheet (expenses, survey exports, sales data, a personal dataset) and want quick, trustworthy answers ("what's the average X", "how many rows have Y", "break this down by Z") without opening a notebook.

## Core Problem Being Solved

Answering ad hoc questions about a spreadsheet normally means opening Excel/pandas and writing formulas or code by hand, one question at a time. This agent turns that into a conversation: upload once, ask in plain English, get a real computed answer plus the exact code that produced it — so the user can trust and verify the number, not just believe it.

## Success Criteria

- [ ] A user can upload a CSV or XLSX file and receive a schema profile (columns, dtypes, row count) within seconds, with zero raw data rows ever leaving the local machine.
- [ ] A user can ask a natural-language question about the uploaded data and receive a plain-language answer with correct key numbers, computed by locally-executed generated code against the **full** dataset (never a sample or truncated subset).
- [ ] Every query is durably logged with its question, the generated code, the result, token usage, and timestamps — retrievable after the fact as a real audit trail.
- [ ] When generated code fails to execute, the system automatically retries exactly once with a corrected approach before surfacing a clear, human-readable error — the user is never shown a raw stack trace.
- [ ] A user can ask a second, follow-up question in the same session and get an answer that correctly uses context (prior question + answer) from earlier in the session.

## What This Agent Does NOT Do (Out of Scope)

- **No multi-file joins or cross-dataset comparison, ever** — one file per session, in every phase, with no future plan to add this.
- **No persistent dataset/export library across sessions** — no "past uploads" or "past exports" browser, in any phase. Charts, tables, and exported files are ephemeral, viewed/downloaded in the moment.
- **No multi-day resumable sessions** — a session's working context (uploaded file handle, conversation) does not survive past the browser session/process restart, beyond what is captured in the permanent DB audit log.
- **No iterative/multi-step reasoning beyond one code-generation call plus exactly one execution retry** — no agent planning loop, no multi-step tool chains, no reflection passes.
- **No integrations** — no Slack, email, BI-tool, or other external notification/reporting integrations.
- **No access control, authentication, or multi-user support** — this is a single-user local tool.
- **Raw data rows, full file contents, or full dataframes are never sent to the LLM, under any circumstance** — this is a hard architectural constraint, not a preference (see Key Constraints).

## Key Constraints

- **HARD PRIVACY CONSTRAINT: raw data rows must never be sent to the LLM.** Only schema/column metadata — column names, dtypes, null counts, min/max, and sample distinct values for low-cardinality columns — may ever be sent to the LLM to generate analysis code. The actual data is only ever touched by the generated code executing locally against the uploaded file. See `spec/architecture.md` and `spec/agent.md` for how this is enforced structurally, not just by convention.
- **Exactly one automatic retry** on a generated-code execution failure (e.g. wrong column name, type mismatch); no further retries — a second failure surfaces a clear error.
- **Small-scale, latency-insensitive.** Personal spreadsheets, a few MB. Correctness and trust (real numbers, visible code, audit trail) matter far more than response time.
- **One file per session; no multi-file joins**, now or in any future phase.
- **Local-first.** SQLite + local disk storage; the only network dependency is the Gemini API call itself.
- **One query in flight per session at a time.** A session's next question waits for the current one to finish (`POST /sessions/{id}/queries` returns `409` naming the in-flight `query_id` if one is already running) — this matches the natural one-question-at-a-time chat interaction model and keeps each session's LangGraph run isolated with no concurrency logic needed inside the graph itself.
  > **Assumed:** the brief describes one question at a time conversationally but doesn't state the concurrency rule explicitly; serializing per-session (via a `409`) is the simplest correct behavior for a single-user chat-style UI where a second question is never submitted before the first renders.

## Phases of Development

> **Phase 1 is the smallest first-time-right user-testable win.** It must work perfectly the first time the user tests it. Its backend is minimal but REAL on the one core path (no fake data on the tested path). Its frontend is visually complete: real UI for the one working path PLUS clearly-labelled NON-FUNCTIONAL stubs for everything coming later. Each later phase wires those stubs into real functionality.

> **Decision — auto-retry included in Phase 1, not deferred.** The one-retry-on-execution-error behaviour is included in Phase 1 (not pushed to Phase 2) because: (a) it is central to the trust/reliability story the brief calls non-negotiable, (b) it costs almost nothing extra — the LangGraph conditional edge that implements it has to exist anyway to satisfy "agentic stack wired from day one," and (c) leaving it out of Phase 1 would mean shipping a visibly worse error experience on the very first tested path, which conflicts with "zero rough edges on the tested path."

### Phase 1 — Upload, Ask, Get a Real Answer

- **Goal:** the complete core journey works for real, first time: upload a CSV/XLSX → the agent profiles it locally → ask one natural-language question → get back a real plain-language answer with real numbers, computed by locally-executed generated code against the real file, using Gemini for code generation from schema-only context (never raw rows). The collapsible code panel, token-usage display, DB audit log, the "generating code… / running analysis…" status indicator, and the one-retry-on-execution-error are all real. Conversation memory within the session is real (a second question can reference the first).
- **Independent slices (parallel build units):**
  - `db-schema` (backend) — deps: none. New SQLAlchemy models `SessionRow`, `DatasetRow`, `QueryRow` + the Alembic migration that creates them.
  - `domain-models` (backend) — deps: none. Pydantic request/response/domain types: `DatasetSchema`/`ColumnSchema` (the ONLY shape ever passed into the LLM prompt builder), `SessionResponse`, `DatasetResponse`, `QueryRequest`, `QueryResponse`.
  - `llm-usage-tracking` (backend) — deps: none. Extends `src/llm/client.py` and both `src/llm/providers/*.py` so a model call returns text **and** token-usage metadata (prompt/completion/total tokens), without breaking the existing `call_model()` signature used by any other caller.
  - `dataset-profiling` (backend) — deps: `domain-models`. Pure functions: save an uploaded file to `data/uploads/<session_id>/<dataset_id>/<filename>`, load it with pandas/openpyxl, and produce a `DatasetSchema` (columns, dtypes, null counts, min/max, sample distinct values for low-cardinality columns) — never returns or logs raw rows.
  - `codegen-sandbox` (backend) — deps: `domain-models`, `llm-usage-tracking`. The prompt builder that accepts **only** a `DatasetSchema` + question text + conversation-history text + optional prior-error text (never a dataframe — enforced by the function's type signature), calls `LLMClient` (Gemini), and extracts generated code; the restricted-exec sandbox that runs that code against a locally-loaded dataframe and captures `answer`/`table` or raises a concise execution error.
  - `query-graph` (backend) — deps: `db-schema`, `domain-models`, `codegen-sandbox`. The LangGraph wiring: `generate_code` ⇄ `execute_code` (bounded, exactly one retry), `handle_error`, `finalize`; `run_query()` entry point that creates/updates the `QueryRow` audit record, including the live status writes ("generating_code" → "running_analysis") that the frontend polls for. Structured request/response logging (question, code, latency, tokens, error) to stdout.
  - `api-routes` (backend) — deps: `db-schema`, `domain-models`, `dataset-profiling`, `query-graph`. FastAPI routers: `POST /sessions`, `POST /sessions/{id}/datasets`, `GET /sessions/{id}/datasets/{dataset_id}`, `POST /sessions/{id}/queries` (rejects with `409` if the session already has a non-terminal query, else kicks off `run_query` via `BackgroundTasks`), `GET /queries/{id}` (poll), `GET /sessions/{id}/queries` (history).
  - `frontend-upload-and-thread` (frontend) — deps: none (builds against the `spec/api.md` contract). Real upload zone + dataset-profile summary, real chat-style Q&A thread, real per-answer card (answer text, basic table, collapsed code panel, token-usage badge, live status indicator, retry note), labelled non-functional stubs for chart area / follow-up chips / export button, and the Playwright smoke test in `tests/e2e/`.
- **Key surfaces / files:** `src/db/models.py`, `alembic/versions/*.py`, `src/domain/*.py`, `src/llm/client.py`, `src/llm/providers/{anthropic,gemini}.py`, `src/analysis/{profiling,storage,codegen,sandbox}.py`, `src/prompts/codegen.md`, `src/graph/{state,nodes,edges,agent,runner}.py`, `src/api/{sessions,queries}.py`, `pyproject.toml` (`[project.dependencies]`: add `pandas`, `openpyxl`), `frontend/src/app/**`, `frontend/tests/e2e/phase1.spec.ts`.
- **Gate command:**
  1. `uv run alembic upgrade head`
  2. `uv run alembic current` (must show a revision, not blank output)
  3. `uv run pytest tests/unit tests/integration -q` (real `AGENT_GEMINI_API_KEY` from `.env`; the integration fixture uses a CSV of ≥5,000 rows with a pre-computed answer, so a sampled/truncated implementation would fail — see `spec/capabilities/ask-question.md`)
  4. `cd frontend && pnpm build` (styled static export)
  5. `uv run python agent.py --run` boots with no `ImportError`/`ModuleNotFoundError`, serving `http://localhost:8001/app/`
  6. `npx playwright test tests/e2e/ --reporter=line` (against the live app at `:8001/app/`)
  7. **Observability check:** while step 5's server is running, submit one real question and confirm stdout emits a structured (`structlog` JSON) log line for the `generate_code` call containing `question`, `token_usage`, and `latency` fields — observability is wired in Phase 1, not deferred (per `spec/agent.md` → Observability). If `LANGCHAIN_TRACING_V2`/`LANGCHAIN_API_KEY` is set in `.env`, additionally confirm a trace appears in LangSmith for that run.
- **How the user tests it (handoff seed):**
  1. `uv run python agent.py --run` from the repo root, then open `http://localhost:8001/app/`.
  2. Upload a real CSV or XLSX file — see the dataset profile appear (row/column count, column list).
  3. Ask a question about the data (e.g. "what is the average of column X" or "how many rows have Y = Z") — watch the status line go "Generating code…" → "Running analysis…", then see a plain-language answer with the real number, a basic table, a token-usage badge, and a collapsed "Show generated code" panel you can expand.
  4. Ask a second question that references the first ("and what about last month") and confirm the answer uses that context.
  5. Note the greyed-out chart panel, follow-up chips row, and "Export cleaned data" button — these are **labelled non-functional stubs**, not bugs; they activate in Phase 2.

### Phase 2 — Conversation, Charts & Export

- **Goal:** wire every Phase-1 stub into a real feature: interactive charts render for chart-appropriate questions, the summary table is polished (sorting/formatting), the agent asks a clarifying question before running analysis when a question is ambiguous or references a nonexistent column, the agent proactively suggests 2-3 follow-up questions after each answer, and the user can export a cleaned/filtered version of the data. This phase delivers 5 distinct capabilities: clarification-before-analysis, unanswerable-question detection, proactive follow-up suggestions, interactive chart rendering, and cleaned-data export — well over the 3-capability floor for a requirements phase.
- **Independent slices (parallel build units):**
  - `db-schema-v2` (backend) — deps: none. Adds `chart_spec_json` and `suggested_followups_json` columns to `queries`, plus the migration.
  - `query-pipeline-v2` (backend) — deps: `db-schema-v2`. Extends the **same single** `generate_code` LLM call to return structured output `{status: "ok" | "needs_clarification" | "unanswerable", code, followups, message}` instead of bare code text; extends the sandbox to optionally capture a `chart` variable (a Plotly figure) from generated code; extends `after_generate_code` routing so `needs_clarification`/`unanswerable` skip execution and go straight to `finalize` with a message instead of an error.
  - `export-cleaned-data` (backend) — deps: none (reuses the stable Phase-1 sandbox interface; re-executes a query's already-audited `generated_code` against the dataset file and streams the resulting dataframe as CSV/XLSX — no new LLM call, no new sandbox capability).
  - `frontend-phase2-ui` (frontend) — deps: none declared (builds against the updated `spec/api.md` contract; integration is verified together at the phase gate). Real Plotly chart rendering (`react-plotly.js`), real clickable follow-up chips, real "Export cleaned data" button, a clarification message bubble type, polished summary table (sortable columns, formatted numbers), and the extended Playwright suite.
- **Key surfaces / files:** `src/db/models.py`, `alembic/versions/*.py`, `src/analysis/{codegen,sandbox,export}.py`, `src/graph/{nodes,edges,state}.py`, `src/prompts/codegen.md`, `src/api/queries.py` (new export route), `pyproject.toml` (add `plotly`), `frontend/package.json` (add `react-plotly.js`, `plotly.js`), `frontend/src/app/**`, `frontend/tests/e2e/phase2.spec.ts`.
- **Gate command:**
  1. `uv run alembic upgrade head` && `uv run alembic current`
  2. `uv run pytest tests/unit tests/integration -q` (real Gemini key; includes a chart-appropriate question, an ambiguous question, a question referencing a nonexistent column, a two-turn session where the second question is a follow-up chip click, and — reusing the Phase 1 ≥5,000-row fixture — an export test asserting the downloaded file's row count equals the full computed result, not the 50-row display cap, so a truncated-export implementation would fail this gate)
  3. `cd frontend && pnpm build`
  4. `uv run python agent.py --run`
  5. `npx playwright test tests/e2e/ --reporter=line`
- **How the user tests it (handoff seed):**
  1. `uv run python agent.py --run`, open `http://localhost:8001/app/`, re-use (or re-upload) a dataset from Phase 1.
  2. Ask a question that naturally produces a chart (e.g. "show me a breakdown of X by Y") — see a real interactive Plotly chart render in the previously-stubbed chart area.
  3. Click one of the real follow-up-suggestion chips shown under the answer — confirm it populates and submits the next question.
  4. Ask a deliberately ambiguous question (e.g. reference a vague "that column") — confirm the agent asks a clarifying question instead of guessing.
  5. Ask about a column that does not exist in the file — confirm the agent clearly says it cannot answer and why, without guessing a substitute.
  6. Click "Export cleaned data" on an answer that produced a table — confirm a real CSV/XLSX file downloads.
