# Capability: NL → SQL Analysis

## What It Does
Translates a plain-English question about the active dataset into a single read-only SQL `SELECT`, runs it locally against DuckDB, and returns the result table plus a chart spec.

## Inputs
| Input | Type | Source | Required |
|-------|------|--------|----------|
| question | string | `POST /runs { input_text }` (the NL question) | Yes |
| dataset_id | string | request (optional); defaults to the active/seeded dataset | No |
| schema | list of {column, type} | DuckDB introspection of the active table | Yes (derived) |
| sample_rows | list of rows (≤ N, default 5) | DuckDB `SELECT ... LIMIT N` over the active table | Yes (derived) |

## Outputs
| Output | Type | Destination |
|--------|------|-------------|
| sql | string (single SELECT) | `RunRow.output_text` JSON → `/runs` response → UI SQL block |
| columns | list of string | same | UI table header |
| rows | list of list (cells) | same | UI table body |
| chart_spec | object `{chart_type, x, y[]}` | same | UI chart (Recharts) |
| error | string or null | same | UI error message |

## External Calls
| System | Operation | On Failure |
|--------|-----------|------------|
| Gemini `gemini-2.5-flash` | NL + schema + sample → `{sql, chart_spec}` JSON | set `error`, route to `handle_error`; UI shows graceful copy |
| DuckDB (in-process) | introspect schema/sample; run read-only SELECT | set `error` on query failure; UI shows graceful copy |

## Business Rules
- Only the **schema (column names + types)** and **≤ N sample rows** (default 5, configurable) are sent to the LLM — never the full table.
- The LLM must return JSON `{ "sql": "...", "chart_spec": { "chart_type": "...", "x": "...", "y": ["..."] } }`.
- `sql` MUST be a single read-only statement starting with `SELECT` (or `WITH ... SELECT`). Reject if it contains multiple statements (`;` separating statements), or any of: `INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, ATTACH, COPY, PRAGMA, INSTALL, LOAD, REPLACE, TRUNCATE`. Rejection sets `error` and the SELECT is never executed.
- `chart_type` ∈ `{ bar, line, pie, scatter, table }`. `x` is a column name; `y` is a list of one or more numeric column names. If the LLM omits or returns an invalid chart spec, default to `chart_type = "table"`.
- Result set is bounded — if the SELECT lacks a LIMIT, the engine caps returned rows (default cap configurable, e.g. 1000) to protect memory and the UI.
- Empty result set is a valid, non-error outcome: return empty `rows`, `chart_spec.chart_type = "table"`, and the UI shows "No rows matched."

## Success Criteria
- [ ] A question against the seeded `sales` table returns a single `SELECT`, a non-empty `columns`/`rows` set, and a `chart_spec` — verified end-to-end against real Gemini in `tests/integration/test_nl_sql.py`.
- [ ] A unit test confirms the SQL guard rejects `DROP TABLE sales`, `INSERT ...`, `SELECT 1; DELETE ...`, and `UPDATE ...`, and accepts a plain `SELECT ... GROUP BY ...` and a `WITH ... SELECT ...`.
- [ ] The LLM context built for a question contains schema + at most N sample rows and excludes the full table (unit test on the context builder).
- [ ] An LLM reply that is not valid JSON, or returns a non-SELECT, yields `error` set and a graceful UI message — never a crash and never an executed non-SELECT.
- [ ] An empty result set renders the "No rows matched" state rather than an error.
