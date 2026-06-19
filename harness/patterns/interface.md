# Pattern: Interface / serving (Layer 10)

How the agent reaches the outside world: an async FastAPI app exposing `/health`, `POST /runs`, and the
built-in `/traces` viewer. **Generate this fresh at build time**, pinning the *current* `fastapi` /
`uvicorn` (check the latest first — a guessed/old version 404s). The code below is proven working.

The graph and loop come from `patterns/react-agent.md`; spans + the `/traces` HTML from
`patterns/observability-and-evals.md`; the runtime model from `patterns/model-and-providers.md`. This
recipe is only the serving edge.

## Contract
- `GET /health` → `{"ok": true}` — the liveness probe the demo gate hits.
- `POST /runs {"goal": "..."}` → runs the agent, returns the `ok()` envelope with the answer + run id.
- `GET /` → redirect to `/traces`; `GET /traces` → server-rendered timeline (no JS).
- Port **8001** (override `APP_PORT`). One envelope shape everywhere: `ok(data)` / `err(msg)`.

## Code — `agent/runner.py` (proven, verbatim)
Drives one run end-to-end: create the `Run`, build the graph, seed the domain system prompt + goal, invoke
under the `invoke_agent` span, persist messages + outcome. `run_id` is returned so the caller can deep-link
into `/traces`.
```python
import uuid
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from sqlalchemy import select
from .config import get_settings
from .db import Message, Run, session_scope
from .graph import build_graph
from .llm import get_model
from .observability import span

DOMAIN_PROMPT = (  # the spec-writer overwrites this from spec/product.md (domain instructions)
    "You are a focused task agent. Use the tools available. Call finish when you have the answer."
)

async def run_agent(goal: str, model=None, run_id: str | None = None) -> dict:
    settings = get_settings()
    run_id = run_id or uuid.uuid4().hex
    model = model or get_model()

    async with session_scope() as s:
        s.add(Run(id=run_id, goal=goal, status="running", iterations=0))

    graph = build_graph(model)
    state = {
        "messages": [SystemMessage(content=DOMAIN_PROMPT), HumanMessage(content=goal)],
        "iterations": 0, "answer": None, "run_id": run_id,
    }
    async with span(run_id, "invoke_agent", "AGENT", goal=goal):
        result = await graph.ainvoke(state, config={"recursion_limit": 50})

    async with session_scope() as s:
        for m in result["messages"]:
            role = "assistant" if isinstance(m, AIMessage) else getattr(m, "type", "system")
            content = m.content if isinstance(m.content, str) else str(m.content)
            s.add(Message(id=uuid.uuid4().hex, run_id=run_id, role=role, content=content))
        run = (await s.execute(select(Run).where(Run.id == run_id))).scalar_one()
        run.status, run.answer, run.iterations = "completed", result["answer"], result["iterations"]

    return {"run_id": run_id, "answer": result["answer"], "iterations": result["iterations"]}
```

## Code — `agent/server.py` (proven, verbatim)
```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
from .db import init_db
from .runner import run_agent
from .traces_view import render_traces      # patterns/observability-and-evals.md

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()                          # create_all — sqlite local-first
    yield

app = FastAPI(title="agent", lifespan=lifespan)

def ok(data):  return {"ok": True, "data": data}
def err(msg):  return {"ok": False, "error": msg}

class RunIn(BaseModel):
    goal: str

@app.get("/health")
async def health():
    return ok({"status": "alive"})

@app.post("/runs")
async def create_run(body: RunIn):
    try:
        return ok(await run_agent(body.goal))
    except Exception as e:                    # surface key/model failures as JSON, not a 500 stacktrace
        return err(str(e))

@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse("/traces")

@app.get("/traces", response_class=HTMLResponse)
async def traces():
    return await render_traces()             # server-rendered HTML, no JS
```

## Code — `agent/__main__.py` (proven, verbatim)
```python
import uvicorn
from .config import get_settings

if __name__ == "__main__":
    s = get_settings()
    uvicorn.run("agent.server:app", host="0.0.0.0", port=s.port, reload=False)
```
Run it: `python -m agent` → `http://localhost:8001`. `GET /health` is the demo gate's liveness check;
the deploy artifact serves the same app (`patterns/durability.md`, deploy ladder).

## SSE token streaming (sketch — add when the UI wants live tokens)
`POST /runs` returns the whole answer; for a typing-cursor UX stream tokens over **Server-Sent Events**.
Stream from `graph.astream_events` (LangGraph emits `on_chat_model_stream` chunks) and forward each token
as an SSE `data:` line. One extra endpoint, no protocol change to the rest:
```python
import json
from fastapi.responses import StreamingResponse

@app.post("/runs/stream")
async def stream_run(body: RunIn):
    async def gen():
        async for ev in stream_agent(body.goal):        # wraps graph.astream_events(..., version="v2")
            if ev["event"] == "on_chat_model_stream" and (tok := ev["data"]["chunk"].content):
                yield f"data: {json.dumps({'token': tok})}\n\n"
            elif ev["event"] == "on_chain_end" and ev["name"] == "finalize":
                yield f"data: {json.dumps({'done': True, 'answer': ev['data']['output']['answer']})}\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream")
```
Headers that bite in prod: `Cache-Control: no-cache`, `X-Accel-Buffering: no` (disable proxy buffering).
Client reads with `EventSource` / `fetchEventSource`. The span wrapping is unchanged — streaming is a view
over the same run, still persisted and visible in `/traces`.

## UI — Next.js + React + Tailwind, primary journey only
The harness builds a UI **by default**; **headless products skip it** (set in `spec/tech-stack.md` — an
API/cron/Slack-only agent ships no web UI). When built, scope it to the **primary journey** the user
described in `spec/product.md` — *not* a screen per capability. Usually one page: enter a goal → see the
answer stream in → a link to its trace. The agent's value is the run, not the chrome.

- **Stack:** Next.js (App Router) + React + Tailwind. The page calls `POST /runs` (or `/runs/stream` for
  SSE) and renders the `ok()` envelope. Keep state minimal — input, streaming answer, run-id link.
- **Honesty:** real network call to the real agent. No mocked answer, no fake latency, no lorem.
- **Deep-link the trace:** show `run_id` as a link to `/traces` so a human can inspect the actual steps —
  the UI and the observability layer are the same truth (`patterns/observability-and-evals.md`).
- **Don't rebuild `/traces`.** The server already renders the timeline; the UI links to it.

### Gate — Playwright asserts the post-JS DOM (run it, don't trust it)
The journey test drives a real browser against the running app and asserts what a user actually sees
*after* React hydrates and the answer arrives — never the raw HTML, never a 200 alone. → `workflows/gates.md`.
```python
# tests/e2e/test_primary_journey.py  (pytest + playwright; agent server + next dev both up)
from playwright.sync_api import expect

def test_user_gets_an_answer(page):
    page.goto("http://localhost:3000")
    page.get_by_role("textbox", name="goal").fill("What does the onboarding doc say about refunds?")
    page.get_by_role("button", name="Run").click()
    answer = page.get_by_test_id("answer")
    expect(answer).not_to_be_empty(timeout=30_000)        # post-JS DOM, after the real run completes
    expect(page.get_by_role("link", name="trace")).to_be_visible()   # deep-link to /traces present
```
A headless product replaces this with the API + outcome-eval gate only (no browser). The mechanical
two-tier success (demo / productionise) is defined in `harness/harness.md` and `workflows/gates.md` — this
recipe just wires the serving edge into it.
