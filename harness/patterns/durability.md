# Pattern: Durability (LangGraph checkpointer) — Layer 8

Make a run **resumable** — survive a crash, a restart, or a deploy mid-run, and pick up at the last
completed step. **Generate this fresh at build time**, pinning the *current* `langgraph`,
`langgraph-checkpoint-sqlite`, and (for prod) `langgraph-checkpoint-postgres` (check the latest first — a
guessed/old version 404s). The code below is the proven loop (`patterns/react-agent.md`) wired to a
checkpointer; nothing about the graph itself changes.

## When it earns its place (escalation criteria)
A second-tier capability — **off by default** (`spec/agent.md`). The demo gate's runs are short and
in-process; they don't need it. Turn it on only when at least one holds:
- **Long runs** — a run spans minutes/many steps (deep research, large multi-agent fan-out) and a restart
  mid-run would waste real money and time.
- **Resumable / interruptible** — the run pauses for a human approval and continues later
  (`patterns/guardrails-and-hitl.md` HITL is built *on* the checkpointer), or a client reconnects to an
  in-flight run.
- **Must survive a restart** — serverless/auto-scaled hosts recycle workers; a deploy lands mid-run. State
  must outlive the process.

If none hold, stop — the ephemeral loop is cheaper and simpler. Note the harness **already** persists the
*record* of every run (`runs`/`messages`/`spans` → `agent/db.py`, `patterns/observability-and-evals.md`);
that's the audit trail, not resumability. The checkpointer persists the *graph's in-flight state* (the
pending step) so `ainvoke` can be re-issued and resume instead of restart. Different jobs — keep both.

## How it works: thread_id + checkpoints
A **checkpointer** snapshots `AgentState` after every node into a store, keyed by a `thread_id` you pass in
`config`. Re-invoking the graph with the **same `thread_id`** loads the latest checkpoint and continues
from there instead of starting over. One `thread_id` == one resumable conversation/run; use the `run_id`
the harness already mints (`agent/runner.py`) so the checkpoint thread and the `runs` row line up.

## The ladder: SQLite local → Postgres (+ Redis) for prod
Same API as the persistence ladder (`patterns/persistence.md` / `agent/db.py`) — local-first, swap the
saver by environment, never change the graph:

| Env | Saver | Pin | Backed by |
|-----|-------|-----|-----------|
| **Local / demo** | `AsyncSqliteSaver` | `langgraph-checkpoint-sqlite` | a SQLite file (aiosqlite) |
| **Prod** | `AsyncPostgresSaver` | `langgraph-checkpoint-postgres` | Postgres (asyncpg) |
| **Prod streaming** | + Redis | the host's `langgraph` Redis option | Redis for token/event streaming across workers |

Never `psycopg2` (sync) — the async savers above match the async stack (`harness.md`). Postgres + Redis is
the `langgraph build` prod ladder (`workflows/deploy.md`, Layer 11).

## Code — `agent/durability.py`
A factory that returns the right saver for the environment, plus a resumable invoke. Drop-in for the
`graph.ainvoke(...)` call in `agent/runner.py`.
```python
# agent/durability.py — pin current langgraph + langgraph-checkpoint-{sqlite,postgres} before generating.
from contextlib import asynccontextmanager
from langgraph.checkpoint.memory import InMemorySaver
from .config import get_settings

@asynccontextmanager
async def get_checkpointer():
    """Yield the right checkpointer for the environment. Off → InMemorySaver (no persistence)."""
    s = get_settings()
    if not s.durability_enabled:                 # spec/agent.md toggle; demo gate stays ephemeral
        yield InMemorySaver()
        return
    url = s.database_url
    if url.startswith("postgresql"):             # prod: postgresql+asyncpg://...
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        async with AsyncPostgresSaver.from_conn_string(url) as cp:
            await cp.setup()                     # create checkpoint tables if absent
            yield cp
    else:                                        # local: sqlite+aiosqlite:///./agent.db
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
        path = url.split(":///")[-1] or ":memory:"
        async with AsyncSqliteSaver.from_conn_string(path) as cp:
            yield cp
```
Compile the graph **with** the checkpointer, then invoke **with** a `thread_id`. The graph from
`patterns/react-agent.md` is unchanged — `build_graph` ends in `g.compile()`; compile with the saver:
```python
# in agent/runner.py — wrap the existing build + ainvoke
from .durability import get_checkpointer
from .graph import build_graph                  # patterns/react-agent.md

async with get_checkpointer() as cp:
    graph = build_graph(model, checkpointer=cp)  # build_graph: g.compile(checkpointer=checkpointer)
    config = {"configurable": {"thread_id": run_id}, "recursion_limit": 50}
    result = await graph.ainvoke(initial_state, config=config)   # resumes if thread_id already has state
```
`build_graph` takes an optional `checkpointer=None` and passes it straight to `g.compile(...)` — one new
kwarg, no other change to `patterns/react-agent.md`.

## Resume after a crash (the payoff)
Re-issuing `ainvoke` with the **same `thread_id`** loads the last checkpoint and continues. Pass `None` as
the input to resume from saved state without injecting a new message:
```python
# replay/resume: same thread_id, no new input → continues from the last completed node
result = await graph.ainvoke(None, config={"configurable": {"thread_id": run_id}})
```
Inspect or rewind with `graph.aget_state(config)` / `graph.aget_state_history(config)` (e.g. resume a HITL
pause, or replay to a checkpoint and branch) — `patterns/guardrails-and-hitl.md`.

## Externalize state (why this scales to multi-worker / serverless)
The reason durability and horizontal scale are the *same* recipe: the **control plane owns the state and
the credentials; the workers are stateless**.
- **State lives in the checkpointer (Postgres/Redis), not in process memory.** Any worker can pick up any
  thread by `thread_id` — that's what makes auto-scaling and serverless recycling safe. A worker dying
  loses nothing; the next `ainvoke` resumes from the store.
- **Credentials never live in the snapshot.** The checkpoint holds `AgentState` (messages, iterations,
  answer, run_id) — never API keys or OAuth tokens. Secrets stay in `Settings` / the OAuth exchange minted
  per call (`patterns/tools-and-mcp.md`); a leaked checkpoint must not be a leaked key.
- **Tool execution belongs in a sandbox, not the control plane.** Mutating/irreversible tool calls run in
  an isolated executor with least privilege (`patterns/tools-and-mcp.md` action-safety boundary); the
  control plane orchestrates and persists, the sandbox does the dangerous doing. Keep them separate so a
  worker restart never half-fires an external side-effect.

This is the same split `langgraph build` ships for prod (Layer 11, `workflows/deploy.md`): a control plane
backed by Postgres + Redis, stateless workers, externalized state.

## Mandatory mechanics (do not omit)
- **One `thread_id` per run** — reuse the harness `run_id` so checkpoint thread ↔ `runs` row align.
- **Match the saver to the DB** — SQLite local, Postgres prod; async savers only, never `psycopg2`.
- **`await cp.setup()`** on the Postgres saver so checkpoint tables exist before the first run.
- **Off for the demo gate** — `durability_enabled=False` keeps demo runs ephemeral (`InMemorySaver`); flip
  it on only when the criteria above hold (`spec/agent.md`).
- **No secrets in checkpoints** — snapshots carry state, never credentials.

## Gate (the test that proves it — run it, don't trust it)
Prove **resume actually resumes**, not just that a saver is attached. Use an `AsyncSqliteSaver` on a temp
file and a `FakeModel` (no key, `patterns/react-agent.md`):
1. Script the fake model to emit one tool call, then **raise** on the next step (simulate a crash
   mid-run). Invoke with `thread_id="t1"`; assert it raised and a checkpoint exists
   (`await graph.aget_state(config)` is non-empty).
2. Swap in a fake model that now returns `finish`, re-invoke with `input=None` and **the same
   `thread_id`**; assert the run completes and `iterations` continued from the checkpoint (did **not**
   reset to 0) — proof it resumed rather than restarted.
→ `workflows/gates.md`.
