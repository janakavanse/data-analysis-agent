# Agent

> Filled by the **spec-writer** from intake. Part 3 of the 4-part spec contract (see `harness/harness.md`).
> Decides which of the 11 agentic layers are ON for this build. Baseline layers ship in Phase 1 and are
> pre-checked — leave them on unless you have a reason. The earns-its-place layers stay OFF until a
> capability needs them; turning one on is a deliberate cost. Each pattern recipe lives at the path shown;
> don't restate it here — name the layer, mark it ON/OFF, give the one-line *why for this agent*.

## Layers

Mark `[x]` ON / `[ ]` OFF. The "why" is one line, specific to **this** agent (not the generic layer).

### Baseline — ON in Phase 1 (the raised default; leave on unless you have a reason)

- [x] **L1 · Model & providers** — `harness/patterns/model-and-providers.md`
  Runtime LLM behind `init_chat_model`; provider/model pinned in `spec/tech-stack.md` (cheap tier default).
  <!-- FILL IN: one line — anything model-specific this agent needs (e.g. JSON mode, long context, vision). -->
- [x] **L2 · Context engineering** — `harness/patterns/context-engineering.md`
  Assemble the window each turn: domain system prompt + goal + tool results, within a token budget.
  <!-- FILL IN: one line — what must always be in context for this domain (and what to keep out). -->
- [x] **L3 · Memory (working / short-term only)** — `harness/patterns/memory.md`
  In-run scratchpad + message history. **Long-term / cross-run memory is OFF** (see earns-its-place below).
  <!-- FILL IN: one line — what the agent must remember within a single run. -->
- [x] **L4 · Tools & MCP** — `harness/patterns/tools-and-mcp.md`
  Internal actions = plain typed `@tool` in-process; **MCP only for external integrations** (OAuth2.1, no static secrets).
  <!-- FILL IN: one line — the concrete tools this agent calls, and which (if any) are external/MCP. -->
- [x] **Orchestration · ReAct Deep-Agent loop** — `harness/patterns/react-agent.md`
  LangGraph `StateGraph`: `agent → (tools → agent)* → finalize`, with planning todos + a `finish` tool.
  <!-- FILL IN: one line — anything non-default about the loop (iteration cap, forced finalize, sub-agent split). -->
- [x] **L7 · Guardrails (action-safety only)** — `harness/patterns/guardrails-and-hitl.md`
  Validate tool inputs, refuse out-of-scope/unsafe actions per the domain rules. **HITL pause is OFF** (below).
  <!-- FILL IN: one line — the specific actions to gate/refuse for this agent. -->
- [x] **L9 · Observability & Evals** — `harness/patterns/observability-and-evals.md`
  OTel-GenAI spans → SQLite → built-in `/traces` viewer; outcome + trajectory evals from the EARS criteria.
  <!-- FILL IN: one line — the outcome eval that proves *this* agent works (links to a capability's criteria). -->
- [x] **L10 · Interface / serving** — `harness/patterns/interface.md`
  Async FastAPI: `GET /health`, `POST /runs`, `GET /traces`. Port 8001.
  <!-- FILL IN: one line — any extra endpoint/SSE/streaming this agent exposes. -->
- [x] **L11 · Deploy & Operate** — `harness/patterns/deploy.md`
  Portable artifact (`langgraph.json` / Dockerfile); local SQLite → Postgres + Redis on the prod ladder.
  <!-- FILL IN: one line — the deploy target (Railway/Fly/Modal/…) once known; OK to leave for /deploy. -->

> Persistence (the data spine — `harness/patterns/persistence.md`) is not a toggle: it's always on.
> Async SQLAlchemy 2.0, SQLite (`aiosqlite`) local → Postgres (`asyncpg`) prod. Tables: `runs`, `messages`,
> `spans` (+ domain entities). Never `psycopg2`.

### Earns its place — OFF by default (turn ON only when a capability needs it; that's the deliberate cost)

- [ ] **L5 · Retrieval / RAG** — `harness/patterns/retrieval.md`
  ON only if the agent must ground answers in a corpus it doesn't already know.
  <!-- FILL IN: leave OFF, or one line — what corpus, why the model can't answer without it. -->
- [ ] **L3+ · Long-term / cross-run memory** — `harness/patterns/memory.md`
  ON only if the agent must remember facts *across* separate runs/users.
  <!-- FILL IN: leave OFF, or one line — what persists across runs, scoped to whom. -->
- [ ] **L6 · Multi-agent (supervisor + sub-agents)** — `harness/patterns/multi-agent.md`
  ON only if one ReAct loop genuinely can't hold the task; sub-agents get isolated context.
  <!-- FILL IN: leave OFF, or one line — the split and why a single loop fails. -->
- [ ] **L7+ · HITL (human-in-the-loop pause)** — `harness/patterns/guardrails-and-hitl.md`
  ON only if a dangerous/irreversible action must pause for human approval mid-run.
  <!-- FILL IN: leave OFF, or one line — which action pauses, who approves. -->
- [ ] **L8 · Durability (checkpointer / resume)** — `harness/patterns/durability.md`
  ON only if a run is long/expensive enough that surviving a crash or restart matters.
  <!-- FILL IN: leave OFF, or one line — why a run must resume rather than restart. -->

## Notes
<!-- FILL IN (optional): any layer interaction or trade-off worth recording for the build. -->
