# Agent

> Filled by the **spec-writer** from intake. Part 3 of the 4-part spec contract (see `harness/harness.md`).
> The layer **on/off ledger** for this build: which of the 11 agentic layers are ON. Baseline layers ship in
> Phase 1 and are pre-checked — leave them on unless you have a reason. The earns-its-place layers stay OFF
> until a capability needs them; turning one on is a deliberate cost. Each pattern recipe lives at the path
> shown; don't restate it here — name the layer, mark it ON/OFF, give the one-line *why for this agent*.
>
> **Every baseline layer here is delivered by the reused, version-pinned TESTED CORE** (code is truth there,
> like a framework dependency — see `spec/constitution.md` § two-zone model). `/build` does not regenerate
> the loop, server, config, persistence, or `/traces` dashboard; it fills the GENERATED DOMAIN seams
> (capability nodes, tools, prompts, EARS evals, domain screens) on top of that proven core. The
> non-negotiable correctness rules each layer must satisfy are enumerated in `spec/constitution.md` — this
> ledger only decides which layers are wired on.

## Layers

Mark `[x]` ON / `[ ]` OFF. The "why" is one line, specific to **this** agent (not the generic layer).

### Baseline — ON in Phase 1 (the raised default; leave on unless you have a reason)

- [x] **L1 · Model & providers** — `harness/patterns/model-and-providers.md`
  Runtime LLM behind `init_chat_model`; provider/model pinned in `spec/tech-stack.md` (cheap tier default).
  Google `gemini-2.5-flash` via `langchain-google-genai`; no vision or JSON-mode override needed for P1 text analysis.
- [x] **L2 · Context engineering** — `harness/patterns/context-engineering.md`
  Assemble the window each turn: domain system prompt + goal + tool results, within a token budget.
  Domain prompt must always include the session file path and the user's analytical goal; exclude raw file bytes from context (only load them via `file_load`).
- [x] **L3 · Memory (working / short-term only)** — `harness/patterns/memory.md`
  In-run scratchpad + message history. **Long-term / cross-run memory is OFF** (see earns-its-place below).
  Agent must remember the loaded DataFrame and prior analytical steps within the same session so follow-up questions require no re-upload.
- [x] **L4 · Tools & MCP** — `harness/patterns/tools-and-mcp.md`
  Internal actions = plain typed `@tool` in-process; **MCP only for external integrations** (OAuth2.1, no static secrets).
  In-process tools: `file_load`, `python_exec`, `sql_explorer` (P2 stub), `multi_source_fetch` (P3 stub), `write_todos`, `finish`. No MCP in P1.
- [x] **Orchestration · ReAct Deep-Agent loop** — `harness/patterns/react-agent.md`
  LangGraph `StateGraph`: `agent → (tools → agent)* → finalize`, with planning todos + a `finish` tool.
  Core invariants (from `spec/constitution.md`): `max_iterations` sized to worst-case tool depth (not the
  happy path), a `force_finalize` fallback chain that never returns a blank answer, and graceful degradation
  on non-critical external failures. Code-executing tools use AST-validated eval, never regex dispatch.
  `max_iterations` set to 8 to cover: `write_todos` → `file_load` → up to 3 `python_exec` refinement calls → `finish`; `force_finalize` fires on iteration cap.
- [x] **L7 · Guardrails (action-safety only)** — `harness/patterns/guardrails-and-hitl.md`
  Validate tool inputs, refuse out-of-scope/unsafe actions per the domain rules. **HITL pause is OFF** (below).
  AST-validate all `python_exec` input: block filesystem escapes (any `open()`, `os.*`, `pathlib.*` outside session dir) and destructive ops (DELETE, DROP, TRUNCATE, rm, shutil.rmtree, os.remove).
- [x] **L9 · Observability & Evals** — `harness/patterns/observability-and-evals.md`
  OTel-GenAI spans → SQLite → built-in, self-contained **organized `/traces` observability dashboard**
  (overview + drill-down; no Docker/signup) for a non-technical operator. Outcome eval is the **hard gate**
  for the v1 single-capability slice (a 200 with the wrong answer FAILS, multi-sampled with margin so
  exit 0 is deterministic); trajectory eval is advisory until a 2nd capability exists. Each EARS line is
  bound to an executable check via its `[@eval]` token — that binding is what "proves it ran."
  Outcome eval proves `file-analysis` P1: judge scores whether the answer contains a correct numeric result + code; `expect_tools: [file_load, python_exec]`.
- [x] **L10 · Interface / serving** — `harness/patterns/interface.md`
  Async FastAPI: `GET /health`, `POST /runs`, `GET /traces`. Port **8001**. One JSON envelope everywhere:
  routes return `ok(data)` or raise `api_error(...)` — a failed run reads `state['error']`, logs with
  `run_id`, and returns `api_error('RUN_FAILED', status=500)` (no `error.html`). Serves the static
  Next.js export from the same port/command.
  Self-contained HTML UI served at `GET /` (no Node.js build step); includes a file upload affordance that posts multipart to `POST /sessions/{id}/resource` before the first `/runs` call.
- [x] **L11 · Deploy & Operate** — `harness/patterns/deploy.md`
  Portable artifact (`langgraph.json` / Dockerfile); local SQLite → Postgres + Redis on the prod ladder.
  Deploy target TBD (Railway / Fly / Modal — chosen at `/deploy`); local demo runs on port 8001 with SQLite.

> Persistence (the data spine — `harness/patterns/persistence.md`) is not a toggle: it's always on.
> Async SQLAlchemy 2.0, SQLite (`aiosqlite`) local → Postgres (`asyncpg`) prod. Tables: `runs`, `messages`,
> `spans` (+ domain entities); `runs` carries `input_tokens`/`output_tokens`/`cost_usd`/`thread_id` from
> Phase 1. Never `psycopg2`. **Session-scoped resources** (e.g. a parsed file/DataFrame/index keyed by
> `session_id`) persist across follow-up turns and are released only on explicit session delete —
> per-question release is a `SESSION_DATA_LOST` correctness bug on Q2.

### Earns its place — OFF by default (turn ON only when a capability needs it; that's the deliberate cost)

- [ ] **L5 · Retrieval / RAG** — `harness/patterns/retrieval.md`
  OFF — the agent reads data from user-uploaded files via `file_load`, not from a standing corpus.
- [ ] **L3+ · Long-term / cross-run memory** — `harness/patterns/memory.md`
  OFF — uploaded files and analysis results are session-scoped; no cross-run user memory needed in v1.
- [ ] **L6 · Multi-agent (supervisor + sub-agents)** — `harness/patterns/multi-agent.md`
  OFF — a single ReAct loop handles file load → code execution → answer in one session. No sub-agent split needed in P1.
- [ ] **L7+ · HITL (human-in-the-loop pause)** — `harness/patterns/guardrails-and-hitl.md`
  OFF — code execution is AST-validated and sandboxed; no irreversible mutation occurs, so no mid-run human approval gate is needed.
- [ ] **L8 · Durability (checkpointer / resume)** — `harness/patterns/durability.md`
  OFF — Python analysis runs complete in seconds; crash recovery via resume is not justified for P1.

## Notes

Sessions are keyed by `session_id` (= `thread_id` in `runs`). A `POST /sessions/{id}/resource` multipart
endpoint receives the uploaded file, stores it in the session resource store keyed by `session_id`, and
makes it available to `file_load` for the duration of that session. This is the `C-SESSION-SCOPE`
contract: the file persists across turns so Q2 (follow-up) can call `file_load` without a re-upload.
The gate's two-turn E2E (Q1 = upload + question, Q2 = follow-up without re-upload) validates this
session scoping directly.

`python_exec` uses AST-level validation (not regex) per `spec/constitution.md` § AST-EVAL: parse the
code string with `ast.parse()`, walk the tree, and reject any node that opens a file handle outside
the session directory or calls a destructive stdlib function. Return a safe error message to the agent;
never raise to the user.

Domain entities beyond `runs`/`messages`/`spans`: none (uploaded files are held in-memory per session,
not persisted to the DB in v1).
