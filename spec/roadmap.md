# Roadmap

> DataChat — a personal, locally-run CSV/Excel data-analysis agent. The HOW (stack, graph) is in [`architecture.md`](architecture.md) and [`agent.md`](agent.md); this file owns the WHAT, the WHO, and the phased plan.

---

## What This Agent Does

DataChat lets a single owner upload tabular data (CSV/Excel) and ask plain-English questions about it, getting back plain-English answers backed by real numbers, summary tables, and (in later phases) interactive charts. It is conversational and persistent — upload once, ask many follow-ups, and return to the same dataset across days. For each question it **plans** a multi-step analysis, **generates pandas code**, **runs that code locally against the full data**, and **synthesizes** a streamed answer — keeping a full audit trail of every run. Crucially, the data **never leaves the machine**: only the schema and a few sample rows go to the LLM to write the code; the full dataset is processed locally.

## Who Uses It

A single technical-enough owner-user (the "owner") analyzing their own private datasets on their own machine — frequently, across days. They are comfortable uploading a file and asking questions in English, want correct numbers they can act on, and care that their data stays local. No second user, no team, no auth.

## Core Problem Being Solved

Answering ad-hoc questions about a spreadsheet today means either writing pandas/SQL by hand or pasting private data into a cloud chatbot. DataChat removes both: the owner asks in English and gets a correct, auditable answer, while the data stays on their machine (only schema + samples reach the model). It replaces hand-written one-off analysis scripts and the privacy-risky copy-paste-into-ChatGPT workflow.

## Success Criteria

- [ ] Uploading a CSV auto-profiles it locally (columns, types, ranges, missing values) with no LLM call and no data leaving the machine.
- [ ] Asking a plain-English question returns a streamed plain-English answer whose numbers **match a direct pandas computation on the full file** (correctness — including on a file large enough that a sample-only answer would differ).
- [ ] Every answer shows its plan, its executed code (collapsible), key numbers, a summary table, and the per-question tokens + cost.
- [ ] Follow-up questions are answered with the context of prior turns, and a dataset's thread reloads across days.
- [ ] Every run (success or failure) is persisted and browsable; failures show the real error and the code that caused it.

## What This Agent Does NOT Do (Out of Scope)

- **Never sends the full dataset to the LLM** — only schema + sample rows + profile. (Hard privacy boundary.)
- No multi-tenant, no auth, no remote/hosted deployment — single local owner only.
- No write-back to source systems, no external integrations (standalone).
- No automated decisions/actions taken on the owner's behalf — it answers questions; the owner acts.
- No real-time/streaming data sources — static uploaded files only.
- No model fine-tuning or learning from feedback.
- Not optimized for raw speed — a reasonable wait is acceptable; correctness and transparency come first.

## Key Constraints

- **Privacy (hard):** full data stays local; only schema + ≤`AGENT_SAMPLE_ROWS` (default 20) sample rows + profile go to Gemini.
- **Provider:** Google Gemini via `google-genai`, key in `.env` as `AGENT_GEMINI_API_KEY`. Default model `gemini-2.0-flash` (low-cost), env-configurable.
- **Cost:** keep API spend low — cheap default model, schema-only context, no full-data uploads.
- **Data:** CSV/Excel incl. multi-sheet workbooks up to ~100 MB (`AGENT_MAX_UPLOAD_MB`). Excel/multi-sheet are later-phase.
- **Quality:** production-grade — the owner acts on the answers; correctness matters; full audit trail.
- **Local execution:** generated pandas runs in a restricted in-process sandbox (no network, no FS writes, timeout). See [`architecture.md`](architecture.md).
- **Tests/gates:** run against the **real Gemini API** using `.env`, against the production DB driver (SQLite — which here **is** production), never offline/stubbed.

## Phases of Development

> **Phase 1 is the smallest first-time-right user-testable win.** Its backend is minimal but REAL on the one core path (upload → profile → ask → plan → generate → execute-local → stream answer with numbers/table/code/cost, saved to history). Its frontend is visually complete: real UI for that path PLUS clearly-labelled NON-FUNCTIONAL stubs for everything coming later (charts, library, Excel, multi-file, daily total, confirm-gate) — a stub is never mistaken for a bug. Each later phase wires those stubs into real features. The agentic stack (LangGraph plan-execute graph) is wired REAL in Phase 1. All gates run against the real Gemini API via `.env`.
>
> Slices default to **independent** (concurrent build on disjoint paths); a dependency is declared only where one slice truly needs another's output.

### Phase 1 — Upload, Profile & Ask (the core analysis loop)

- **Goal:** The owner uploads a single CSV, sees an auto-profile, asks one plain-English question, and gets a streamed plain-English answer with key numbers, a summary table, the executed code (collapsible), and the per-question tokens + cost — backed by pandas running locally on the full data, with the run saved to browsable history. Follow-ups use conversation memory.
- **Independent slices (parallel build units):**
  - `db-schema` (backend) — `datasets` + `messages` SQLAlchemy models and the Alembic revision (drops `runs`). **deps: none.**
  - `execution` (backend) — local pandas profiling (`src/execution/profile.py`) + safe sandbox (`src/execution/sandbox.py`, restricted namespace + timeout). **deps: none.**
  - `llm-usage` (backend) — extend `LLMClient`/`GeminiProvider` to return token usage + streaming; cost computation helper. **deps: none.**
  - `agent-graph` (backend) — the plan-execute graph: state, nodes (profile_context, plan, generate_code, execute_local, synthesize, finalize, handle_error), edges, runner, prompts (`src/prompts/{plan,generate_code,synthesize}.md`). **deps: execution + llm-usage (consumes their interfaces — declare as a soft dependency; build to the documented signatures so it can develop in parallel and integrate last).**
  - `api-routes` (backend) — `POST /api/datasets` (upload+profile), `POST /api/datasets/{id}/ask` (SSE), `GET /api/datasets/{id}`, `GET /api/datasets/{id}/messages`, `GET /api/messages/{id}`, stubbed `GET /api/datasets`. **deps: db-schema + agent-graph (integration point).**
  - `frontend` (frontend) — empty state + upload, chat panel with SSE streaming, profile/observability panel, history browser, starter questions, and all labelled stubs (charts, library, Excel, daily total, follow-ups). **deps: none (builds against the `api.md` contract; integrates last).**
  - `e2e` (frontend) — Playwright `tests/e2e/` smoke for upload → ask → streamed answer with numbers/table/code/cost. **deps: frontend + api-routes (runs against the live app).**
- **Key surfaces / files:**
  - backend: `src/db/models.py`, `alembic/versions/0002_datachat.py`, `src/execution/profile.py`, `src/execution/sandbox.py`, `src/llm/client.py`, `src/llm/providers/gemini.py`, `src/graph/{state,nodes,agent,edges,runner}.py`, `src/prompts/{plan,generate_code,synthesize}.md`, `src/api/datasets.py`, `src/api/__init__.py`, `src/config/settings.py`, `src/domain/*.py`
  - frontend: `frontend/src/app/page.tsx`, `frontend/src/app/components/*`, `frontend/src/lib/sse.ts`, `tests/e2e/datachat.spec.ts`
  - tests: `tests/unit/*`, `tests/integration/test_analysis.py` (real Gemini), `tests/fixtures/*.csv`
- **Gate command:** `uv run alembic upgrade head && uv run pytest && (cd frontend && pnpm build) && uv run python -m src &` then `npx playwright test tests/e2e/ --reporter=line` (real Gemini via `.env`; SQLite is production here). The integration test must include a **large fixture** (≥ tens of thousands of rows) where a 20-row sample and the full file give **different** aggregates, and assert the streamed answer matches the **full-file** computation.
- **How the user tests it (handoff seed):** `cd frontend && pnpm build`, then `uv run python -m src`; open `http://localhost:8001/app/`. Upload a CSV → see the profile populate (columns/types/missing/ranges) in the right panel. Ask "What is the average of <a numeric column> by <a category column>?" → watch the step indicator advance, the answer stream in, the key numbers + summary table appear, expand "Show code" to see the pandas, and read the tokens + cost line. Ask a follow-up ("now just for <one category>") → it uses prior context. Reload the page → the thread is still there. Expand a history row → full plan/code/result. **Labelled stubs (NOT bugs):** the "Charts coming soon" card, the greyed library sidebar + "Save cleaned dataset", the greyed "daily total — coming soon", AI follow-up suggestions, and `.xlsx` upload being rejected with "coming in a later phase".

### Phase 2 — Charts & Richer Output

- **Goal:** Answers gain interactive charts (and a dashboard when multiple are useful), and each answer is followed by 2–3 AI-suggested follow-up questions. Wires the "Charts coming soon" and follow-up-suggestion stubs into real features.
- **Independent slices (parallel build units):**
  - `chart-node` (backend) — a chart-spec step (extend `synthesize` or add a `propose_chart` node) producing a `chart_spec_json`; add the `chart_spec_json` column (Alembic revision). **deps: none.**
  - `suggestions` (backend) — generate 2–3 follow-up questions from the result + profile; add to the `ask` `done` event. **deps: none.**
  - `frontend-charts` (frontend) — render charts (e.g. Recharts) from `chart_spec_json`; multi-chart dashboard layout; render suggested follow-ups as clickable chips. **deps: chart-node + suggestions (consumes their output shapes — build to contract).**
  - `e2e` (frontend) — Playwright assertion that a chart renders and a follow-up chip is clickable. **deps: frontend-charts.**
- **Key surfaces / files:** backend `src/graph/nodes.py`, `src/prompts/chart.md`, `src/prompts/suggest.md`, `alembic/versions/0003_charts.py`, `src/api/datasets.py`; frontend `frontend/src/app/components/Chart*.tsx`, `frontend/src/app/components/Suggestions.tsx`; `tests/e2e/charts.spec.ts`.
- **Gate command:** `uv run pytest && (cd frontend && pnpm build) && uv run python -m src &` then `npx playwright test tests/e2e/ --reporter=line` (real Gemini via `.env`).
- **How the user tests it (handoff seed):** ask a question whose answer suits a chart ("revenue by month") → a chart renders alongside the table; 2–3 follow-up chips appear; clicking one asks it. Stubs remaining: library sidebar, Excel, multi-file, daily total, confirm-gate.

### Phase 3 — Dataset Library & Persistent Threads

- **Goal:** A persistent multi-dataset library (sidebar list across days) becomes real; the owner can switch datasets, each keeps its own thread, and can save a derived/cleaned dataset back to the library as a new item (originals untouched). Wires the library-sidebar and "Save cleaned dataset" stubs.
- **Independent slices (parallel build units):**
  - `library-api` (backend) — real `GET /api/datasets` (list all), `DELETE /api/datasets/{id}`, `POST /api/datasets/{id}/derive` (save a derived dataset); add `derived_from_id` column (Alembic revision). **deps: none.**
  - `derive-logic` (backend) — produce + persist a derived dataset (e.g. last result or a cleaning op) as a new `datasets` row + file; profile it. **deps: library-api (shares the new column/route — declare).**
  - `frontend-library` (frontend) — real sidebar list, dataset switching (loads that dataset's thread), delete, and a working "Save cleaned dataset" action. **deps: library-api.**
  - `e2e` (frontend) — Playwright: upload two datasets, switch between them, verify independent threads. **deps: frontend-library.**
- **Key surfaces / files:** backend `src/api/datasets.py`, `src/db/models.py`, `alembic/versions/0004_library.py`, `src/execution/derive.py`; frontend `frontend/src/app/components/Sidebar.tsx`; `tests/e2e/library.spec.ts`.
- **Gate command:** `uv run pytest && (cd frontend && pnpm build) && uv run python -m src &` then `npx playwright test tests/e2e/ --reporter=line` (real Gemini via `.env`).
- **How the user tests it (handoff seed):** upload two CSVs → both appear in the sidebar; switch between them and confirm each has its own conversation; save a cleaned/derived dataset → it appears as a new library item with the original untouched. Stubs remaining: Excel/multi-sheet, multi-file join, daily total, confirm-gate.

### Phase 4 — Excel & Multi-file Joins

- **Goal:** Upload Excel (`.xlsx`) including multi-sheet workbooks (each sheet selectable/loadable), and ask questions that join or compare multiple loaded files. Wires the Excel-rejection and multi-file stubs.
- **Independent slices (parallel build units):**
  - `excel-ingest` (backend) — `openpyxl`-backed `.xlsx`/multi-sheet read + profile; add `sheet_name`/`source_kind` handling (Alembic revision). **deps: none.**
  - `multi-file-graph` (backend) — let the agent reference multiple datasets in one question (context = multiple schemas; code joins multiple frames in the sandbox). **deps: excel-ingest (shares ingest shape — soft).**
  - `frontend-multifile` (frontend) — `.xlsx` upload + sheet picker; UI to select 2+ datasets for a cross-file question. **deps: excel-ingest + multi-file-graph.**
  - `e2e` (frontend) — Playwright: upload a 2-sheet workbook, ask a cross-sheet/file question. **deps: frontend-multifile.**
- **Key surfaces / files:** backend `src/execution/profile.py`, `src/execution/sandbox.py`, `src/graph/nodes.py`, `alembic/versions/0005_excel.py`; frontend sheet picker + multi-select components; `tests/e2e/excel.spec.ts`.
- **Gate command:** `uv run pytest && (cd frontend && pnpm build) && uv run python -m src &` then `npx playwright test tests/e2e/ --reporter=line` (real Gemini via `.env`).
- **How the user tests it (handoff seed):** upload a multi-sheet `.xlsx` → pick a sheet, profile loads; upload a second file and ask a question that joins/compares the two → correct joined answer. Stubs remaining: daily total, confirm-gate.

### Phase 5 — Daily Cost Total & Confirm-Before-Heavy-Work

- **Goal:** A running daily cost total in the header, and a clarification gate that pauses to confirm before heavy/expensive multi-step work (otherwise best-guess with assumptions flagged). Wires the last two stubs — every capability now real.
- **Independent slices (parallel build units):**
  - `cost-api` (backend) — `GET /api/cost/today` aggregating `messages.cost_usd` for the day. **deps: none.**
  - `confirm-gate` (backend) — a plan-cost estimate + an optional human-in-the-loop pause before `generate_code` (the `ask` stream emits a `confirm` event; a `confirm` flag resumes). **deps: none.**
  - `frontend-cost-confirm` (frontend) — live daily total in the header; a confirm modal on the `confirm` event. **deps: cost-api + confirm-gate.**
  - `e2e` (frontend) — Playwright: trigger a heavy question → confirm modal → approve → answer; daily total increments. **deps: frontend-cost-confirm.**
- **Key surfaces / files:** backend `src/api/cost.py`, `src/graph/nodes.py`, `src/graph/edges.py` (confirm edge), `src/api/datasets.py`; frontend header total + confirm modal; `tests/e2e/cost_confirm.spec.ts`.
- **Gate command:** `uv run pytest && (cd frontend && pnpm build) && uv run python -m src &` then `npx playwright test tests/e2e/ --reporter=line` (real Gemini via `.env`).
- **How the user tests it (handoff seed):** watch the daily total rise as questions are asked; ask a deliberately heavy/expensive multi-step question → a confirm prompt appears → approving runs it, declining cancels cleanly. No stubs remain — every capability is real.
