# Roadmap

---

## What This Agent Does

A local-first conversational data-analysis agent. A single user uploads a CSV/Excel spreadsheet into a local web app and explores it in plain English — asking questions and follow-ups, getting back answers that **always show the work** (the exact calculation that ran and the numbers behind it), plus charts, summary tables, surfaced findings, and one-shot reports. The defining promise is privacy: the data never leaves the user's machine — the LLM only ever sees column names, dtypes, a tiny sample, and computed summaries, and writes pandas code that executes **locally**.

## Who Uses It

A single, technically-comfortable individual doing ad-hoc analysis of their own spreadsheets (an analyst, founder, researcher, or operator) who wants conversational speed without uploading private data to a cloud service.

## Core Problem Being Solved

Spreadsheet analysis today means either writing pandas/SQL by hand, or pasting private data into a cloud chatbot. This agent gives the conversational speed of the chatbot while keeping the raw data entirely local — and it always shows its work, so the user can trust and verify every number.

## Success Criteria

- [ ] A user uploads a CSV and asks a plain-English question, getting a correct answer that includes the pandas code and the computed numbers.
- [ ] The full dataset is never transmitted to the LLM — only schema + N sample rows + computed summaries (verifiable in the prompt payload).
- [ ] Follow-up questions correctly build on prior conversation context.
- [ ] Computed answers match a direct full-data pandas computation (not a sampled approximation).
- [ ] Messy data (missing values, mixed types) is handled without pestering the user with cleaning questions.

## What This Agent Does NOT Do (Out of Scope)

- No multi-user, auth, sharing, or cloud deployment — single-user localhost only.
- No sending raw/full row-level data to the LLM, ever.
- No write-back / editing of the source file — read-only analysis.
- No database/warehouse connectors — file upload only.
- No scheduled or automated pipelines — interactive, ad-hoc use only.
- No model fine-tuning or learning from feedback.

## Key Constraints

- **Privacy (hard):** analysis runs locally in pandas; the LLM sees only schema + N sample rows (default 5) + computed summaries.
- **Cost (hard):** default to the cheap `gemini-2.5-flash` model and minimal API calls per question.
- **Local-first:** SQLite + in-process DataFrame; runs as one local process.
- **Show the work (hard):** every answer includes the code and the numbers.

## Phases of Development

> **Phase 1 is the smallest first-time-right user-testable win.** Real backend on the one tested path (real Gemini writes pandas, code executes locally, real numbers), real upload+chat UI for that path, PLUS clearly-labelled NON-FUNCTIONAL stubs for charts, one-shot report, Excel, and auto-findings. Later phases wire those stubs into real functionality one increment at a time.

### Phase 1 — Ask a CSV, get an answer with the work shown

- **Goal:** Upload a CSV, ask ONE plain-English question, and get a correct answer WITH the pandas code it ran and the numbers behind it. Real on this path end-to-end; everything else is a labelled stub.
- **Independent slices (parallel build units):**
  - `db-schema` (backend) — Alembic migration + SQLAlchemy models for `Session`, `Dataset`, `Message`. Deps: none.
  - `analysis-core` (backend) — `src/analysis/store.py` (DataFrame store + schema/sample extraction) and `src/analysis/sandbox.py` (restricted local exec of pandas). Deps: none (pure pandas; no DB/graph).
  - `graph-loop` (backend) — replace the `transform_text` slot in `src/graph/` with the analysis loop (`extract_schema → plan_analysis → execute_analysis → format_answer → finalize`, with the repair edge + `handle_error`); new prompts `src/prompts/analysis.md` + `src/prompts/format_answer.md`; update `src/graph/state.py`, `edges.py`, `agent.py`, `runner.py`. Deps: `analysis-core` (uses store + sandbox), `db-schema` (persists messages). **Serialize after those two.**
  - `api-routes` (backend) — `POST /datasets`, `POST /sessions/{id}/ask`, `GET /sessions/{id}` in `src/api/`; new Pydantic models in `src/domain/`; remove the `/runs` transform endpoints. Deps: `graph-loop` (calls the runner), `db-schema`. **Serialize after graph-loop.**
  - `frontend-workspace` (frontend) — replace `frontend/src/app/page.tsx` with the upload zone + chat transcript + collapsible "Show the work" + labelled coming-soon stubs (charts / report / Excel / insights). Deps: none — builds against the API contract in [api.md](api.md) in parallel.
- **Key surfaces / files:** backend → `alembic/versions/*`, `src/db/models.py`, `src/analysis/{store,sandbox}.py`, `src/graph/{state,nodes,edges,agent,runner}.py`, `src/prompts/{analysis,format_answer}.md`, `src/api/*`, `src/domain/*`. frontend → `frontend/src/app/page.tsx` (+ components under `frontend/src/`). Disjoint: frontend never touches `src/`.
- **Gate command:** `uv run alembic upgrade head && uv run pytest -q` (real Gemini via `.env`). Tests must include: a CSV upload returning correct schema/row_count; an ask over a **fixture of ≥500 rows** where the sampled-rows answer differs observably from the full-data answer, asserting the full-data answer is returned; a follow-up using prior context; a sandbox test that `import os` / file access is blocked; assertion that the LLM prompt payload contains only schema + N sample rows (no full data).
- **How the user tests it (handoff seed):** Open `http://localhost:8001/app/`. Drag a CSV onto the drop zone — see the filename, row count, and column chips appear. Type a question like "what's the average of <a numeric column>?" and send. See the assistant reply with a plain-English answer, then click "Show the work" to reveal the pandas code and the result table. Confirm the number is correct. The Charts / One-shot report / Excel / Insights panels are visibly greyed and labelled "coming soon (Phase N)" — those are intentional stubs, not bugs.

### Phase 2 — Inline charts

- **Goal:** When a question implies a visualization (or the user asks for a chart), render a chart inline in the chat alongside the answer and the work.
- **Independent slices (parallel build units):**
  - `chart-backend` (backend) — extend `format_answer`/add a `render_chart` branch: the LLM may emit chart code; render locally with matplotlib to a PNG (base64) returned in the payload. Add `chart` to `Message.result_json`. Deps: none beyond Phase 1.
  - `chart-frontend` (frontend) — render the returned chart image inline in the assistant bubble; un-stub the Charts panel. Deps: none — builds against the extended contract.
- **Key surfaces / files:** backend → `src/graph/nodes.py`, `src/prompts/*`, `src/analysis/charts.py`. frontend → assistant-bubble component.
- **Gate command:** `uv run alembic upgrade head && uv run pytest -q` (real Gemini) — includes an ask whose answer carries a non-empty base64 PNG chart rendered locally.
- **How the user tests it (handoff seed):** Upload a CSV, ask "show me a bar chart of count by <category column>". See a real chart rendered inline under the answer, with the chart code visible in "Show the work". The Charts panel is no longer labelled coming-soon.

### Phase 3 — One-shot auto-report

- **Goal:** One click produces an automatic report: a profile/overview of the file + key findings + a few charts, with no prompting.
- **Independent slices (parallel build units):**
  - `report-backend` (backend) — a `/sessions/{id}/report` endpoint that fans out a fixed set of profiling analyses (shape, dtypes, summary stats, top breakdowns) + a few charts concurrently, assembles them into a structured report. Deps: Phase 2 chart rendering.
  - `report-frontend` (frontend) — un-stub the "Generate report" button; render the structured report (sections + tables + charts). Deps: none — builds against the contract.
- **Key surfaces / files:** backend → `src/api/`, `src/analysis/report.py`, `src/graph/` (parallel fan-out). frontend → report view component.
- **Gate command:** `uv run alembic upgrade head && uv run pytest -q` (real Gemini) — `/report` over a fixture returns a profile section with correct shape/dtypes, ≥1 finding, and ≥1 chart.
- **How the user tests it (handoff seed):** Upload a CSV, click "Generate report". See an overview (rows/columns/types), summary stats, a couple of charts, and a few surfaced findings — no question typed.

### Phase 4 — Excel support + messy-data robustness

- **Goal:** Upload `.xlsx`/`.xls` files, and handle messy data (mixed types, missing values, weird headers) quietly with sensible defaults.
- **Independent slices (parallel build units):**
  - `excel-backend` (backend) — accept Excel in `/datasets` via `openpyxl`/`pandas.read_excel` (sheet selection default = first sheet); strengthen the loader to coerce/normalize messy columns silently. Deps: none beyond Phase 1.
  - `excel-frontend` (frontend) — accept Excel in the drop zone; remove the "CSV only" stub label. Deps: none.
- **Key surfaces / files:** backend → `src/analysis/store.py`, `src/api/`. frontend → drop-zone component.
- **Gate command:** `uv run alembic upgrade head && uv run pytest -q` — an `.xlsx` upload loads and answers a question correctly; a messy CSV (missing values + mixed types) answers without error.
- **How the user tests it (handoff seed):** Drag an `.xlsx` file in — it loads like a CSV. Ask a question over a messy file — it answers without asking any cleaning questions.

### Phase 5 — Auto-findings / insights

- **Goal:** Surface what is interesting or surprising in the data, not only what was literally asked — both proactively after upload and within answers.
- **Independent slices (parallel build units):**
  - `insights-backend` (backend) — a `/sessions/{id}/insights` analysis that runs a set of local heuristics + LLM-summarized findings (outliers, skew, notable correlations, dominant categories) from computed summaries only. Deps: Phase 1 analysis core.
  - `insights-frontend` (frontend) — un-stub the Insights panel; render the findings list. Deps: none.
- **Key surfaces / files:** backend → `src/analysis/insights.py`, `src/api/`. frontend → insights panel component.
- **Gate command:** `uv run alembic upgrade head && uv run pytest -q` (real Gemini) — `/insights` over a fixture with a known outlier/skew returns that finding.
- **How the user tests it (handoff seed):** Upload a CSV with an obvious quirk (an outlier, a dominant category). See the Insights panel populate with surfaced findings you did not explicitly ask for.
