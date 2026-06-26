# Agent

## Agent Architecture Pattern

**Chosen:** Graph (LangGraph) — the query pipeline has clearly ordered steps with a conditional error edge and a Phase 2 extension point (chart generation). The linear sequence with one conditional branch is a minimal `StateGraph` — simpler than a tool-use loop (no dynamic tool selection needed) and does not require multi-agent overhead.

Patterns applied from `harness/patterns/agentic-ai.md`:
- **Prompt Chaining** (#1) — `load_dataset` → `analyze_query` → `extract_table` → `finalize` is a fixed ordered chain.
- **Tool Use** (#5) — pandas DataFrame operations are in-process "tools" called deterministically by nodes.
- **Exception Handling and Recovery** (#12) — every node wraps its logic; errors route to `handle_error`.

---

## LLM Provider & Model

| Node | Provider | Model ID | Rationale |
|------|----------|----------|-----------|
| `analyze_query` | Google Gemini | `gemini-2.5-flash` (env: `AGENT_LLM_MODEL`) | Single node that needs strong instruction-following to produce a structured text answer with an embedded table spec; Flash balances quality and latency well for tabular Q&A |

**Fallback behaviour:** The Gemini API call is wrapped in a try/except inside `analyze_query`. On any exception (4xx, 5xx, timeout), `state["error"]` is set and the graph routes to `handle_error`, which marks the run as "failed" and returns the error message to the API caller. No retry in Phase 1 (retry/back-off is a Phase 4 concern per the roadmap).

**Prompt strategy:** System prompt (loaded from `src/prompts/analyst.md`) + user turn containing:
- Column names and dtypes of the active DataFrame(s)
- Output of `df.describe()` (numeric stats)
- `df.head(5)` formatted as Markdown table
- The user's question

The prompt instructs Gemini to respond with:
1. A plain-text answer paragraph.
2. (Optional) A fenced code block tagged `table_json` containing a JSON array of objects — one object per result row — when the answer includes tabular data.
3. (Phase 2) A fenced code block tagged `chart_spec` containing a JSON object describing the chart type, x/y columns, and title.

---

## Tools & Tool Calling

The agent does not use LLM-driven dynamic tool selection. Each node calls its own deterministic in-process function. There are no registered LangGraph tools.

| Operation | Node | Side-effects |
|-----------|------|--------------|
| Read CSV file from disk | `load_dataset` | None (read-only) |
| Compute schema + stats (`df.describe()`, `df.head(5)`) | `load_dataset` | None |
| Call Gemini API | `analyze_query` | External API call |
| Parse `table_json` block from answer text | `extract_table` | None |
| Generate matplotlib PNG, encode base64 (Phase 2) | `generate_chart` | None (in-memory) |
| Write `RunRow` to SQLite | `finalize` via runner | DB write |

---

## Agent State

```python
class AgentState(TypedDict, total=False):
    # Identity
    run_id: str            # set by runner before graph invocation
    session_id: str        # set by runner; identifies the browser session
    dataset_id: str        # set by runner; primary dataset being queried
    dataset_ids: list[str] # set by runner (Phase 3 multi-file); may be empty in Ph1-2

    # Input
    question: str          # the user's natural-language question

    # Pipeline data — populated progressively by nodes
    dataframe_context: str # set by load_dataset: schema + stats + head as Markdown string
    answer_text: str       # set by analyze_query: Gemini's prose answer
    table_data: list[dict] | None  # set by extract_table: parsed rows, or None
    chart_b64: str | None  # set by generate_chart (Phase 2): base64 PNG, or None

    # Control
    error: str | None      # set by any node on fatal failure; routes to handle_error
```

---

## Nodes / Steps

### `load_dataset`

**Reads from state:** `session_id`, `dataset_id` (Phase 3: `dataset_ids`)

**Writes to state:** `dataframe_context`, or `error` on failure

**LLM call:** No

**External calls:**

| System | Operation | On Failure |
|--------|-----------|------------|
| Filesystem | Read CSV from `data/uploads/<session_id>/<file_path>` via pandas `read_csv` | Fatal — set `error`, route to `handle_error` |
| SQLite | Fetch `DatasetRow` file path by `dataset_id` | Fatal — set `error`, route to `handle_error` |

**Behaviour:** Fetches the dataset record from SQLite to get the file path, reads the CSV with pandas, computes schema + `.describe()` + `head(5)` as a Markdown string, and writes it to `state["dataframe_context"]`. In Phase 3, loads multiple DataFrames by iterating `dataset_ids` and concatenates their contexts.

---

### `analyze_query`

**Reads from state:** `dataframe_context`, `question`

**Writes to state:** `answer_text`, or `error` on failure

**LLM call:** Yes — `GeminiProvider.call_model(user_turn, system=analyst_prompt)`

**External calls:**

| System | Operation | On Failure |
|--------|-----------|------------|
| Google Gemini API | `generate_content` with system prompt + user turn | Fatal — set `error`, route to `handle_error` |

**Behaviour:** Constructs a user turn from `dataframe_context` and `question`, calls Gemini with the analyst system prompt, writes the raw response text to `state["answer_text"]`. The response is expected to contain a prose paragraph and optionally a `table_json` fenced block and (Phase 2) a `chart_spec` fenced block.

---

### `extract_table`

**Reads from state:** `answer_text`

**Writes to state:** `table_data` (list of dicts, or `None` if no table block found)

**LLM call:** No

**External calls:** None

**Behaviour:** Searches `answer_text` for a fenced code block tagged ` ```table_json `. If found, parses the JSON array and writes it to `state["table_data"]`. If the block is absent or the JSON is malformed, sets `table_data = None` (non-fatal; the prose answer is still returned). Never sets `error` — table extraction failure is graceful degradation, not a fatal error.

---

### `generate_chart` (Phase 2 only)

**Reads from state:** `answer_text`, `dataframe_context`, `dataset_id`, `session_id`

**Writes to state:** `chart_b64` (base64-encoded PNG string, or `None` if no chart spec)

**LLM call:** No

**External calls:** None (in-process matplotlib)

**Behaviour:** Searches `answer_text` for a fenced code block tagged ` ```chart_spec `. If found, parses the JSON object (`{type, x_col, y_col, title}`), loads the DataFrame from disk (re-read), calls matplotlib to render the chart, encodes the PNG as base64, and writes to `state["chart_b64"]`. If no chart spec block is present, sets `chart_b64 = None` (non-fatal). On matplotlib error, sets `chart_b64 = None` and logs a warning — does not set `error`.

---

### `handle_error`

**Reads from state:** `error`, `run_id`

**Writes to state:** `status` = `"failed"`

**LLM call:** No

**External calls:** None (DB write happens in the runner after graph completion)

**Behaviour:** Sets `state["status"] = "failed"`. The runner observes the state after graph termination and writes the error to the `RunRow`. Logs the error with `run_id` context.

---

### `finalize`

**Reads from state:** `answer_text`, `table_data`, `chart_b64`

**Writes to state:** `status` = `"completed"`

**LLM call:** No

**External calls:** None (DB write happens in the runner after graph completion)

**Behaviour:** Sets `state["status"] = "completed"`. No other transformation — the runner reads state fields after graph termination and persists them to `RunRow`.

---

## Graph / Flow Topology

### Phase 1

```
START
  │
  ▼
load_dataset ──(error)──► handle_error ──► END
  │
  ▼
analyze_query ──(error)──► handle_error
  │
  ▼
extract_table
  │
  ▼
finalize ──► END
```

### Phase 2 (adds generate_chart)

```
START
  │
  ▼
load_dataset ──(error)──► handle_error ──► END
  │
  ▼
analyze_query ──(error)──► handle_error
  │
  ▼
extract_table
  │
  ▼
generate_chart   ← non-fatal; chart_b64 = None if no chart spec
  │
  ▼
finalize ──► END
```

**Conditional edges:**

| Source node | Condition | Target |
|-------------|-----------|--------|
| `load_dataset` | `state.get("error")` is not None | `handle_error` |
| `load_dataset` | `state.get("error")` is None | `analyze_query` |
| `analyze_query` | `state.get("error")` is not None | `handle_error` |
| `analyze_query` | `state.get("error")` is None | `extract_table` |
| `extract_table` | always | `generate_chart` (Phase 2) or `finalize` (Phase 1) |
| `generate_chart` | always | `finalize` |
| `finalize` | always | END |
| `handle_error` | always | END |

---

## Memory & Context

| Scope | Mechanism | What is stored |
|-------|-----------|----------------|
| Within a run | LangGraph `AgentState` (in-memory dict) | All pipeline data for one query |
| Across queries in a session | SQLite `runs` table + filesystem CSV files | Past answers, uploaded files (by session_id) |
| Conversation history | Not maintained — each query is stateless | The LLM has no memory of prior questions |

**Context window management:** Only schema + `.describe()` + `head(5)` are sent to Gemini. For wide CSVs (many columns), `describe()` is limited to the first 50 columns if needed. No sliding window or summarisation is required in Phase 1–3 — the schema context for one typical CSV is well within Gemini Flash's context window.

---

## Human-in-the-Loop Checkpoints

Not applicable. All query execution is fully automated. The human testing gates are at phase boundaries, not within the agent graph.

---

## Error Handling & Recovery

**Node-level:** `load_dataset` and `analyze_query` wrap their logic in `try/except Exception`; on any exception they set `state["error"] = str(exc)` and return. `extract_table` and `generate_chart` do NOT set `state["error"]` on parse failures — they degrade gracefully (set their output to `None`).

**Edge routing:** After `load_dataset` and `analyze_query`, a conditional edge function checks `state.get("error")`: if set, routes to `handle_error`; otherwise continues.

**Graph-level (`handle_error`):** Sets `status = "failed"`. Runner writes `RunRow.error_message = state["error"]` and `RunRow.status = "failed"` to the DB.

**API surface:** The runner returns a typed result; the `POST /sessions/{id}/queries` route checks for `status == "failed"` and returns HTTP 422 with `{error: state["error"]}` for the browser to display in the chat.

**Resume / retry strategy:** No resumption in Phase 1–3 (single-request lifecycle). A failed query can be retried by the user resubmitting the same question.

---

## Observability

| Signal | What | Where |
|--------|------|-------|
| Run outcome | `status`, `error_message` | SQLite `runs` table |
| Errors | `error` string with `run_id` | `print` / `logging.error` to stdout |
| LLM call | No token-level tracing in Phase 1 | Gemini SDK response object logged on error only |

---

## Concurrency Model

- **Run isolation:** Each HTTP request creates a new `AgentState` and calls `agentic_ai.invoke(state)` synchronously. FastAPI runs with a thread pool (default Uvicorn workers); each request is independent by `run_id` and `session_id`.
- **Parallel nodes within a run:** None — the graph is a linear chain with one conditional branch.
- **Checkpointing:** None (no `SqliteSaver`). Runs are single-request, short-lived; no resume needed.

---

## Graph Assembly (`src/graph/agent.py`)

```python
from langgraph.graph import StateGraph, END
from graph.state import AgentState
from graph.nodes import load_dataset, analyze_query, extract_table, finalize, handle_error
from graph.edges import after_load, after_analyze

def _build_graph() -> StateGraph:
    g = StateGraph(AgentState)

    g.add_node("load_dataset", load_dataset)
    g.add_node("analyze_query", analyze_query)
    g.add_node("extract_table", extract_table)
    g.add_node("finalize", finalize)
    g.add_node("handle_error", handle_error)

    g.set_entry_point("load_dataset")

    g.add_conditional_edges(
        "load_dataset",
        after_load,
        {"analyze_query": "analyze_query", "handle_error": "handle_error"},
    )
    g.add_conditional_edges(
        "analyze_query",
        after_analyze,
        {"extract_table": "extract_table", "handle_error": "handle_error"},
    )
    g.add_edge("extract_table", "finalize")
    g.add_edge("finalize", END)
    g.add_edge("handle_error", END)

    return g.compile()

agentic_ai = _build_graph()
```

**Phase 2 extension:** Insert `generate_chart` between `extract_table` and `finalize`. Change `g.add_edge("extract_table", "finalize")` to `g.add_edge("extract_table", "generate_chart")` + `g.add_edge("generate_chart", "finalize")`. Add `generate_chart` node import.
