# Agent

---

## Agent Architecture Pattern

| Pattern | Use when |
|---------|----------|
| **Single-agent loop** | One LLM drives a deterministic tool-call loop. No branches, no handoffs. |
| **Graph (LangGraph)** | Multi-step pipeline with conditional edges, checkpointing, or parallel nodes. |
| **Multi-agent** | Specialised sub-agents with distinct roles; orchestrator routes between them. |
| **Supervisor** | One supervisor LLM dispatches to worker agents based on task type. |
| **Human-in-the-loop** | Execution pauses at defined checkpoints for user review or approval. |

**Chosen: Graph (LangGraph) — a tiny, bounded graph, not a full ReAct loop.**

**Why LangGraph at all, given the brief's "single LLM call, no planning phase" model:** the skeleton already ships a working LangGraph wiring (`src/graph/{state,nodes,edges,agent,runner}.py`) that generators are required to extend in place, not replace. Reusing it costs nothing and buys real things: the existing conditional-edge machinery is exactly the shape needed for "one execution retry," and it gets LangSmith-compatible tracing/observability for free. A hand-rolled `try/except` retry wrapper would have to reinvent this with no benefit.

**Why it is *not* a ReAct loop:** `harness/patterns/agentic-ai.md` sets the ReAct loop (reason → act → observe → repeat until done) as the default floor for "an agent," but explicitly says to reach *down* to a simpler shape "when the task is a fixed transform with no [open-ended] actions to take." This capability is exactly that: the brief mandates a single code-generation call per question with **exactly one** bounded retry on execution failure — never an open-ended "repeat until done." The graph below is best read as a composition of two catalogue patterns, not a loop:

- **#5 Tool Use (Function Calling)** — `execute_code` is the one tool the "agent" calls: a sandboxed local pandas executor.
- **#12 Exception Handling and Recovery** — the single conditional retry edge from `execute_code` back to `generate_code` on failure, capped at one attempt, is a textbook instance of this pattern, not a reasoning loop.
- **#22 LLM-Generated Code Execution** — the core mechanism: for open-ended questions over structured data, the LLM writes executable code and the system runs it with the (schema-described, never transmitted) data in scope. This is also how the natural-language answer and the summary table are produced: the generated code itself computes and phrases them (see `generate_code` below) — there is no second "explain the result" LLM call.
- **#18 Guardrails / Safety Patterns** — the restricted-exec sandbox (no filesystem/network builtins, bounded execution time) and the structural privacy boundary (schema-only prompts) are guardrails wrapped around the whole graph.

No planning (#6), no reflection (#4), no multi-agent (#7) — the brief is explicit that none of these are wanted, and the task genuinely doesn't need them.

---

## LLM Provider & Model

| Node | Provider | Model ID | Rationale |
|------|----------|----------|-----------|
| `generate_code` | Gemini (`src/llm/providers/gemini.py`) | `gemini-3.1-pro` (env-configurable via `AGENT_LLM_MODEL`) | The only LLM-calling node in the graph; quality matters more than latency here since a bad code-gen either produces a wrong answer or burns the one retry — `gemini-3.1-pro` is the accurate default, not the fast/cheap tier. |

**Fallback behaviour:** if the Gemini call itself fails (network error, 5xx, timeout, invalid response), `generate_code` sets `state["error"]` and the graph routes straight to `handle_error` — this is a distinct failure class from an *execution* failure and does **not** consume or trigger the one execution retry (see Error Handling below).

**Prompt strategy:**
- **Phase 1:** system prompt (`src/prompts/codegen.md`) instructs Gemini to return **only** a fenced Python code block. The user-turn prompt is built entirely from: the `DatasetSchema` (columns/dtypes/null-counts/min-max/low-cardinality sample values), the question, up to the last 5 prior Q&A pairs from the same session (text only), and — on retry — the prior execution error text. The generated code must assign a plain-language sentence containing the key computed number(s) to a variable named `answer`, and may assign a `pandas.DataFrame` (≤ 50 rows) to a variable named `table`.
- **Phase 2:** the same single call's response becomes structured JSON: `{"status": "ok" | "needs_clarification" | "unanswerable", "code": "...", "followups": ["...", "...", "..."], "message": "..."}`. `code`/`followups` are present only when `status == "ok"`; `message` (the clarifying question, or the explanation of why the question can't be answered) is present otherwise. The generated code may additionally assign a `plotly.graph_objects.Figure` to a variable named `chart`.

---

## Tools & Tool Calling

| Tool name | Description | Inputs | Output | Side-effects |
|-----------|-------------|--------|--------|--------------|
| `execute_code` (sandbox) | Runs LLM-generated pandas code against the real, locally-loaded dataframe inside a restricted-exec environment | generated code string, dataset file path | `{answer: str, table: list[dict] \| None, chart: str \| None}` or raises a concise execution error | Reads the uploaded file from local disk; no writes, no network, no filesystem access from within the sandbox itself |

**Tool selection strategy:** none needed — there is exactly one tool, and it is always called after a successful code generation. This is not an LLM-driven tool-choice; it is a fixed pipeline step.

**Tool failure handling:** exactly one retry. On the first `execute_code` failure, the error text is fed back into a second `generate_code` call (a corrected-code attempt); if the second `execute_code` also fails, the graph routes to `handle_error` and the failure is surfaced to the user.

---

## Agent State

```python
class AgentState(TypedDict, total=False):
    # Identity
    query_id: str                        # set at initialisation — the Query row this run updates
    session_id: str
    dataset_id: str

    # Input (populated at initialisation, read-only during the run)
    dataset_path: str                    # local disk path — loaded into a DataFrame ONLY inside execute_code, never in state
    dataset_schema: dict                 # DatasetSchema.model_dump() — the ONLY dataset information ever sent to the LLM
    question: str
    conversation_history: list[dict]     # [{"question": str, "answer": str}, ...] — last 5 turns, text only, no raw data

    # Pipeline data (populated progressively by nodes)
    generated_code: str | None
    retry_count: int                     # 0 initially; incremented to 1 on the single allowed retry
    last_error: str | None               # the most recent EXECUTION error text (drives the retry edge); cleared on success

    # Phase 2 additions
    classification: str | None           # "ok" | "needs_clarification" | "unanswerable" — parsed from the same generate_code response
    clarification_message: str | None    # the clarifying question or the "can't answer because…" explanation
    suggested_followups: list[str] | None
    chart_spec: str | None               # Plotly figure JSON, if the generated code produced one

    # Output
    answer_text: str | None
    result_table: list[dict] | None      # capped-row summary table, JSON-serialisable
    token_usage: dict | None             # {"prompt_tokens": int, "completion_tokens": int, "total_tokens": int}

    # Control
    error: str | None                    # set by any node on a FATAL failure (LLM call failure, or execution retry exhausted)
    status: str | None                   # "completed" | "failed" | "needs_clarification" | "unanswerable" — final status written to the Query row
```

---

## Nodes / Steps

### `generate_code`

**Reads from state:** `dataset_schema`, `question`, `conversation_history`, `retry_count`, `last_error` (if `retry_count > 0`)

**Writes to state:** `generated_code`, `token_usage`, `error` (on LLM-call failure), and (Phase 2) `classification`, `clarification_message`, `suggested_followups`

**LLM call:** yes. Builds the schema-only prompt (see LLM Provider & Model above), calls `LLMClient` (Gemini), parses the response. Before calling, writes `Query.status = "generating_code"` to the DB (direct SQLAlchemy write, no repository layer, per `harness/patterns/project-layout.md`).

**External calls:**

| System | Operation | On Failure |
|--------|-----------|------------|
| Gemini API | Generate code (Phase 1) / structured `{status, code, followups}` (Phase 2) from the schema-only prompt | Fatal — sets `state["error"]`, routes to `handle_error`. Not retried by the execution-retry mechanism. |

**Behaviour:** builds a prompt containing zero raw data, calls Gemini once, and on success stores the generated code (Phase 1) or the parsed structured decision (Phase 2) plus token usage into state. On a retry pass (`retry_count == 1`), the prompt additionally includes the previous execution's error text so the model can produce corrected code.

### `execute_code`

**Reads from state:** `generated_code`, `dataset_path`

**Writes to state:** `answer_text`, `result_table`, `last_error`, and (Phase 2) `chart_spec`

**LLM call:** no.

**External calls:**

| System | Operation | On Failure |
|--------|-----------|------------|
| Local filesystem | Load the dataset file into a pandas `DataFrame` (local variable, never written to state) | Fatal — treated as an execution error, same path as a generated-code bug |
| Restricted-exec sandbox | Run the generated code with `df` (and, Phase 2, `pd`/`plotly`) in a restricted globals dict — no `open`, `os`, `sys`, `__import__`, or network builtins; bounded execution time (10s default — **Assumed:** not specified in the brief; a pragmatic guardrail against a runaway generated loop given "a few MB" datasets should compute in well under a second) | Sets `state["last_error"]` to a concise error string (exception type + message, never raw data); does not set `state["error"]` — that decision belongs to the edge below |

**Behaviour:** loads the real file fresh (always the full dataset — never a sample), runs the generated code, and reads `answer`/`table`/(`chart`) out of the sandbox's local namespace. Before starting, writes `Query.status = "running_analysis"` to the DB.

### `handle_error`

**Reads from state:** `error`, `last_error`, `query_id`

**Writes to state:** `status = "failed"`

**Behaviour:** updates the `Query` row: `status="failed"`, `error_message` set from `state["error"]` or `state["last_error"]`, `completed_at` set. Logs the failure with `query_id` context. This is a terminal node.

### `finalize`

**Reads from state:** `answer_text`, `result_table`, `generated_code`, `token_usage`, `retry_count`, and (Phase 2) `classification`, `clarification_message`, `suggested_followups`, `chart_spec`

**Writes to state:** `status = "completed"` (Phase 1), or `"needs_clarification"` / `"unanswerable"` (Phase 2, when `classification != "ok"`)

**Behaviour:** updates the `Query` row with every field that belongs in the permanent audit trail: `answer_text`, `result_table_json`, `generated_code`, `retry_count`, token usage, `completed_at`, and (Phase 2) `chart_spec_json`/`suggested_followups_json`/`error_message` (used to hold the clarification/unanswerable message). This is a terminal node.

---

## Graph / Flow Topology

```
START
  │
  ▼
generate_code ──(LLM call failed)──► handle_error ──► END
  │
  │ (Phase 2 only: classification != "ok")
  ├──────────────────────────────────────────────────► finalize ──► END
  │
  ▼ (classification == "ok" / Phase 1 default)
execute_code ──(execution failed AND retry_count == 0)──► generate_code   [retry_count += 1]
  │
  ├──(execution failed AND retry_count == 1)──► handle_error ──► END
  │
  ▼ (success)
finalize ──► END
```

**Conditional edges:**

| Source node | Condition | Target |
|-------------|-----------|--------|
| `generate_code` | `state.get("error")` is not None (LLM call itself failed) | `handle_error` |
| `generate_code` | Phase 2: `state.get("classification")` in `{"needs_clarification", "unanswerable"}` | `finalize` |
| `generate_code` | otherwise | `execute_code` |
| `execute_code` | `state.get("last_error")` is not None and `state.get("retry_count", 0) == 0` | `generate_code` (with `retry_count` incremented to 1) |
| `execute_code` | `state.get("last_error")` is not None and `state.get("retry_count", 0) >= 1` | `handle_error` |
| `execute_code` | `state.get("last_error")` is None | `finalize` |

---

## Memory & Context

| Scope | Mechanism | What is stored |
|-------|-----------|-----------------|
| **Within a run** | LangGraph state | The current question, schema, generated code, retry state, result |
| **Across runs (same session)** | SQLite `queries` table, reloaded per new query | The last 5 prior `(question, answer_text)` pairs for that `session_id`, formatted as plain text and included in the `generate_code` prompt |
| **Across sessions** | None (by design — see `spec/roadmap.md` Out of Scope) | Nothing is reloaded into a new session; only the permanent audit-log rows remain in the DB |

**Context window management:** conversation history is capped at the last 5 Q&A pairs (env-configurable via `AGENT_CONVERSATION_HISTORY_TURNS`, default 5) and is text-only (question + final answer sentence — never the generated code or the table), keeping the prompt small regardless of session length. The schema itself is already compact (column-level stats, not per-row data).

> **Assumed:** the 5-turn conversation-history window is not specified in the brief; it's a reasonable default given questions and answers are short text and Gemini's context window is large. Adjust via `AGENT_CONVERSATION_HISTORY_TURNS` if the user wants more/less history retained.

---

## Human-in-the-Loop Checkpoints

Not applicable — Phase 2's "clarifying question" is not a human-in-the-loop *approval* checkpoint; it is a terminal graph outcome (`status="needs_clarification"`) that the user resolves by asking a new, more specific question (which becomes the next `Query` turn, informed by the prior turn's clarifying message via `conversation_history`). No graph run ever pauses mid-execution waiting on the user.

---

## Error Handling & Recovery

**Node-level:** `generate_code` catches Gemini call/parse exceptions and sets `state["error"]` (fatal — no retry). `execute_code` catches sandbox exceptions and sets `state["last_error"]` (recoverable — drives the retry edge), never `state["error"]` directly.

**Graph-level (`handle_error` node):**
- Reads: `state.error`, `state.last_error`, `state.query_id`
- Updates DB: `Query.status = "failed"`, `Query.error_message`, `Query.completed_at`
- Logs the error with `query_id` context via structured logging
- Terminates the graph

**Resume / retry strategy:** no run-level resume — a failed query is not resumable; the user simply asks again. Within a single run, exactly one execution retry is automatic (see topology above); this is the entire retry strategy — there is no back-off, no second retry, and no retry of the `generate_code` LLM call itself on a provider-side failure.

**Partial failure:** there is no "partial" success in this pipeline — a query is either `completed` (Phase 1) / `completed | needs_clarification | unanswerable` (Phase 2), or `failed`. There is no degraded-but-usable state.

---

## Observability

| Signal | What | Where |
|--------|------|-------|
| **Trace** | One LangGraph run per query; LangSmith tracing enabled when `LANGCHAIN_TRACING_V2=true` and `LANGCHAIN_API_KEY` are set in `.env` (optional — pass-through, not required to run) | LangSmith (when configured) |
| **LLM calls** | Prompt (schema+question+history text, never data), completion, prompt/completion/total tokens, latency, model ID | Structured log (`structlog`, JSON to stdout) on every `generate_code` call, and persisted per-query in the `queries` table |
| **Tool calls** | `execute_code` invocation: success/failure, error text (if any), latency, retry count | Structured log + `queries.retry_count`/`error_message` |
| **Run outcome** | `status`, total duration (`completed_at - created_at`), error if any | DB (`queries` table) + structured log |

Structured logging (question, generated code, latency, token usage, error) to stdout is wired from Phase 1 — it is never deferred. LangSmith tracing is additive and optional (no LangSmith key is confirmed present in `.env`; the env vars are read but tracing simply stays inactive if unset — this does not block the Phase 1 gate).

> **Assumed:** no `LANGCHAIN_API_KEY` was confirmed present at intake, so LangSmith tracing is wired as optional/pass-through rather than mandatory. Structured stdout logging is the guaranteed observability signal the Phase 1 gate checks; if the user later adds a LangSmith key, tracing activates with no code change.

---

## Concurrency Model

- **Run isolation:** each `POST /sessions/{id}/queries` call creates its own `Query` row and its own LangGraph invocation via a FastAPI `BackgroundTasks` task. Isolation is enforced at the API layer, not inside the graph: `api-routes` rejects a new query for a session that already has a non-terminal one (`status` in `pending`/`generating_code`/`running_analysis`) with `409`, naming the in-flight `query_id` (see `spec/api.md`). This means at most one graph invocation is ever running per session at a time — the graph itself needs no locking or concurrency logic. Different sessions run fully independently and concurrently (each loads its own local `DataFrame` copy inside `execute_code` — read-only per invocation, so concurrent runs against different sessions' files are safe).
- **Parallel nodes within a run:** none — the graph is a strict sequential chain (bounded to at most 2 passes through `generate_code`/`execute_code`).
- **Checkpointing:** none. Each query is a fresh, non-resumable graph invocation, consistent with "no multi-day resumable sessions" in `spec/roadmap.md`.

---

## Graph Assembly (`src/graph/agent.py`)

```python
from langgraph.graph import StateGraph, END

from graph.state import AgentState
from graph.nodes import generate_code, execute_code, handle_error, finalize
from graph.edges import after_generate_code, after_execute_code

def _build_graph() -> StateGraph:
    g = StateGraph(AgentState)
    g.add_node("generate_code", generate_code)
    g.add_node("execute_code", execute_code)
    g.add_node("handle_error", handle_error)
    g.add_node("finalize", finalize)

    g.set_entry_point("generate_code")

    g.add_conditional_edges(
        "generate_code",
        after_generate_code,
        {"execute_code": "execute_code", "finalize": "finalize", "handle_error": "handle_error"},
    )
    g.add_conditional_edges(
        "execute_code",
        after_execute_code,
        {"generate_code": "generate_code", "finalize": "finalize", "handle_error": "handle_error"},
    )

    g.add_edge("finalize", END)
    g.add_edge("handle_error", END)
    return g.compile()

agentic_ai = _build_graph()
```

```python
# graph/edges.py
def after_generate_code(state: AgentState) -> str:
    if state.get("error"):
        return "handle_error"
    if state.get("classification") in {"needs_clarification", "unanswerable"}:   # Phase 2
        return "finalize"
    return "execute_code"

def after_execute_code(state: AgentState) -> str:
    if state.get("last_error") is None:
        return "finalize"
    if state.get("retry_count", 0) >= 1:
        return "handle_error"
    return "generate_code"   # the one allowed retry; runner increments retry_count before re-entry
```
