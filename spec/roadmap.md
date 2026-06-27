# Roadmap

---

## What This Agent Does

This is a privacy-first, local data-analysis agent. A user points it at tabular data and asks a question in plain English ("Which region had the highest sales last quarter?"). The agent introspects the data, asks the LLM to translate the question into SQL, runs that SQL **locally** against an in-process DuckDB engine, and returns the answer as **both** a result table **and** a chart. All raw data stays on the machine: only the schema (table/column names + types) and a small sample of rows ever leave the box, sent to the LLM purely so it can reason about how to write correct SQL. The full dataset is never uploaded anywhere.

## Who Uses It

A data-literate-but-not-SQL-fluent analyst, operator, or founder who has a CSV/table of business data (sales, orders, signups, support tickets) and wants fast answers without writing SQL or pasting sensitive data into a cloud tool. They value privacy: the data must not leave their machine.

## Core Problem Being Solved

Today this person either (a) writes SQL by hand, (b) builds a spreadsheet pivot, or (c) pastes their data into a cloud chat tool — losing time, accuracy, or privacy. This agent replaces all three: ask in English, get a verified, locally-computed answer plus a chart, with only schema + a handful of sample rows ever leaving the machine.

## Success Criteria

- [ ] A user can open the app, type one plain-English question against the seeded sample dataset, and receive a generated SQL statement, a result table, and a chart — end-to-end against the real Gemini model.
- [ ] The generated SQL is shown to the user before/with the result (transparency).
- [ ] Only a single read-only `SELECT` is ever executed; any non-SELECT / DDL / DML / multi-statement output from the LLM is rejected and never run.
- [ ] The LLM receives only the schema (table + column names + types) and at most N sample rows (configurable, default 5) — never the full table.
- [ ] Every successful answer includes a chart spec (chart type + axes), not just a table.
- [ ] Invalid SQL, empty results, and LLM failures each produce a clear, non-crashing message in the UI.

## What This Agent Does NOT Do (Out of Scope)

- Does NOT send the full dataset to any third party — only schema + a small sample reach Gemini.
- Does NOT use any cloud data warehouse or third-party data service; the analytical engine is in-process DuckDB.
- Does NOT execute writes, DDL, DML, or multi-statement SQL — read-only single `SELECT` only.
- Does NOT (in v1) do joins across multiple user tables, saved dashboards, drill-down, or user accounts/auth.
- Does NOT replace the app-state store: run bookkeeping stays in the skeleton's SQLite/`RunRow`. DuckDB is only the analytical engine for user data.
- Does NOT do streaming/real-time data — it queries a static loaded dataset.

## Key Constraints

- **Privacy boundary (hard):** only schema + ≤ N sample rows may be sent to the LLM. The full dataset never leaves the process.
- **Read-only execution (hard):** exactly one `SELECT` statement runs against DuckDB; everything else is rejected before execution.
- **Large-data safety:** rely on DuckDB's columnar engine for scale; never materialise a full table into LLM context or into Python memory beyond the bounded result set.
- **LLM:** Gemini `gemini-2.5-flash`, key `AGENT_GEMINI_API_KEY` from `.env`. All gates/tests run against the real model.
- **Extend the skeleton in place** — replace the `transform_text` capability slot; never copy/rename modules.
- **Latency:** a single question should return within a few seconds on the seeded dataset (one LLM call + one local query).

## Phases of Development

> **Phase 1 is the smallest first-time-right user-testable win.** Backend is minimal but REAL on the one core path (real Gemini, real DuckDB, seeded dataset — no fake data on the tested path). Frontend is visually complete: real UI for the working path PLUS clearly-labelled NON-FUNCTIONAL stubs for everything coming later. Later phases wire those stubs into real functionality, one increment at a time.

### Phase 1 — Ask a question, get SQL + table + chart (seeded dataset)

- **Goal:** The user opens the app, types ONE plain-English question against a pre-seeded sample sales dataset already loaded in DuckDB, and sees (a) the generated SQL, (b) the result table, and (c) a chart — real end-to-end against real Gemini.
- **Independent slices (parallel build units):**
  - `nl-sql-backend` (backend) — DuckDB engine module + seeded sample dataset on startup; schema/sample introspection; `plan_sql` node (NL + schema + sample → SQL + chart_spec via Gemini); read-only single-SELECT validation + `execute_sql` node; `AgentState` extension; runner carries the structured payload as JSON in `RunRow.output_text`; `/runs` response shape; unit + integration tests. **deps: none.**
  - `analysis-ui` (frontend) — question box + submit; generated-SQL display block; result table; chart render (Recharts); error/empty states; clearly-labelled NON-FUNCTIONAL stubs for CSV upload, dataset switcher, saved dashboards, drill-down. Builds against the `spec/api.md` contract. **deps: none** (integration gate runs after both land).
- **Key surfaces / files:**
  - `nl-sql-backend` writes: `src/analytics/duckdb_engine.py` (new), `src/analytics/seed.py` (new), `src/analytics/sql_guard.py` (new), `src/graph/state.py`, `src/graph/nodes.py`, `src/graph/agent.py`, `src/graph/edges.py`, `src/graph/runner.py`, `src/prompts/plan_sql.md` (new; remove `transform.md`), `src/domain/run.py`, `src/api/runs.py`, `src/config/settings.py`, `pyproject.toml` (add `duckdb`), `tests/unit/test_sql_guard.py`, `tests/unit/test_duckdb_engine.py`, `tests/integration/test_nl_sql.py`.
  - `analysis-ui` writes: `frontend/src/app/page.tsx`, `frontend/src/app/components/*` (new), `frontend/package.json` (add `recharts`).
- **Gate command:** `uv run pytest tests/integration/test_nl_sql.py -q` (real Gemini via `AGENT_GEMINI_API_KEY` in `.env`; real in-process DuckDB with the seeded dataset).
- **How the user tests it (handoff seed):** Run `python agent.py --run`, open `http://localhost:8001/app/`. Type e.g. *"What were total sales by region?"* and submit. Expected: a generated SQL block (a single `SELECT ... GROUP BY region`), a result table of regions + totals, and a bar chart of the same. The CSV-upload button, dataset switcher, "Saved dashboards", and drill-down controls are visible but carry a "Coming soon" label — they are intentional stubs, not bugs.
- **Cross-cutting Definition of Done (every slice):** README delta (applied serially after the parallel slices land) · a structured log line per new operation · error handling + timeout on each new external call · a real behaviour-asserting test · an incremental drift check — see harness/patterns/phases.md Horizontal Axis.

### Phase 2 — Bring your own CSV (real upload)

- **Goal:** The user uploads their own CSV; it loads into DuckDB as the active dataset, and questions run against it (replacing the seeded-only path). Turns the Phase-1 upload stub into real functionality.
- **Independent slices (parallel build units):**
  - `upload-backend` (backend) — CSV upload endpoint; DuckDB ingest (`read_csv_auto`) into a per-session table; active-dataset tracking; schema/sample re-introspection over the uploaded table; tests. **deps: none** (extends Phase-1 engine module).
  - `upload-ui` (frontend) — wire the upload control to the new endpoint; show active-dataset name + column list; keep dataset switcher/dashboards/drill-down as labelled stubs. **deps: none** (builds against `spec/api.md` upload contract).
- **Key surfaces / files:**
  - `upload-backend` writes: `src/analytics/duckdb_engine.py`, `src/analytics/ingest.py` (new), `src/api/datasets.py` (new), `src/domain/dataset.py` (new), `src/config/settings.py`, `tests/unit/test_ingest.py`, `tests/integration/test_upload_query.py`.
  - `upload-ui` writes: `frontend/src/app/page.tsx`, `frontend/src/app/components/*`.
- **Gate command:** `uv run pytest tests/integration/test_upload_query.py -q` (real Gemini + real DuckDB ingest of a fixture CSV).
- **How the user tests it (handoff seed):** Run `python agent.py --run`, open the app, click "Upload CSV", pick a small CSV, then ask a question about its columns. Expected: the active dataset name + columns appear, and the question returns SQL + table + chart over the uploaded data. Dataset switcher / saved dashboards / drill-down remain labelled stubs.
- **Cross-cutting Definition of Done (every slice):** README delta (applied serially after the parallel slices land) · a structured log line per new operation · error handling + timeout on each new external call · a real behaviour-asserting test · an incremental drift check — see harness/patterns/phases.md Horizontal Axis.

### Phase 3 — Manage multiple datasets (switcher)

- **Goal:** The user can hold several loaded datasets at once and switch the active one; questions target the selected dataset. Turns the Phase-1/2 dataset-switcher stub into real functionality.
- **Independent slices (parallel build units):**
  - `dataset-mgmt-backend` (backend) — list/select/delete datasets; persist dataset registry (table name, source, columns) in SQLite; route the active dataset into the graph; tests. **deps: none** (extends Phase-2 ingest).
  - `dataset-switcher-ui` (frontend) — real dataset list + switcher; show active dataset; keep saved dashboards + drill-down as labelled stubs. **deps: none** (builds against `spec/api.md`).
- **Key surfaces / files:**
  - `dataset-mgmt-backend` writes: `src/db/models.py` (new `DatasetRow`), `alembic/versions/*` (new migration), `src/analytics/registry.py` (new), `src/api/datasets.py`, `src/domain/dataset.py`, `tests/integration/test_dataset_switch.py`.
  - `dataset-switcher-ui` writes: `frontend/src/app/page.tsx`, `frontend/src/app/components/*`.
- **Gate command:** `uv run pytest tests/integration/test_dataset_switch.py -q` (real Gemini + real DuckDB, two datasets loaded, query routed to the selected one).
- **How the user tests it (handoff seed):** Run `python agent.py --run`, upload two CSVs, switch between them, and confirm a question answers against whichever dataset is active. Saved dashboards + drill-down remain labelled stubs.
- **Cross-cutting Definition of Done (every slice):** README delta (applied serially after the parallel slices land) · a structured log line per new operation · error handling + timeout on each new external call · a real behaviour-asserting test · an incremental drift check — see harness/patterns/phases.md Horizontal Axis.

> Saved dashboards, joins across tables, and drill-down stay as labelled stubs beyond Phase 3 and are not scoped here; add them as new capabilities via `/zero-shot-build` when needed.
