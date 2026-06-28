# Agent

The conversational-analysis loop, implemented as a LangGraph graph that extends the repo baseline in `src/graph/`. One invocation answers one question over the active DataFrame.

---

## Agent Architecture Pattern

| Pattern | Use when |
|---------|----------|
| **Graph (LangGraph)** | Multi-step pipeline with conditional edges and a bounded repair loop. |

**Chosen:** A **LangGraph graph implementing LLM-Generated Code Execution** (`agentic-ai.md` #22) inside a short **ReAct-style** loop (#17 + #5): the LLM *reasons* and *acts* by writing pandas, the system *observes* by executing locally, and on a code error it *re-acts* once (#12 Exception Handling). It also uses **Memory Management** (#8) — prior chat turns thread into the prompt for follow-ups. We deliberately do NOT use multi-agent, planning, or reflection: a single code-generation loop with one repair retry is the smallest pattern that satisfies "answer + show the work" over arbitrary questions. A rigid op-list interpreter is explicitly rejected (#22 anti-pattern).

---

## LLM Provider & Model

| Agent / Node | Provider | Model ID | Rationale |
|-------------|----------|----------|-----------|
| `plan_analysis` | Gemini | `gemini-2.5-flash` (default; `AGENT_LLM_MODEL` overrides) | Cheap + capable; writes pandas from schema+sample. Cost-conscious constraint favors flash over pro. |
| `format_answer` | Gemini | `gemini-2.5-flash` | Phrases the final answer from the question + computed result. |

**Fallback behaviour:** On a Gemini API error (timeout / rate limit), the node sets `state["error"]` with a readable message and routes to `handle_error`; the chat shows the error and no successful answer is persisted. No offline stub — tests call the real Gemini via `.env`.

**Prompt strategy:** System prompt (in `src/prompts/analysis.md`) instructs the model to return ONLY a pandas snippet that assigns its answer to a variable named `result`, using only `df` and `pd`. User content carries the schema, the N-row sample, prior turns, and the question. `format_answer` uses a separate prompt that takes the question + the computed `result` and returns plain English. Both are kept short to control cost; code output is parsed from a fenced block.

---

## Tools & Tool Calling

The agent's single "tool" is **local pandas execution** — not an external API, but the sandboxed exec of LLM-written code.

| Tool name | Description | Inputs | Output | Side-effects |
|-----------|-------------|--------|--------|--------------|
| `run_pandas` (`src/analysis/sandbox.py`) | Executes the LLM's snippet over the in-process DataFrame in a restricted env | `code: str`, `df` | `result` value (scalar / DataFrame / Series) or raises | None — read-only over `df`; no file/network/import |

**Tool selection strategy:** Forced single tool — every question runs the generated code exactly once (plus at most one repair).

**Tool failure handling:** On exec error, `execute_analysis` captures the traceback, increments a retry counter, and routes back to `plan_analysis` with the error appended (one retry only). A second failure routes to `handle_error`.

---

## Agent State

```python
class AgentState(TypedDict, total=False):
    # Identity
    run_id: str                     # set at initialisation (reuses baseline field)
    session_id: str                 # which dataset/conversation this belongs to

    # Input
    question: str                   # the user's plain-English question
    schema: list[dict]              # [{name, dtype}, ...] from the DataFrame (privacy-safe)
    sample_rows: list[dict]         # first N rows (default 5) — the ONLY raw data the LLM sees
    prior_turns: list[dict]         # [{role, content}, ...] prior chat context

    # Pipeline data (populated progressively)
    code: str | None                # pandas snippet emitted by plan_analysis
    result_repr: dict | None        # structured result: {kind, columns?, rows?, value?}
    exec_error: str | None          # traceback from a failed exec (drives the repair retry)
    retries: int                    # repair attempts so far (cap = 1)

    # Output
    answer: str | None              # plain-English answer
    output_payload: dict | None     # {answer, code, result_table} — the "show the work" bundle

    # Control
    error: str | None               # fatal error → handle_error
    status: str | None              # "completed" | "failed"
```

The DataFrame itself is NOT in state (it never serializes to the LLM or checkpoint); it is fetched from the in-process store by `session_id` inside the exec node.

---

## Nodes / Steps

### `extract_schema`
**Reads from state:** `session_id`, `question`
**Writes to state:** `schema`, `sample_rows`, `prior_turns`
**LLM call:** no.
**External calls:** in-process DataFrame store (load DataFrame for `session_id`); DB read for prior turns.
**Behaviour:** Pulls the privacy-safe context — column names + dtypes, first N rows, and prior chat turns — so the LLM never needs the full dataset. Real in Phase 1.

### `plan_analysis`
**Reads from state:** `schema`, `sample_rows`, `prior_turns`, `question`, `exec_error` (if repairing)
**Writes to state:** `code` (or `error` on LLM failure)
**LLM call:** yes — Gemini `gemini-2.5-flash`, prompt `src/prompts/analysis.md`, output = a fenced pandas snippet assigning `result`.
**External calls:** Gemini → on failure set `error`, route to `handle_error`.
**Behaviour:** Produces the pandas code. On a repair pass, the previous `exec_error` is included so the model corrects it. Real in Phase 1.

### `execute_analysis`
**Reads from state:** `code`, `session_id`, `retries`
**Writes to state:** `result_repr` on success; `exec_error` + `retries` on failure
**LLM call:** no.
**External calls:** `run_pandas` sandbox over the in-process DataFrame.
**Behaviour:** Runs the snippet locally with restricted builtins, no imports/IO, and a timeout; reads the `result` variable and serializes it to `result_repr`. On error with `retries < 1`, increments and routes back to `plan_analysis`; otherwise sets `error`. Real in Phase 1.

### `format_answer`
**Reads from state:** `question`, `result_repr`, `code`
**Writes to state:** `answer`, `output_payload`
**LLM call:** yes — Gemini `gemini-2.5-flash` (short prompt: question + computed result → plain English).
**External calls:** Gemini → on failure, fall back to a templated answer built from `result_repr` (still shows the work) rather than failing the whole turn.
**Behaviour:** Builds the answer-with-work bundle `{answer, code, result_table}`. Real in Phase 1.

### `finalize`
**Reads from state:** `session_id`, `question`, `output_payload`
**Writes to state:** `status = "completed"`
**Behaviour:** Persists the user message and the assistant message (answer + code + result) to SQLite. Real in Phase 1.

### `handle_error`
**Reads from state:** `error`
**Writes to state:** `status = "failed"`
**Behaviour:** Surfaces the readable error; persists nothing as a successful answer. Real in Phase 1.

> Phase 1 wires ALL of the above for the real text-answer path. Charts, one-shot report, auto-findings are NOT graph nodes in Phase 1 — they are added in later phases (chart generation becomes a branch off `format_answer`; the report is a separate multi-question fan-out).

---

## Graph / Flow Topology

```
START
  │
  ▼
extract_schema ──(error)──► handle_error ──► END
  │
  ▼
plan_analysis ──(error)──► handle_error
  │
  ▼
execute_analysis ──(exec_error & retries<1)──► plan_analysis   (repair loop, max 1)
  │                ──(exec_error & retries>=1)──► handle_error
  ▼ (success)
format_answer ──(error)──► handle_error
  │
  ▼
finalize ──► END
```

**Conditional edges:**

| Source node | Condition | Target |
|-------------|-----------|--------|
| `extract_schema` | `state["error"]` set | `handle_error` |
| `extract_schema` | else | `plan_analysis` |
| `plan_analysis` | `state["error"]` set | `handle_error` |
| `plan_analysis` | else | `execute_analysis` |
| `execute_analysis` | `exec_error` and `retries < 1` | `plan_analysis` |
| `execute_analysis` | `exec_error` and `retries >= 1` | `handle_error` |
| `execute_analysis` | success | `format_answer` |
| `format_answer` | `state["error"]` set (unrecoverable) | `handle_error` |
| `format_answer` | else | `finalize` |

---

## Memory & Context

| Scope | Mechanism | What is stored |
|-------|-----------|----------------|
| **Within a run** | LangGraph state | schema, sample, code, result, answer |
| **Across runs** | SQLite | sessions, messages, dataset metadata (schema/sample only) |
| **Conversation** | message history threaded into `prior_turns` | prior user questions + assistant answer summaries for the session |

**Context window management:** Only the schema + N sample rows + the last K prior turns (sliding window, K configurable, default ~6) are sent — never full data, keeping prompts small and cheap. If a session has many turns, older turns are dropped from the window (full history still persists in DB for replay).

---

## Error Handling & Recovery

**Node-level:** Each node catches its own exceptions. LLM failures set `state["error"]`; exec failures set `state["exec_error"]` to drive the bounded repair loop.

**Graph-level (`handle_error`):**
- Reads: `state["error"]`, `state["run_id"]`
- Sets `status = "failed"`; surfaces the readable message to the chat
- Persists no successful answer
- Terminates the graph

**Resume / retry strategy:** Single in-graph repair retry for bad pandas (cap 1). No cross-run resume — each question is an independent invocation.

**Partial failure:** If `format_answer`'s LLM call fails but a result was computed, fall back to a templated answer from `result_repr` (the work is still shown) rather than failing the turn.

---

## Observability

| Signal | What | Where |
|--------|------|-------|
| **Trace** | One log line per node with `run_id` + `session_id` | stdout (structured) |
| **LLM calls** | model, latency, success/error | structured log |
| **Tool calls** | generated code, exec success/error, retry count | structured log |
| **Run outcome** | status, error if any | DB + structured log |

---

## Concurrency Model

- **Run isolation:** one question at a time per session (single user). Distinct sessions are isolated by `session_id`-keyed DataFrame store + `run_id` scoping.
- **Parallel nodes within a run:** none in Phase 1. (The one-shot report in a later phase fans out independent question-runs concurrently.)
- **Checkpointing:** none required — runs are short and synchronous; no human-in-the-loop pause.

---

## Graph Assembly (`src/graph/agent.py`)

```python
graph = StateGraph(AgentState)

graph.add_node("extract_schema", extract_schema)
graph.add_node("plan_analysis", plan_analysis)
graph.add_node("execute_analysis", execute_analysis)
graph.add_node("format_answer", format_answer)
graph.add_node("finalize", finalize)
graph.add_node("handle_error", handle_error)

graph.set_entry_point("extract_schema")

graph.add_conditional_edges(
    "extract_schema",
    lambda s: "handle_error" if s.get("error") else "plan_analysis",
)
graph.add_conditional_edges(
    "plan_analysis",
    lambda s: "handle_error" if s.get("error") else "execute_analysis",
)
graph.add_conditional_edges(
    "execute_analysis",
    after_execute,   # success→format_answer; exec_error&retries<1→plan_analysis; else→handle_error
)
graph.add_conditional_edges(
    "format_answer",
    lambda s: "handle_error" if s.get("error") else "finalize",
)
graph.add_edge("finalize", END)
graph.add_edge("handle_error", END)

agentic_ai = graph.compile()
```
