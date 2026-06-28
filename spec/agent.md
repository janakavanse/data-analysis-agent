# Agent

> The DataChat analysis agent: a LangGraph **plan-then-execute** graph with **local code execution** and **conversation memory**. REQUIRED — a framework is in use. Patterns chosen from [`harness/patterns/agentic-ai.md`](../harness/patterns/agentic-ai.md): **Planning (#6)**, **LLM-Generated Code Execution (#22)**, **Memory Management (#8)**, **Exception Handling and Recovery (#12)**, **Evaluation and Monitoring (#19)**. Reflection/multi-agent are deliberately NOT used (overkill for one analysis loop).

---

## Agent Architecture Pattern

| Pattern | Use when |
|---------|----------|
| **Graph (LangGraph)** ✅ | Multi-step pipeline with conditional edges (plan → generate → execute → synthesize) and a self-correction loop |

**Chosen:** **LangGraph plan-execute graph.** Each question is one graph invocation: the agent produces an explicit numbered plan, generates pandas code from the **schema + sample rows only**, executes that code **locally against the full data**, then synthesizes a streamed plain-English answer. A conditional self-correction edge retries code once on execution failure; all other failures route to an error node. This matches the intake requirement — "plan before executing, then carry it out step by step; this is an agentic loop, not a single LLM call."

---

## LLM Provider & Model

| Agent / Node | Provider | Model ID | Rationale |
|--------------|----------|----------|-----------|
| `plan` | Google Gemini | `gemini-2.0-flash` (env `AGENT_LLM_MODEL`) | Low-cost; planning over a schema is light |
| `generate_code` | Google Gemini | `gemini-2.0-flash` | Low-cost code gen; flash is sufficient for pandas snippets |
| `synthesize` | Google Gemini | `gemini-2.0-flash` | Low-cost; streamed prose over the computed result |
| `profile_context` | — (no LLM) | — | Pure local assembly of schema + samples + history |
| `execute_local` | — (no LLM) | — | Pure local pandas execution |
| `handle_error` | — (no LLM) | — | Persists failure |

All LLM calls go through `LLMClient` (`src/llm/client.py`) — **nodes never call `google-genai` directly.** The wrapper is extended to return token usage so the graph captures `prompt_tokens`/`completion_tokens` per call.

**Fallback behaviour:** on a Gemini error/timeout/rate-limit, the calling node catches it, sets `state["error"]`, and routes to `handle_error`; the run is persisted as `failed` and the error is streamed to the UI. This is production resilience, not a test stub — tests call the real API with the key from `.env`.

**Prompt strategy:** system/user split; prompts are `.md` files in `src/prompts/`. `plan` and `generate_code` request **structured output** (a numbered plan; a fenced pandas block assigning `result`). `synthesize` is free-form prose, streamed token-by-token.

---

## Tools & Tool Calling

This agent uses a fixed-topology graph rather than free LLM tool-choice; the "tool" is the local executor invoked deterministically after code generation.

| Tool name | Description | Inputs | Output | Side-effects |
|-----------|-------------|--------|--------|--------------|
| `execute_pandas` | Run generated pandas code locally on the full dataframe in a restricted namespace | `code: str`, `df: DataFrame` | `ExecResult{result_table, key_numbers, error, traceback}` | None (no writes, no network) |
| `build_llm_context` | Assemble schema + sample rows + profile + trimmed history into the prompt context | `profile`, `question`, `history` | `str` (bounded by sample-row cap) | None |

**Tool selection strategy:** deterministic — the graph always plans, generates, then executes; no LLM free-choice routing.

**Tool failure handling:** `execute_pandas` exceptions trigger **one** self-correction retry (regenerate code with the error appended); a second failure routes to `handle_error` with the real traceback + the code.

---

## Agent State

```python
class AgentState(TypedDict, total=False):
    # Identity
    message_id: str                 # set at init — the messages row id
    dataset_id: str                 # set at init — the active dataset

    # Input
    question: str                   # set at init — the user's question
    profile: dict                   # set at init — schema/dtypes/ranges/missing/sample rows (local)
    file_path: str                  # set at init — on-disk path of the full dataset
    messages: list                  # set at init — trimmed prior turns [{role, content}]

    # Pipeline data (populated progressively by nodes)
    plan: str | None                # set by plan
    generated_code: str | None      # set by generate_code (and on retry)
    result_table: list | None       # set by execute_local (rows/cols of computed result)
    key_numbers: dict | None        # set by execute_local (label -> value)
    exec_error: str | None          # set by execute_local on exception (drives self-correction)
    retry_count: int                # init 0; incremented before a self-correction

    # Output
    answer: str | None              # set by synthesize (streamed)

    # Observability
    prompt_tokens: int              # accumulated across LLM nodes
    completion_tokens: int          # accumulated across LLM nodes
    cost_usd: float                 # computed from token totals + price env vars

    # Control
    error: str | None               # set by any node on fatal failure → handle_error
    status: str | None              # "completed" | "failed" — set by finalize/handle_error
```

The full dataframe is **not** in state — it is loaded from `file_path` inside `execute_local` only, so it never serializes into a prompt.

---

## Nodes / Steps

### `node_profile_context`
**Reads:** `profile`, `question`, `messages`
**Writes:** (nothing new to state; prepares the bounded LLM context via `build_llm_context`)
**LLM call:** no.
**Behaviour:** Assembles the **schema + sample rows + profile + trimmed history** into the context strings the LLM nodes use. The single chokepoint enforcing the privacy boundary — full data is never assembled here.

### `node_plan`
**Reads:** context (schema/samples/profile/history), `question`
**Writes:** `plan`, `prompt_tokens`, `completion_tokens`
**LLM call:** yes — `src/prompts/plan.md`, model `gemini-2.0-flash`, output = a numbered multi-step plan.
**External calls:** Gemini via `LLMClient` → on failure set `error`.
**Behaviour:** Produces the explicit step-by-step analysis plan (Planning #6) before any code is written.

### `node_generate_code`
**Reads:** `plan`, context, `exec_error` (if retrying), `generated_code` (if retrying)
**Writes:** `generated_code`, `prompt_tokens`, `completion_tokens`
**LLM call:** yes — `src/prompts/generate_code.md`, model `gemini-2.0-flash`, output = a fenced pandas block that assigns `result`.
**External calls:** Gemini via `LLMClient` → on failure set `error`.
**Behaviour:** Writes pandas code that realizes the plan, against the schema (LLM-Generated Code Execution #22). On a retry, the prior code + the execution error are included so it can self-correct.

### `node_execute_local`
**Reads:** `generated_code`, `file_path`
**Writes:** `result_table`, `key_numbers`, `exec_error` (on failure)
**LLM call:** no.
**External calls:** local pandas only — loads the **full** dataframe from `file_path`, runs `execute_pandas` in the restricted sandbox with the `AGENT_EXEC_TIMEOUT_S` timeout.
**Behaviour:** Executes the generated code locally over the full data. On exception, sets `exec_error` (drives the self-correction edge); does not set `error` on the first failure.

### `node_synthesize`
**Reads:** `question`, `plan`, `result_table`, `key_numbers`, `messages`
**Writes:** `answer`, `prompt_tokens`, `completion_tokens`, `cost_usd`
**LLM call:** yes — `src/prompts/synthesize.md`, model `gemini-2.0-flash`, **streamed**.
**External calls:** Gemini via `LLMClient` (streaming) → on failure set `error`.
**Behaviour:** Turns the computed result into a plain-English answer referencing the key numbers, streamed token-by-token to the SSE response. Computes `cost_usd` from accumulated tokens.

### `node_finalize`
**Reads:** all output fields
**Writes:** `status = "completed"`
**Behaviour:** Marks success; the runner persists the full `messages` row.

### `node_handle_error`
**Reads:** `error` (or final `exec_error`), `generated_code`
**Writes:** `status = "failed"`
**Behaviour:** Terminal failure. The runner persists a `failed` `messages` row carrying the **actual error and the code that caused it** (transparency over silent retries). No crash; the error is streamed to the UI.

---

## Graph / Flow Topology

```
START
  │
  ▼
profile_context
  │
  ▼
plan ──(error)──► handle_error ──► END
  │
  ▼
generate_code ──(error)──► handle_error
  │
  ▼
execute_local
  │
  ├──(exec_error and retry_count < 1)──► generate_code   (self-correction, retry once)
  ├──(exec_error and retry_count >= 1)──► handle_error
  │
  └──(ok)──► synthesize ──(error)──► handle_error
                │
                ▼
            finalize ──► END
```

**Conditional edges:**

| Source node | Condition | Target |
|-------------|-----------|--------|
| `plan` | `state["error"]` is not None | `handle_error` |
| `plan` | else | `generate_code` |
| `generate_code` | `state["error"]` is not None | `handle_error` |
| `generate_code` | else | `execute_local` |
| `execute_local` | `exec_error` and `retry_count < AGENT_MAX_RETRIES` (default 1) | `generate_code` (increment `retry_count`) |
| `execute_local` | `exec_error` and `retry_count >= AGENT_MAX_RETRIES` | `handle_error` |
| `execute_local` | no `exec_error` | `synthesize` |
| `synthesize` | `state["error"]` is not None | `handle_error` |
| `synthesize` | else | `finalize` |

---

## Memory & Context

| Scope | Mechanism | What is stored |
|-------|-----------|----------------|
| **Within a run** | LangGraph `AgentState` | plan, code, result, tokens, cost, error |
| **Across runs** | SQLite `messages` (audit trail) | every question/plan/code/result/tokens/cost/status |
| **Conversation** | `messages` per `dataset_id`, trimmed to `AGENT_HISTORY_TURNS` turns | prior question + answer text only (never full data) — see [conversation_memory](capabilities/conversation_memory.md) |

**Context window management:** only the **schema + sample rows + profile + last N turns** ever enter a prompt; `build_llm_context` bounds it. The full dataframe is never in any prompt — that is the privacy boundary, not a token optimization.

---

## Human-in-the-Loop Checkpoints

None in Phase 1. The "confirm before heavy/expensive work" gate is **deferred to Phase 5** (a labelled stub until then). When added, it pauses before generate_code when the plan is estimated to be expensive/heavy and asks the owner to confirm.

---

## Error Handling & Recovery

**Node-level:** every LLM node wraps its `LLMClient` call in try/except; on failure it sets `state["error"]` and the conditional edge routes to `handle_error`. `execute_local` captures exceptions into `exec_error` (not `error`) so the self-correction edge can fire.

**Graph-level (`handle_error`):**
- Reads `error`/`exec_error`, `message_id`, `generated_code`
- Runner updates the `messages` row: status → `failed`, `error` = real message/traceback, `generated_code` = offending code, `completed_at`
- Logs the error with `message_id`/`dataset_id` context
- Terminates the graph (END); the error (and code) is streamed to the UI

**Resume / retry strategy:** code-execution failures self-correct **once** (regenerate with the error fed back). All other failures (LLM error, second exec failure, timeout) are terminal and surfaced — no silent retry loops.

**Partial failure:** if `synthesize` streaming fails mid-way, the computed result + code are still persisted; the message is marked `failed` with the streaming error.

---

## Observability

| Signal | What | Where |
|--------|------|-------|
| **Trace** | One trace per question, one span per node | LangSmith when `LANGCHAIN_TRACING_V2=true` + `LANGCHAIN_API_KEY` set (optional); always structlog |
| **LLM calls** | model, prompt/completion tokens, latency, cost | structlog JSON (`src/observability/events.py`) + persisted on the `messages` row |
| **Code execution** | code, success/error, latency | structlog JSON |
| **Run outcome** | status, total duration, error | `messages` row + structlog |

Structured request/response logging is wired from Phase 1 (input question, plan, code, output, latency, tokens, cost, error) — observability is never deferred. LangSmith tracing is opt-in via env and adds no requirement.

---

## Concurrency Model

- **Run isolation:** single local owner; questions are processed one at a time per request. Each run is scoped by `message_id`; no cross-run shared mutable state.
- **Parallel nodes within a run:** none — the pipeline is strictly sequential (plan → generate → execute → synthesize).
- **Checkpointing:** none required (no human-in-the-loop in Phase 1, runs are short). The streaming SSE response holds the single in-flight run.

---

## Graph Assembly (`src/graph/agent.py`)

> Replaces the skeleton's `transform_text` wiring in place; keeps the compiled-graph + error-edge structure.

```python
graph = StateGraph(AgentState)

graph.add_node("profile_context", node_profile_context)
graph.add_node("plan", node_plan)
graph.add_node("generate_code", node_generate_code)
graph.add_node("execute_local", node_execute_local)
graph.add_node("synthesize", node_synthesize)
graph.add_node("finalize", node_finalize)
graph.add_node("handle_error", node_handle_error)

graph.set_entry_point("profile_context")
graph.add_edge("profile_context", "plan")

graph.add_conditional_edges(
    "plan",
    lambda s: "handle_error" if s.get("error") else "generate_code",
    {"handle_error": "handle_error", "generate_code": "generate_code"},
)
graph.add_conditional_edges(
    "generate_code",
    lambda s: "handle_error" if s.get("error") else "execute_local",
    {"handle_error": "handle_error", "execute_local": "execute_local"},
)
graph.add_conditional_edges(
    "execute_local",
    route_after_execute,   # exec_error+retries→generate_code | exec_error→handle_error | ok→synthesize
    {"generate_code": "generate_code", "handle_error": "handle_error", "synthesize": "synthesize"},
)
graph.add_conditional_edges(
    "synthesize",
    lambda s: "handle_error" if s.get("error") else "finalize",
    {"handle_error": "handle_error", "finalize": "finalize"},
)

graph.add_edge("finalize", END)
graph.add_edge("handle_error", END)

agentic_ai = graph.compile()
```

The streaming variant uses LangGraph's streaming API in `src/graph/runner.py` so `synthesize` tokens flow to the SSE response while the rest of the state still flows through `finalize`.
