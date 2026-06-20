import uuid
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from sqlalchemy import select

from .config import get_settings
from .db import Dataset, Message, Run, Span, Thread, get_sessionmaker
from .graph import build_graph
from .llm import get_model
from .observability import span

DOMAIN_PROMPT_BASE = """You are a data analysis assistant. Your job is to help the user understand and \
explore datasets they have uploaded.

Tools available:
- upload_dataset: parse a CSV or JSON file into a SQLite table
- list_datasets: show available datasets with their schemas
- query_dataset: execute a SELECT query against a dataset (SELECT only — no mutations)
- generate_chart: produce a Plotly JSON chart spec (returns CHART_SPEC:<json>)
- write_todos: record a step-by-step plan before multi-step work
- finish: return your final answer and end the run — call exactly once when done

Rules:
- Only execute SELECT statements. Refuse any request that would mutate or destroy data.
- Always ground answers in actual query results. Do not invent data or statistics.
- Look up table names and column names from the dataset schema — never guess them.
- When the answer is a chart, return finish(answer="CHART_SPEC:<plotly_json>").
- Keep answers concise. Lead with the direct answer, then 1-3 sentences of interpretation.
- If asked to do something outside data analysis, decline and redirect.

{schema_section}"""


def _build_system_prompt(dataset_schema: dict | None = None) -> str:
    if dataset_schema:
        cols = dataset_schema.get("columns", {})
        col_str = ", ".join(f"{c} ({t})" for c, t in cols.items())
        table_name = dataset_schema.get("table_name", "")
        schema_section = f"Active dataset — table: {table_name}\nColumns: {col_str}"
    else:
        schema_section = "No dataset is active. Ask the user to upload a CSV or JSON file first."
    return DOMAIN_PROMPT_BASE.format(schema_section=schema_section)


async def _get_dataset_schema(dataset_id: str | None) -> dict | None:
    if not dataset_id:
        return None
    async with get_sessionmaker()() as s:
        ds = (await s.execute(select(Dataset).where(Dataset.id == dataset_id))).scalar_one_or_none()
    if ds is None:
        return None
    return {**ds.schema_json, "table_name": ds.table_name}


_ROLE_TO_CLASS = {"human": HumanMessage, "assistant": AIMessage, "tool": ToolMessage}


async def _load_thread_history(thread_id: str) -> list:
    """Load prior AI+human messages for this thread to enable multi-turn context."""
    async with get_sessionmaker()() as s:
        prior_runs = (await s.execute(
            select(Run).where(Run.thread_id == thread_id, Run.status == "completed")
            .order_by(Run.created_at.asc())
        )).scalars().all()
        if not prior_runs:
            return []
        run_ids = [r.id for r in prior_runs]
        msgs = (await s.execute(
            select(Message)
            .where(Message.run_id.in_(run_ids), Message.role.in_(["human", "assistant"]))
            .order_by(Message.created_at.asc())
        )).scalars().all()

    history = []
    for m in msgs:
        cls = _ROLE_TO_CLASS.get(m.role, HumanMessage)
        history.append(cls(content=m.content))
    return history


async def run_agent(
    goal: str,
    thread_id: str | None = None,
    dataset_id: str | None = None,
    model=None,
    run_id: str | None = None,
) -> dict:
    settings = get_settings()
    run_id = run_id or uuid.uuid4().hex
    model = model or get_model()
    thread_id = thread_id or uuid.uuid4().hex

    # No external checkpointer — multi-turn via manual history loading
    graph = build_graph(model)

    dataset_schema = await _get_dataset_schema(dataset_id)
    system_prompt = _build_system_prompt(dataset_schema)

    # Load prior conversation turns for this thread
    history = await _load_thread_history(thread_id)

    async with get_sessionmaker()() as s:
        s.add(Run(
            id=run_id, goal=goal, status="running", iterations=0,
            thread_id=thread_id, dataset_id=dataset_id,
        ))
        await s.commit()

    # Always fresh SystemMessage (current schema), then history, then new goal
    messages = [SystemMessage(content=system_prompt)] + history + [HumanMessage(content=goal)]

    state = {
        "messages": messages,
        "iterations": 0,
        "answer": None,
        "run_id": run_id,
    }

    async with span(run_id, "invoke_agent", "INTERNAL", goal=goal):
        result = await graph.ainvoke(state, config={"recursion_limit": 50})

    # Tally tokens from LLM spans
    input_tokens = 0
    output_tokens = 0
    async with get_sessionmaker()() as s:
        spans = (await s.execute(select(Span).where(Span.run_id == run_id, Span.kind == "LLM"))).scalars().all()
        for sp in spans:
            toks = sp.attributes.get("tokens") or {}
            input_tokens += toks.get("input", 0)
            output_tokens += toks.get("output", 0)
    cost_usd = (input_tokens / 1_000_000) * settings.cost_per_1m_input + \
               (output_tokens / 1_000_000) * settings.cost_per_1m_output

    async with get_sessionmaker()() as s:
        for m in result["messages"]:
            role = "assistant" if isinstance(m, AIMessage) else getattr(m, "type", "system")
            content = m.content if isinstance(m.content, str) else str(m.content)
            s.add(Message(id=uuid.uuid4().hex, run_id=run_id, role=role, content=content))
        run_obj = (await s.execute(select(Run).where(Run.id == run_id))).scalar_one()
        run_obj.status = "completed"
        run_obj.answer = result["answer"]
        run_obj.iterations = result["iterations"]
        run_obj.input_tokens = input_tokens
        run_obj.output_tokens = output_tokens
        run_obj.cost_usd = cost_usd
        await s.commit()

    # Update thread totals
    async with get_sessionmaker()() as s:
        th = (await s.execute(select(Thread).where(Thread.id == thread_id))).scalar_one_or_none()
        if th is None:
            s.add(Thread(
                id=thread_id, dataset_id=dataset_id,
                total_tokens=input_tokens + output_tokens,
                total_cost_usd=cost_usd,
            ))
        else:
            th.total_tokens += input_tokens + output_tokens
            th.total_cost_usd += cost_usd
        await s.commit()

    return {
        "run_id": run_id,
        "thread_id": thread_id,
        "answer": result["answer"],
        "iterations": result["iterations"],
        "messages": result["messages"],
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": cost_usd,
    }
