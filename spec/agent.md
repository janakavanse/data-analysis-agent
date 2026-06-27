# Agent

> This project uses LangGraph (it extends the skeleton's compiled `agentic_ai` graph). This file is REQUIRED and authoritative for the graph.

---

## Agent Architecture Pattern

| Pattern | Use when |
|---------|----------|
| **Graph (LangGraph)** | Multi-step pipeline with conditional edges. |

**Chosen:** Graph (LangGraph) — a short linear pipeline `plan_sql → execute_sql → finalize` with a conditional error branch. It extends the existing compiled `agentic_ai` graph in `src/graph/agent.py`, replacing the single `transform_text` node with two nodes.

---

## LLM Provider & Model

| Agent / Node | Provider | Model ID | Rationale |
|-------------|----------|----------|-----------|
| `plan_sql` | Gemini | `gemini-2.5-flash` | Fast, cheap NL→SQL; structured JSON output; the only LLM call in the graph |
| `execute_sql` | — | — | No LLM; pure local DuckDB execution |

**Fallback behaviour:** `plan_sql` wraps the Gemini call with a timeout and try/except; on failure (timeout, API error, unparseable reply) it sets `state["error"]` and routing sends the run to `handle_error`. No offline stub — tests call real Gemini via `.env`.

**Prompt strategy:** System prompt at `src/prompts/plan_sql.md` instructs the model to return **only** JSON `{ "sql": "<single read-only SELECT>", "chart_spec": { "chart_type": "...", "x": "...", "y": ["..."] } }`. The user message carries the question + the introspected schema (column names + types) + ≤ N sample rows. The prompt forbids non-SELECT statements and explains the chart_type enum.

---

## Tools & Tool Calling

This graph does not use LLM tool-calling; nodes call DuckDB directly. The "tools" are deterministic functions invoked by nodes.

| Function | Description | Inputs | Output | Side-effects |
|----------|-------------|--------|--------|--------------|
| `introspect(dataset)` | Read table schema + sample rows from DuckDB | dataset/table name | `{schema, sample_rows}` | none (read-only) |
| `is_read_only_select(sql)` | SQL guard | sql string | bool / raises | none |
| `run_select(sql)` | Execute bounded read-only SELECT | sql string | `{columns, rows}` | none (read-only connection) |

**Tool selection strategy:** rule-based — `plan_sql` always calls Gemini; `execute_sql` always guards then runs the SELECT.

**Tool failure handling:** any failure sets `state["error"]` → `handle_error`.

---

## Agent State

Extends `src/graph/state.py`. `AgentState` is a `TypedDict, total=False`; new fields are optional and populated progressively.

```python
class AgentState(TypedDict, total=False):
    # Identity
    run_id: str                  # set at initialisation by run_agent

    # Input
    input_text: str              # the NL question (existing key, reused)
    dataset_id: str | None       # active dataset; None → seeded "sales"

    # Pipeline data
    schema: list[dict]           # [{"column": str, "type": str}] from introspect
    sample_rows: list[list]      # ≤ N sample rows for LLM context
    sql: str                     # SELECT produced by plan_sql (after guard)
    chart_spec: dict             # {"chart_type","x","y":[...]}

    # Output
    columns: list[str]           # from execute_sql
    rows: list[list]             # from execute_sql (bounded)
    output_text: str             # JSON-serialized payload written by finalize (existing key)

    # Control
    status: str                  # "completed" | "failed"
    error: str | None            # set by any node on fatal failure
```

**Structured-payload carrier (decision):** the runner serializes the final payload `{"sql","columns","rows","chart_spec","error"}` to a JSON string and stores it in the existing `RunRow.output_text` column. No schema migration is needed in Phase 1 — `output_text` already exists and is `Text`. The API and UI both treat `output_text` as JSON. (`finalize` builds this JSON into `state["output_text"]`; `run_agent` writes it to `RunRow.output_text` unchanged.)

---

## Nodes / Steps

### `plan_sql`

**Reads from state:** `input_text`, `dataset_id`
**Writes to state:** `schema`, `sample_rows`, `sql`, `chart_spec`, `error`
**LLM call:** yes — Gemini `gemini-2.5-flash`, system prompt `prompts/plan_sql.md`, JSON output `{sql, chart_spec}`.

**External calls:**

| System | Operation | On Failure |
|--------|-----------|------------|
| DuckDB | introspect schema + sample for the active dataset | fatal (set error) |
| Gemini | NL + schema + sample → `{sql, chart_spec}` | fatal (set error) |

**Behaviour:** introspects the active dataset, builds the privacy-bounded context, calls Gemini, parses the JSON reply, runs the SQL guard on `sql` (reject non-SELECT → set error), and normalises `chart_spec` (default to `table` if invalid). Logs a structured event with `run_id` and the chosen `chart_type`.

### `execute_sql`

**Reads from state:** `sql`
**Writes to state:** `columns`, `rows`, `error`
**LLM call:** no.

**External calls:**

| System | Operation | On Failure |
|--------|-----------|------------|
| DuckDB | run guarded read-only SELECT, fetch bounded columns + rows | fatal (set error) |

**Behaviour:** re-asserts the SQL guard, executes the SELECT on a read-only connection, applies the row cap, and writes `columns`/`rows`. Empty result is success. Logs a structured event with `run_id` and row count.

### `finalize`

**Reads from state:** `sql`, `columns`, `rows`, `chart_spec`
**Writes to state:** `status="completed"`, `output_text` (JSON payload).
**Behaviour:** serializes `{sql, columns, rows, chart_spec, error:null}` to JSON into `output_text`.

### `handle_error`

**Reads from state:** `error`, `sql` (if present)
**Writes to state:** `status="failed"`, `output_text` (JSON payload with `error` set and best-effort `sql`).
**Behaviour:** serializes `{sql, columns:[], rows:[], chart_spec:null, error:<message>}` so the UI always receives a consistent JSON shape. Logs the error with `run_id`.

---

## Graph / Flow Topology

```
START
  │
  ▼
plan_sql ──(error)──► handle_error ──► END
  │
  ▼
execute_sql ──(error)──► handle_error ──► END
  │
  ▼
finalize ──► END
```

**Conditional edges:**

| Source node | Condition | Target |
|-------------|-----------|--------|
| `plan_sql` | `state.get("error")` | `handle_error` |
| `plan_sql` | else | `execute_sql` |
| `execute_sql` | `state.get("error")` | `handle_error` |
| `execute_sql` | else | `finalize` |

---

## Memory & Context

| Scope | Mechanism | What is stored |
|-------|-----------|----------------|
| **Within a run** | LangGraph state | question, schema, sample, sql, results, chart_spec |
| **Across runs** | SQLite `RunRow` | input_text, output_text (JSON payload), status, error |
| **Conversation** | none | each question is independent (no multi-turn chat in v1) |

**Context window management:** bounded by construction — only schema (names + types) + ≤ N sample rows go to the LLM, never full data.

---

## Human-in-the-Loop Checkpoints

None in v1. The user reviews the generated SQL in the UI after the fact (transparency), but execution is not gated on approval.

---

## Error Handling & Recovery

**Node-level:** each node catches its own exceptions; fatal errors set `state["error"]` and routing sends the run to `handle_error`.

**Graph-level (`handle_error`):** sets `status="failed"`, writes a consistent JSON `output_text` carrying the error and best-effort SQL, logs with `run_id`.

**Resume / retry strategy:** none in v1 — a failed run is terminal; the user re-asks.

**Partial failure:** none — the pipeline is plan→execute; either both succeed or the run fails gracefully.

---

## Observability

| Signal | What | Where |
|--------|------|-------|
| **Per node** | `run_id`, node name, outcome | structlog via `src/observability/events.py` |
| **LLM call** | model, latency, chart_type chosen, success/error | structured log |
| **SQL execution** | guard result, row count, latency | structured log |
| **Run outcome** | status, error if any | SQLite `RunRow` + structured log |

---

## Concurrency Model

- **Run isolation:** one run per request, scoped by `run_id`; DuckDB connection is process-global and used read-only for queries (safe for concurrent reads).
- **Parallel nodes within a run:** none — the pipeline is linear.
- **Checkpointing:** none (no human-in-the-loop, runs are short).

---

## Graph Assembly (`src/graph/agent.py`)

```python
graph = StateGraph(AgentState)

graph.add_node("plan_sql", plan_sql)
graph.add_node("execute_sql", execute_sql)
graph.add_node("finalize", finalize)
graph.add_node("handle_error", handle_error)

graph.set_entry_point("plan_sql")

graph.add_conditional_edges(
    "plan_sql",
    lambda s: "handle_error" if s.get("error") else "execute_sql",
    {"handle_error": "handle_error", "execute_sql": "execute_sql"},
)
graph.add_conditional_edges(
    "execute_sql",
    lambda s: "handle_error" if s.get("error") else "finalize",
    {"handle_error": "handle_error", "finalize": "finalize"},
)

graph.add_edge("finalize", END)
graph.add_edge("handle_error", END)

agentic_ai = graph.compile()
```
