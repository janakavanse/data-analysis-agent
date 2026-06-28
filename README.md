# Privacy-Preserving Data Analysis Agent

Upload a CSV, ask questions in plain English, get answers with the exact analysis code shown — and your **raw data never leaves the machine**. The LLM (Gemini) sees only schema, column profiles, and summaries; it writes pandas code that executes **locally** in a sandbox against your real rows.

> **All commands run from the repo root.** The repo root IS the project — there is no subdirectory to `cd` into (except `frontend/` where noted). Every Python command is prefixed with `uv run`; bare commands fail unless the venv is manually activated.

## Architecture

Python/FastAPI + LangGraph (`plan → generate_code → execute_locally → summarize`) + Gemini + SQLite (the production DB for this single-user tool) + Next.js static export served at `/app/` + a local subprocess sandbox for generated pandas. Structured logging is wired from day one.

## Prerequisites

- Python 3.11+ with [`uv`](https://docs.astral.sh/uv/)
- [`pnpm`](https://pnpm.io/) for the frontend
- A Gemini API key

## Setup

1. Copy `.env.example` to `.env` and set your Gemini key:
   ```
   AGENT_GEMINI_API_KEY=your-key-here
   AGENT_DATABASE_URL=sqlite:///./data/agent.db
   ```
2. Install backend deps and apply migrations (run from the repo root):
   ```
   uv sync
   uv run alembic upgrade head
   uv run alembic current   # must print a revision hash, not blank
   ```
3. Build the frontend (run from the repo root):
   ```
   cd frontend && pnpm install && pnpm build && cd ..
   ```

## Run

From the repo root:
```
uv run python -m src
```
Then open **http://localhost:8001/app/**.

Upload a CSV, view the auto-profile, ask a question (e.g. "What is the total revenue by month?"), watch the live steps and streamed answer, and click **Show code** to see the exact pandas that ran locally.

## Test

From the repo root:
```
uv run alembic upgrade head && uv run pytest
```
Then the frontend gates:
```
cd frontend && pnpm build                 # static export styled-render
cd frontend && pnpm exec playwright test  # E2E against the running app at http://localhost:8001/app/
```
Tests run against the **real Gemini API** using `AGENT_GEMINI_API_KEY` from `.env`.

## Phase status

- **Phase 1 (current):** upload → auto-profile → ask one question → streamed answer with shown code. Raw rows stay local (verified by the audit trail). Deferred features appear as clearly-labelled "Coming soon" stubs.
- **Phase 2:** conversational memory, interactive charts, summary tables, suggested follow-ups, cost/token meter + daily total.
- **Phase 3:** file library, cross-file compare, multi-sheet Excel, audit-trail browser, clarify/plan-confirm.
