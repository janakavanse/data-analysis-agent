# Capability 2: Natural Language Query (Iterative MCP Tool-Call ReAct Loop)

## Overview

The agent answers a user's natural language question by acting as an **MCP client**: it discovers the tools exposed by each attached data source's MCP server and invokes them iteratively until it has enough information to give a confident final answer.

This is a **ReAct loop**: the LLM reasons, selects an MCP tool to call, observes the result, and repeats until it emits `FINAL ANSWER:`. Tools are not hardcoded — they are discovered at runtime via `list_tools()`, making the loop reusable across any data-source type that ships an MCP server.

The session's MCP pool (one server per source) is built **once on the session's first query** and reused by every later query (see `07-agent-graph.md` and capability 3). The agent also has **durable per-session memory** (LangGraph `SqliteSaver`, `thread_id = session_id`): prior Q&A turns are fed into each new query's prompt so follow-up questions work.

## User-Facing Behaviour

1. User types a natural language question in a session.
2. The app acquires the session's MCP pool (building it on first use, reusing it after) and runs the ReAct loop.
3. The agent runs one or more MCP tool calls (each a read-only DuckDB `SELECT` over a Parquet file), with the prior conversation available as context.
4. When the LLM determines it has enough information, it returns a plain-text final answer.
5. The session page shows the answer inline with: iteration count, token usage, cost estimate, and a collapsible tool-call trace.

## Agent Loop (ReAct)

The per-query loop is just plan → execute → finalize; the pool is acquired **before** the graph runs.

```
SessionPoolManager.acquire(session_id)   ← lazy build (first query) / reuse; outside the graph
    │
    ▼
plan_action ◄─────────────────────────────────────────┐   (reads tools/schema from the manager
    │                                                  │    + the durable `conversation` memory)
    ├── (FINAL ANSWER:) → finalize → END               │
    │                                                  │
    └── (tool call JSON) → execute_action ─────────────┘
                               │  (MCP client call_tool → DuckDB SELECT)
                               └── (isError) → plan_action (self-correction)
                               └── (max iterations) → handle_error
```

## LLM Protocol

### Tool call format (LLM output when it wants to act)

```json
{"tool": "ds_2024_sales__run_query", "arguments": {"query": "SELECT ..."}}
```

The `tool` value is the exact namespaced tool name advertised in the prompt (`<table_name>__run_query`).

### Termination format (LLM output when it's done)

```
FINAL ANSWER: <the complete answer in plain text>
```

## Termination Conditions

| Condition | Action |
|-----------|--------|
| LLM emits `FINAL ANSWER: ...` | Extract answer, route to `finalize` |
| DuckDB SQL error / non-SELECT SQL | MCP tool returns `isError=True`; append to history, loop back to `plan_action` |
| Unknown tool name | Recoverable; pool returns a valid-tool-list message, loop back |
| Malformed (non-JSON) LLM tool call | Recoverable; ask the LLM to reformat, loop back |
| Iteration count ≥ `max_agent_iterations` (default 10) | Route to `handle_error` |
| LLM call fails / missing Parquet / MCP session failure | Fatal — route to `handle_error` |

## Tool Execution Rules (`run_query` via DuckDB)

- Only `SELECT` statements are allowed. A non-SELECT statement is returned as a recoverable `isError=True` result (never executed).
- DuckDB queries the Parquet file directly through a read-only view named `<table_name>` (the same name advertised to the LLM).
- Results are capped at 200 rows (`DATAANALYSIS_MCP_MAX_RESULT_ROWS`) and returned as compact CSV.
- DuckDB provides native `STDDEV`/`VARIANCE`/`MEDIAN`/`QUANTILE` — no custom aggregates needed.

## Prompt Protocol

### `plan_action` prompt (each iteration)

```
You are a data-analysis agent operating in a ReAct loop.

Conversation so far (prior questions and answers in this session):
[1] Q: What were total sales? → A: 60.

Available tools (call a tool by its exact name):

Tool: ds_2024_sales__run_query  (queries table: ds_2024_sales)
  Description: <capability_description>
  Parameters: {"query": {"type": "string", "description": "A valid SQL SELECT statement."}}

SQL dialect: DuckDB. Only SELECT statements are permitted.

Dataset schema:
  Table: ds_2024_sales — Columns: <columns>

User question: <question>

<if history:>
Previous tool calls and results:
[1] tool: ds_2024_sales__run_query
    arguments: {"query": "SELECT ..."}
    result: ...
</end if>

Decide your next step. Respond with EXACTLY ONE of:
1. {"tool": "<name>", "arguments": {"query": "SELECT ..."}}
2. FINAL ANSWER: <your complete answer here>
```

## State Fields

| Field | Type | Scope | Description |
|-------|------|-------|-------------|
| `conversation` | `list[dict]` | durable (memory) | Prior turns `{"question","answer"}`; reducer-appended, restored by the checkpointer |
| `action_history` | `list[dict]` | per-query scratch | `{"tool","arguments","result","is_error"}` |
| `iteration_count` | `int` | per-query scratch | Tool calls executed this query |
| `llm_response` | `str` | per-query scratch | Raw LLM output from last `plan_action` |

Tools/schema are read from the `SessionPoolManager` (by `session_id`), not stored in state. The MCP servers + DuckDB connections live in that manager. Per-query scratch is reset via the `ainvoke` input each query; `conversation` accumulates across queries via its reducer + the `SqliteSaver` checkpointer.

## Persistence

| Field | Stored in DB |
|-------|-------------|
| `answer` | Yes (`query_records.answer`) |
| `iteration_count` | Yes (`query_records.iteration_count`) |
| `action_history` | Yes (`query_records.query_history_json`) — displayed as the agent reasoning trace |
| Token counts, cost | Yes (existing columns on `query_records`) |

## Out of Scope (this capability)

- Streaming intermediate results to the browser (deferred)
- Chart generation from tool results (Capability 5)
- Cross-source SQL joins in a single query (each MCP server wraps one Parquet; combine across tool calls)
- Non-CSV data source types (future MCP servers)
