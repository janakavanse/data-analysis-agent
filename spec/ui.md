# UI

---

## UI Type

Web app — a single-page analysis console served at `http://localhost:8001/app/` (Next.js static export served by FastAPI at `/app`). Single screen in v1.

## Views / Screens

### Screen: Analysis Console

**Purpose:** The user asks a plain-English question and reviews the generated SQL, a result table, and a chart.

**Key elements (REAL on the Phase-1 tested path):**
- **Question box** — a text input/textarea with a "Ask" / submit button. Placeholder suggests an example (e.g. *"What were total sales by region?"*).
- **Generated SQL block** — a monospaced, read-only display of the `SELECT` the agent ran (transparency).
- **Result table** — renders `columns` as headers and `rows` as the body.
- **Chart** — rendered with **Recharts** from `chart_spec`: `bar` → BarChart, `line` → LineChart, `pie` → PieChart, `scatter` → ScatterChart, `table` → no chart (table only). `x` is the category/axis field; `y[]` are the series.
- **Loading state** — submit shows a spinner / "Analysing…" while the request is in flight.

**Key elements (clearly-LABELLED NON-FUNCTIONAL stubs — must read "Coming soon" so they're never mistaken for bugs):**
- **Upload CSV** button — labelled "Coming soon" (becomes real in Phase 2).
- **Dataset switcher** — a disabled dropdown showing only "Sample sales data", labelled "Coming soon" (real in Phase 3).
- **Saved dashboards** — a placeholder panel labelled "Coming soon".
- **Drill-down** — a note on the chart/table area labelled "Coming soon".

**Actions available:**
- Type a question and submit → see SQL + table + chart.
- (Stubs are visible but inert.)

## Error States

- **LLM/SQL failure** (`status="failed"` or payload `error` set) → a red, non-crashing banner with the message (e.g. "The model did not return valid SQL — try rephrasing.").
- **Empty result** (`rows` empty, no error) → a neutral "No rows matched your question." message in place of the table/chart.
- **Network error** (server down) → "Network error — is the server running?" (matches the skeleton's existing handling).
- **Loading** → disabled inputs + "Analysing…" indicator.

The UI always decodes `data.output_text` as JSON and renders from `{sql, columns, rows, chart_spec, error}`; it falls back to the top-level `data.error` if present.

## Tech Stack

Next.js 15 (static export) + React 19 + Tailwind (skeleton default) + **Recharts** for charts. The frontend slice adds `recharts` to `frontend/package.json`. Built via `cd frontend && pnpm build` → `frontend/out`, served at `/app`.
