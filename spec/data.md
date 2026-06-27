# Data Model

---

## Storage Technology

Two distinct stores, by design:

- **App-state:** SQLite + SQLAlchemy 2.0 (skeleton default, `sqlite:///./data/agent.db`). Holds run bookkeeping (`RunRow`) and, from Phase 3, the dataset registry (`DatasetRow`).
- **User-data analytical engine:** **DuckDB, in-process** (file at `data/analytics.duckdb`, configurable via settings). Holds the user's tabular data and runs all read-only `SELECT` queries. This is the privacy boundary: the full data lives here and never leaves the machine.

> **Assumed:** DuckDB persists to a file (`data/analytics.duckdb`) rather than `:memory:`, so the seeded/loaded dataset survives across requests within a server session. A single process-global connection is opened; query execution uses read-only access.

## Entities

### Entity: RunRow (app-state, SQLite — existing skeleton model)

One row per question/answer run. Unchanged structurally; `output_text` now carries the JSON analysis payload (see `spec/api.md`).

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | str (uuid) | yes | Primary key |
| status | str | yes | `pending` → `completed` / `failed` |
| input_text | str | no | The NL question |
| output_text | str (JSON) | no | Serialized `{sql, columns, rows, chart_spec, error}` |
| error_message | str | no | Error text on failure |
| created_at / updated_at | timestamp | yes | Bookkeeping |

### Entity: sales (user-data, DuckDB — SEEDED sample dataset for Phase 1)

A small, instantly-relatable, chart-friendly orders table seeded into DuckDB on startup so any reasonable NL question yields a chartable result.

| Column | Type | Description |
|--------|------|-------------|
| order_id | INTEGER | Synthetic order id |
| order_date | DATE | Date of the order (spread across a few recent months) |
| region | VARCHAR | One of `North, South, East, West` |
| product | VARCHAR | One of a handful of product names (e.g. `Widget, Gadget, Gizmo, Doohickey`) |
| quantity | INTEGER | Units ordered (small positive ints) |
| amount | DOUBLE | Line total in currency units |

**Seed shape:** ~200 rows generated deterministically (fixed seed) so tests are stable, spanning all regions/products and multiple months — enough variety that questions like "total sales by region", "monthly sales trend", "top products by revenue" all return non-trivial, chartable results.

**Seeding:** on startup, the FastAPI `_lifespan` hook in `src/api/__init__.py` (alongside the existing `init_db()` call) invokes `src/analytics/seed.py`, which creates the `sales` table in DuckDB if absent and inserts the deterministic rows. Idempotent — re-running does not duplicate. The integration test seeds the same way via a fixture so the gate runs without `agent.py`.

### Entity: DatasetRow (app-state, SQLite — Phase 3 only)

Registry of loaded datasets. Introduced in Phase 3 (with an Alembic migration).

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| id | str (uuid) | yes | Primary key |
| name | str | yes | Display name (e.g. CSV filename) |
| table_name | str | yes | DuckDB table name for this dataset |
| columns_json | str (JSON) | yes | Cached schema (column names + types) |
| is_active | bool | yes | Whether this is the active dataset |
| created_at | timestamp | yes | When loaded |

## Schema introspection + sample extraction (LLM context)

For the active dataset, the engine builds the bounded LLM context:
- **Schema:** `DESCRIBE <table>` (or DuckDB `information_schema`) → list of `{column, type}`.
- **Sample:** `SELECT * FROM <table> LIMIT N` where N is `sample_row_count` (default 5, configurable). Only these N rows + the schema are sent to Gemini. **The full table is never sent.**

## Read-only execution guarantee

- Generated SQL passes the SQL guard (`src/analytics/sql_guard.py`) — single statement, must start with `SELECT`/`WITH`, no DDL/DML/multi-statement keywords — before execution.
- Execution uses a read-only DuckDB access path; results are capped (default 1000 rows) to bound memory and the UI payload.

## Relationships

In v1 there is a single user table (`sales`, or one uploaded table from Phase 2). No cross-table joins in v1. `RunRow` and `DatasetRow` are independent app-state tables (no FK between runs and datasets in v1).

## Data Lifecycle

- **RunRow:** created per question, updated to completed/failed at the end of the run. Retained (local history); no auto-purge in v1.
- **DuckDB data:** seeded on startup (Phase 1); from Phase 2 a CSV upload creates/replaces a user table; from Phase 3 datasets can be added/removed via the registry.

## Sensitive Data

The user's tabular data may contain PII/business-sensitive values — this is exactly why it stays in local DuckDB. The privacy contract: only schema (column names + types) + ≤ N sample rows reach Gemini. No raw full data and no full result sets leave the machine. No secrets are stored in `RunRow`; the Gemini key lives only in `.env` (`AGENT_GEMINI_API_KEY`).
