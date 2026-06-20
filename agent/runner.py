import uuid
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from sqlalchemy import select
from .config import get_settings
from .db import Message, Run, Span, get_sessionmaker
from .graph import build_graph
from .llm import get_model
from .observability import span

DOMAIN_PROMPT = """You are a data analysis agent. Help users analyze their uploaded CSV or JSON files using Python/pandas.

Steps for EVERY question (do them in order, exactly once each):
1. Call write_todos with your plan.
2. Call file_load() to inspect the data (columns, types, sample rows).
3. Call python_exec(code) ONCE with ONE expression that computes the COMPLETE answer. For multi-column questions use df.mean(numeric_only=True) or df.describe() — do NOT call python_exec multiple times.
4. Call finish(answer) immediately. ALWAYS format your answer as:
   The result is: <answer text>
   ```python
   <the exact expression you used>
   ```

Rules:
- python_exec accepts ONLY a single expression. No multi-line code, no imports, no assignments.
- ONE python_exec call per question. Cover all parts in that one call.
- Call finish IMMEDIATELY after python_exec — never ask follow-up questions.
- Round floats to 2 decimal places. Never invent values not in the data.
- If asked about SQL databases, call sql_explorer. If asked about external data sources, call multi_source_fetch."""


async def _load_prior_messages(session_id: str) -> list:
    from sqlalchemy import select as sa_select, desc
    prior: list = []
    async with get_sessionmaker()() as s:
        runs = (await s.execute(
            sa_select(Run).where(Run.thread_id == session_id)
            .order_by(desc(Run.created_at)).limit(3)
        )).scalars().all()
        for run in reversed(runs):
            msgs = (await s.execute(
                sa_select(Message).where(Message.run_id == run.id)
                .order_by(Message.created_at)
            )).scalars().all()
            for m in msgs:
                if m.role == "assistant":
                    prior.append(AIMessage(content=m.content))
                elif m.role == "human":
                    prior.append(HumanMessage(content=m.content))
    return prior


async def run_agent(goal: str, model=None, run_id: str | None = None,
                    session_id: str | None = None, checkpointer=None) -> dict:
    settings = get_settings()
    run_id = run_id or uuid.uuid4().hex
    model = model or get_model()

    async with get_sessionmaker()() as s:
        s.add(Run(id=run_id, goal=goal, status="running", iterations=0, thread_id=session_id))
        await s.commit()

    graph = build_graph(model)
    config = {"recursion_limit": 50}
    prior: list = []
    if session_id:
        prior = await _load_prior_messages(session_id)

    state = {
        "messages": [SystemMessage(content=DOMAIN_PROMPT)] + prior + [HumanMessage(content=goal)],
        "iterations": 0, "answer": None, "run_id": run_id,
    }

    try:
        from .sessions import current_session_id
    except ImportError:
        current_session_id = None
    token = current_session_id.set(session_id) if current_session_id is not None else None
    try:
        async with span(run_id, "invoke_agent", "INTERNAL", goal=goal):
            result = await graph.ainvoke(state, config=config)
    finally:
        if token is not None:
            current_session_id.reset(token)

    async with get_sessionmaker()() as s:
        for m in result["messages"]:
            role = "assistant" if isinstance(m, AIMessage) else getattr(m, "type", "system")
            content = m.content if isinstance(m.content, str) else str(m.content)
            s.add(Message(id=uuid.uuid4().hex, run_id=run_id, role=role, content=content))
        spans = (await s.execute(select(Span).where(Span.run_id == run_id, Span.kind == "LLM"))).scalars().all()
        tok_in = sum((sp.attributes or {}).get("tokens", {}).get("input", 0) for sp in spans)
        tok_out = sum((sp.attributes or {}).get("tokens", {}).get("output", 0) for sp in spans)
        run = (await s.execute(select(Run).where(Run.id == run_id))).scalar_one()
        run.status, run.answer, run.iterations = "completed", result["answer"], result["iterations"]
        run.input_tokens, run.output_tokens = tok_in, tok_out
        run.cost_usd = (tok_in * settings.price_in + tok_out * settings.price_out) / 1_000_000
        await s.commit()

    return {"run_id": run_id, "session_id": session_id, "thread_id": session_id,
            "status": "completed", "answer": result["answer"],
            "iterations": result["iterations"],
            "input_tokens": tok_in, "output_tokens": tok_out,
            "cost_usd": (tok_in * settings.price_in + tok_out * settings.price_out) / 1_000_000,
            "messages": result["messages"]}
