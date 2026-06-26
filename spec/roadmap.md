# Roadmap

## What This Agent Does

The Data Analyst Agent is a web-based chat tool that lets users upload one or more CSV files in a browser and ask natural-language questions about their data. The agent interprets each question, executes analysis with pandas on the uploaded datasets (entirely on-server — no data is forwarded to third-party storage or analytics services), and returns structured answers with inline tables. Later phases add matplotlib chart images rendered inline in the chat and multi-file cross-dataset queries.

## Who Uses It

Data analysts, researchers, and anyone who needs quick, conversational insight from tabular data without writing code. They upload a CSV, type a question ("What is the average revenue by region?"), and get an answer with supporting data immediately.

## Core Problem Being Solved

Extracting insight from CSV files today requires either coding ability (pandas, SQL) or expensive BI tools. This agent closes that gap: users with no code experience can query their data in plain English and get back formatted answers with supporting tables and charts.

## Success Criteria

- [ ] A user can upload a CSV and receive a correct natural-language answer plus an inline data table from a single question within 30 seconds.
- [ ] The agent never forwards uploaded file contents to any third-party storage or analytics service.
- [ ] A session can hold multiple CSV uploads and queries; each query is answered against the correct dataset.
- [ ] Phase 2: a matplotlib chart is rendered inline in the chat for questions that produce a chart (e.g. bar, line, pie).
- [ ] Phase 3: a question explicitly referencing two datasets (by filename) returns a merged or joined analysis.

## What This Agent Does NOT Do (Out of Scope)

- No user authentication or multi-tenant isolation — sessions are ephemeral, identified by a server-generated session ID.
- No export of results to PDF, Excel, or other formats.
- No scheduled or automated query runs — all queries are user-initiated.
- No support for non-CSV tabular formats (Excel, Parquet, JSON arrays) in Phase 1–3.
- No vector-search-based semantic retrieval over row contents.
- No Plotly interactive charts in Phase 1 or Phase 2 (Plotly JSON is a post-Phase-2 optional extension, not in scope).
- No persistent storage of uploaded files beyond the server process lifetime.

## Key Constraints

- All CSV data stays on-server; no row-level data is sent to the Gemini API (only the schema + derived stats + the user's question are included in the LLM prompt).
- LLM provider: Google Gemini via `AGENT_GEMINI_API_KEY`.
- Default model: `gemini-2.5-flash` (env-configurable via `AGENT_LLM_MODEL`).
- Database: SQLite for session and dataset metadata (file path and column metadata only — not raw rows).
- All uploaded CSVs are stored on the server filesystem under `data/uploads/<session_id>/`; files and DB records persist across server restarts. No automatic cleanup in Phases 1–3.
- Backend runs on port 8001. Frontend is a Next.js static export served by FastAPI at `/app`.

---

## Phases of Development

### Phase 1 — Single CSV Upload + NL Question → Text Answer + Inline Table

- **Goal:** A user uploads one CSV, types a natural-language question, and gets a text answer with an inline data table — end-to-end on the first try, no charts, no multi-file.

- **Independent slices (parallel build units):**

  - `slice-a` (backend) — Extend `src/db/models.py` with `SessionRow` and `DatasetRow` tables; add Alembic migration; add `POST /sessions`, `POST /sessions/{id}/datasets`, `GET /sessions/{id}/datasets`, `POST /sessions/{id}/queries` endpoints; replace `transform_text` graph node with `load_dataset`, `analyze_query`, `extract_table`, `handle_error`, `finalize` nodes; extend `AgentState`; write analyst system prompt; write tests in `tests/test_phase1.py`. Deps: none.

  - `slice-b` (frontend) — Replace `frontend/src/app/page.tsx` with a two-panel chat UI: left panel has CSV upload dropzone + file list (real and functional), main panel has chat bubbles (real and functional for text + table), chart area shows a clearly-labelled stub "Charts coming in Phase 2", multi-file toggle shows a clearly-labelled stub "Multi-file queries coming in Phase 3". Deps: none (calls the new API endpoints from slice-a; if backend isn't built yet, shows loading state gracefully).

- **Key surfaces / files:**

  | Slice | Files owned |
  |-------|-------------|
  | slice-a (backend) | `src/db/models.py`, `src/graph/state.py`, `src/graph/nodes.py`, `src/graph/edges.py`, `src/graph/agent.py`, `src/graph/runner.py`, `src/api/sessions.py` (new), `src/api/__init__.py`, `src/prompts/analyst.md` (new), `src/domain/session.py` (new), `src/domain/dataset.py` (new), `src/domain/query.py` (new), `alembic/versions/<rev>_add_analyst_tables.py` (new), `tests/test_phase1.py` (new) |
  | slice-b (frontend) | `frontend/src/app/page.tsx`, `frontend/src/components/FilePanel.tsx` (new), `frontend/src/components/ChatPanel.tsx` (new), `frontend/src/components/MessageBubble.tsx` (new), `frontend/src/components/DataTable.tsx` (new), `frontend/src/lib/api.ts` (new) |

- **Gate command:**
  ```
  uv run alembic upgrade head && uv run pytest tests/test_phase1.py -v
  ```
  Runs against the real Gemini API (key from `.env`) and the SQLite DB configured in `AGENT_DATABASE_URL`.

- **How the user tests it:**
  1. `cd frontend && pnpm build` — build the Next.js static export.
  2. `uv run python -m src` — start the FastAPI server on port 8001.
  3. Open `http://localhost:8001/app/` in a browser.
  4. Upload any CSV file using the dropzone on the left panel. The file name and row count appear in the file list.
  5. Type a question about the data in the chat input (e.g. "What are the column names and how many rows are there?").
  6. Press Enter or click Send. An assistant message bubble appears with a text answer and a rendered inline table.
  7. **Real on the tested path:** upload, question, text answer, table.
  8. **Labelled stubs:** the chart area in each assistant bubble shows "Charts coming in Phase 2 — not yet active"; the multi-file toggle at the top of the left panel shows "Multi-file queries coming in Phase 3 — not yet active".

---

### Phase 2 — Inline Charts (matplotlib PNG, base64)

- **Goal:** Questions that call for a chart (bar, line, pie, scatter) produce a matplotlib PNG rendered inline in the chat alongside the text answer and table.

- **Independent slices (parallel build units):**

  - `slice-a` (backend) — Add `generate_chart` node to the LangGraph graph between `analyze_query` and `finalize`; update `AgentState` with `chart_b64` field; update the analyst prompt to optionally produce a chart-spec JSON block; execute matplotlib to render the chart and base64-encode the PNG; return `chart_b64` in the query response body; extend tests in `tests/test_phase2.py`. Deps: Phase 1 slice-a complete.

  - `slice-b` (frontend) — Wire the chart area (previously a stub) to render a `<img>` tag from `chart_b64` when present; keep the stub label absent when a real chart is shown; extend UI smoke test. Deps: Phase 1 slice-b complete.

- **Key surfaces / files:**

  | Slice | Files owned |
  |-------|-------------|
  | slice-a (backend) | `src/graph/nodes.py`, `src/graph/edges.py`, `src/graph/agent.py`, `src/graph/state.py`, `src/prompts/analyst.md`, `tests/test_phase2.py` |
  | slice-b (frontend) | `frontend/src/components/MessageBubble.tsx`, `frontend/src/components/ChartImage.tsx` (new) |

- **Gate command:**
  ```
  uv run pytest tests/test_phase2.py -v
  ```
  Runs against the real Gemini API and SQLite DB. At least one test uploads a CSV, asks a chart-producing question, and asserts `chart_b64` is a non-empty base64 string in the response.

- **How the user tests it:**
  1. Server already running from Phase 1 (or `uv run python -m src`).
  2. Upload a CSV with numeric columns (e.g. a sales dataset with Month and Revenue).
  3. Ask "Show me a bar chart of revenue by month."
  4. The assistant bubble shows: text answer + data table (as before) + a rendered bar chart image inline.
  5. **Labelled stub removed:** the "Charts coming in Phase 2" placeholder is gone.
  6. **Multi-file stub still present:** "Multi-file queries coming in Phase 3 — not yet active".

---

### Phase 3 — Multi-File Cross-Dataset Queries

- **Goal:** A session can hold multiple uploaded CSVs; the user can ask questions that reference two or more datasets by name, and the agent joins or merges them to answer the question.

- **Independent slices (parallel build units):**

  - `slice-a` (backend) — Update `load_dataset` node to accept a list of dataset IDs and load multiple DataFrames; update the analyst prompt to handle multi-DataFrame context (schema + summary for each); update `POST /sessions/{id}/queries` request body to accept `dataset_ids: list[str]`; write tests in `tests/test_phase3.py`. Deps: Phase 2 slice-a complete.

  - `slice-b` (frontend) — Wire the multi-file toggle (previously a stub) to let the user select which uploaded files to include in a query; show selected file badges in the chat input; update `api.ts` to send `dataset_ids` array. Deps: Phase 2 slice-b complete.

- **Key surfaces / files:**

  | Slice | Files owned |
  |-------|-------------|
  | slice-a (backend) | `src/graph/nodes.py`, `src/graph/state.py`, `src/graph/runner.py`, `src/api/sessions.py`, `src/domain/query.py`, `src/prompts/analyst.md`, `tests/test_phase3.py` |
  | slice-b (frontend) | `frontend/src/components/FilePanel.tsx`, `frontend/src/components/ChatPanel.tsx`, `frontend/src/lib/api.ts` |

- **Gate command:**
  ```
  uv run pytest tests/test_phase3.py -v
  ```
  Runs against the real Gemini API. At least one test uploads two CSVs, sends a cross-file question with both `dataset_ids`, and asserts the answer references data from both files.

- **How the user tests it:**
  1. Upload two CSV files (e.g. `orders.csv` and `customers.csv`).
  2. In the left panel, both files appear. The multi-file toggle is now active (no longer a stub).
  3. Select both files using the checkboxes in the file list.
  4. Ask "Join orders to customers on customer_id and show me the top 5 customers by total order value."
  5. The assistant bubble shows the text answer + inline table referencing both datasets.
  6. **All stubs removed:** both chart and multi-file surfaces are real.
