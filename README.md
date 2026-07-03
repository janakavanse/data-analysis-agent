# Data Analysis Agent

> **All commands below run from the repo root.** There is no subdirectory to `cd` into for backend commands (the frontend build step is the one exception, noted where it applies).

## What This Is

A personal, local-first data-analysis agent. Upload a CSV or XLSX spreadsheet once, then ask natural-language questions about it in plain English — the agent answers with real, computed numbers, produced by pandas code that Google Gemini generates and that runs locally against your actual file. Your raw data rows are never sent to the LLM: only column names, dtypes, and aggregate statistics are. Every question, the code that answered it, the result, and token usage are durably logged to a local SQLite database as an audit trail you can inspect.

## Setup

```bash
copy .env.example .env      # Windows; macOS/Linux: cp .env.example .env
# then edit .env and set AGENT_GEMINI_API_KEY=<your key>
```

```bash
uv sync --extra dev
```

```bash
cd frontend && pnpm install   # first time only
cd ..
```

## Running It

From the repo root:

```bash
uv run python agent.py --run
```

This applies Alembic migrations, builds the Next.js frontend, and starts the server at `http://localhost:8001`.

Alternative (skips the migration/build steps — use once you've already run `--run` at least once, or after `cd frontend && pnpm build`):

```bash
uv run python -m src
```

To confirm migrations actually applied (must print a revision hash, not blank output):

```bash
uv run alembic current
```

## URLs Once Running

| URL | What |
|-----|------|
| `http://localhost:8001/app/` | **UI** — upload a file, ask questions |
| `http://localhost:8001/health` | API health check |
| `http://localhost:8001/docs` | Interactive API docs (Swagger) |

## How to Use It

1. Open `http://localhost:8001/app/` and upload a CSV or XLSX file.
2. Wait for the dataset profile card to appear — row count, column count, and the column list.
3. Type a natural-language question about the data (e.g. "what is the average of the amount column?") and send it.
4. Watch the live status indicator go "Generating code…" → "Running analysis…".
5. Read the answer: plain-language text, a result table, a token-usage badge (prompt + completion = total), and a collapsed "Show generated code" panel you can expand to see and verify the exact pandas code that ran. Ask a follow-up question in the same session — the agent uses prior questions/answers as context.

All of the above is real in Phase 1. The chart area, follow-up-suggestion chips, and "Export cleaned data" button are visible but clearly labelled **"coming in Phase 2"** in the UI itself — they are non-functional stubs, not bugs, and activate in Phase 2.

## Tests

```bash
uv run pytest tests/unit tests/integration -q
```

Requires a real `AGENT_GEMINI_API_KEY` in `.env` — there is no offline/stubbed mode. The integration tests exercise real Gemini code generation and assert on real computed answers (including a ≥5,000-row fixture with a pre-computed answer), so a sampled, truncated, or mocked implementation would fail this suite.

End-to-end (Playwright) tests require the server already running:

```bash
cd frontend && pnpm build
cd ..
uv run python -m src
```

Then, in a second terminal, from the repo root:

```bash
npx playwright test tests/e2e/ --reporter=line
```

## Privacy

Raw data rows, full file contents, and full dataframes are never sent to the LLM, under any circumstance. Only a schema profile — column names, dtypes, null counts, min/max, and sample distinct values for low-cardinality columns — is ever included in the prompt sent to Gemini. The uploaded file is only ever read by pandas, locally, inside the restricted-exec sandbox that runs the generated code; that dataframe never crosses into the LLM call.

## Project Layout

```
src/
  api/            — FastAPI routers: sessions.py, queries.py, health.py
  analysis/       — profiling.py (schema profiling), storage.py (upload persistence),
                    codegen.py (schema-only prompt builder + Gemini call), sandbox.py (restricted exec)
  graph/          — LangGraph: generate_code ⇄ execute_code (≤1 retry) → finalize | handle_error
  domain/         — Pydantic request/response/schema models (DatasetSchema, QueryResponse, ...)
  db/             — SQLAlchemy models (Session, Dataset, Query) + session/engine
  llm/            — provider-agnostic LLM client (llm/providers/gemini.py, anthropic.py)
  config/         — settings
  prompts/        — codegen.md (the Gemini system prompt)
frontend/         — Next.js static export, served by FastAPI at /app/
tests/
  unit/           — no network calls
  integration/    — real Gemini calls, real SQLite
  e2e/            — Playwright, against the live running app
alembic/          — migrations
spec/             — the spec this agent was built from (roadmap, architecture, api, ...)
agent.py          — verify setup (default) / --run to start the server
```

## Roadmap

Phase 1 (this build) covers upload → ask → real answer with audit log. Phase 2 adds interactive charts, follow-up suggestions, a clarifying-question flow, and cleaned-data export — see `spec/roadmap.md`.
