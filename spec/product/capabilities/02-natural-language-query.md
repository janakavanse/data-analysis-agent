# Capability: Natural-Language Query over a Dataset

## What It Does

Answers a natural-language question about a dataset by running a ReAct loop that inspects the schema,
generates a read-only SQL query, executes it on DuckDB via an MCP tool, and returns a plain-English
answer plus the result rows as a table.

## Inputs

| Input | Type | Source | Required |
|-------|------|--------|----------|
| question | string (NL) | user (chat turn) | yes |
| dataset id | uuid | conversation context | yes |
| conversation id | uuid | conversation context (for multi-turn) | yes |
| dataset schema + row sample | JSON | `file` records / DuckDB | yes (assembled into context) |

## Outputs

| Output | Type | Destination |
|--------|------|-------------|
| answer text | plain-English string | SSE stream → UI, persisted as a `message` |
| result table | rows + column headers (JSON) | SSE stream → UI, persisted with the turn |
| live trace | `action_history` (description + result per step) | SSE stream → UI |
| usage | tokens_input/output, estimated_cost_usd | `run` record |

## External Calls

| System | Operation | On Failure |
|--------|-----------|------------|
| Google Gemini | `plan_action` / answer synthesis via `init_chat_model` | LLM down → fatal → `handle_error`; run `error` set; `api_error("LLM_UNAVAILABLE", …)` |
| MCP `inspect_schema` tool | list columns/types + sample rows | tool error returned as a value → observed → retried |
| MCP `run_sql` tool (DuckDB) | execute a **read-only** SELECT | bad query → error value appended to `action_history` → loop retries (self-correction, [`../../engineering/patterns/react-agent.md`](../../engineering/patterns/react-agent.md)) |

## Business Rules

- The agent uses a **ReAct loop**, not a one-shot pipeline — it must run this loop per
  [`07-agent-graph.md`](../07-agent-graph.md) and [`react-agent.md`](../../engineering/patterns/react-agent.md).
- Generated SQL is **read-only**: validated (parse → reject non-SELECT/DDL/DML/multi-statement/
  dangerous functions) before execution. A rejected query is an error value the loop can observe and
  correct from — never executed.
- Only **schema + a small row sample** go to the LLM; answers come from running SQL on the full data.
- Every `action_history` entry carries a plain-English `description` (not just raw SQL) for the user
  trace.
- The loop is bounded by `max_agent_iterations`; exhaustion routes to `force_finalize`, which
  synthesises a best-effort answer from `action_history` (never a bare "I couldn't answer").

## Success Criteria

- [ ] For a known dataset, "total sales by region" returns an answer whose result table matches a
      hand-written reference SQL query (eval case).
- [ ] The loop runs **≥2 iterations** against the real model — at least one action executed, then the
      `finish` tool — verified by an eval/integration test.
- [ ] A non-read-only query the model might emit (e.g. `DELETE …`) is rejected by the safety check and
      never executes against DuckDB.
- [ ] Driving the loop past `max_agent_iterations` yields a substantive `force_finalize` answer, not a
      hard failure.
- [ ] Every step's `description` is present, non-empty, and not identical to the raw SQL `action`.
