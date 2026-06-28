# Personal Data Analysis Agent

> **All commands run from the repo root.** The repo root *is* the project — there is no subdirectory to `cd` into (except where a step explicitly says `cd frontend`). Every Python command is prefixed with `uv run`; a bare `alembic`/`pytest`/`python` will fail unless the venv is manually activated.

A single-user, browser-based **code-execution data analyst**. You upload a CSV, ask a question in plain language, and a LangGraph loop writes and runs **pandas/DuckDB code locally on the full dataset** — the LLM only ever sees the schema, a small sample, and small aggregates. Each answer comes back as prose with key numbers, an interactive Plotly chart, a summary table, the exact code that produced it, the exact payload that was sent to the LLM, and the per-question cost.

---

## Setup

All steps run from the repo root.

1. **Configure your key** (the only manual step — the key is already provided in this environment):

   ```bash
   cp .env.example .env
   ```

   Confirm `AGENT_GEMINI_API_KEY` is set in `.env`.

2. **Install Python dependencies:**

   ```bash
   uv sync --extra dev
   ```

3. **Build the frontend** (run from `frontend/`, then return to the root):

   ```bash
   cd frontend && pnpm install && pnpm build && cd ..
   ```

4. **Apply database migrations:**

   ```bash
   uv run alembic upgrade head
   ```

5. **Verify the tables were created** — this must print revision `0002`. Blank output means the migration did not apply (a failure to fix before continuing):

   ```bash
   uv run alembic current
   ```

6. **Run the app:**

   ```bash
   uv run python -m src
   ```

   Then open **http://localhost:8001/app/**

---

## Using it (Phase 1)

1. **Upload a CSV** — drag and drop it into the upload zone. A sample lives at `data/sample/sales.csv`. Wait for "Dataset loaded".
2. **Ask a question** in plain language, e.g. *"What were total sales by month, and which month was highest?"*, then press **Ask**.
3. **Read the answer.** You get prose with the key numbers, an **interactive Plotly chart** (hover, zoom, filter), and a **summary table**.
4. **Expand "Show code"** to see the exact pandas/DuckDB code that produced the answer.
5. **Expand "What was sent to the LLM"** to see the exact payload — schema + sample rows + small aggregates only, never bulk data.
6. **Check the cost line** — the per-question estimate plus token counts (in / out), computed from the real Gemini usage.

---

## What's real vs Coming soon

**Real in Phase 1:**

- CSV upload → local DuckDB ingest (schema + sample + row count)
- Plain-language question → LangGraph code-execution loop (plan → generate code → run locally on the full data → revise-on-error → summarize → select chart)
- Prose answer + key numbers
- Interactive Plotly chart
- Summary table
- Collapsible "Show code" panel (exact code)
- "What was sent to the LLM" transparency panel (exact payload)
- Per-question cost + token counts
- Staged progress ("Planning… / Writing code… / Running… / Building chart…")

**Coming soon — clearly-labelled, non-functional stubs (deferred to later phases, NOT bugs):**

- Saved sessions
- Dataset profile (ranges, missing counts, distributions)
- Follow-up suggestions
- Daily cost total
- Column notes & business rules
- Export (CSV / chart image / report)
- Saved datasets
- Analysis library
- Connect a database
- Multi-file joins
- Live token-by-token streaming

These appear in the UI as disabled / "Coming soon" states. A stub never errors — if you see one, it is deferred, not broken.

---

## Privacy boundary

Code runs locally on the **full** dataset; the LLM only ever receives the schema + ≤20 sample rows + small aggregates. The "What was sent to the LLM" transparency panel shows exactly what left the local process.

---

## Testing

The Phase-1 gate runs against the **real Gemini API** using the key in `.env`, executes generated pandas code on a large real CSV fixture, and runs Playwright E2E against the live app:

```bash
uv run alembic upgrade head && uv run pytest tests/phase1 -q && (cd frontend && pnpm build) && uv run pytest tests/e2e -q
```

The Playwright E2E suite drives `http://localhost:8001/app/`. With the app running (`uv run python -m src`), you can run the browser tests directly:

```bash
cd frontend && pnpm test:e2e
```

---

## Stack

Python 3.12 · FastAPI (:8001) · LangGraph · Gemini (`gemini-2.5-flash`) · DuckDB (local analysis compute) · SQLite + SQLAlchemy (app state) · Next.js 15 static export + Plotly.
