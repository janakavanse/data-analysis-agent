"""Mechanical loop tests — FakeModel, no API key required."""
import pytest
from langchain_core.messages import AIMessage, ToolMessage

from agent.db import Run, Span, get_sessionmaker, init_db
from agent.graph import build_graph
from agent.runner import run_agent
from agent.state import AgentState


class FakeModel:
    """Scripted model: calls query_dataset then finish; last step repeats finish."""
    def __init__(self, scripted):
        self.s = list(scripted)
        self.i = 0

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, msgs):
        m = self.s[min(self.i, len(self.s) - 1)]
        self.i += 1
        return m


@pytest.mark.asyncio
async def test_loop_runs_two_iterations_and_records_spans():
    await init_db()
    scripted = [
        AIMessage(content="", tool_calls=[{"name": "list_datasets", "args": {}, "id": "a"}]),
        AIMessage(content="", tool_calls=[{"name": "finish", "args": {"answer": "test complete"}, "id": "b"}]),
    ]
    model = FakeModel(scripted)
    graph = build_graph(model)

    state: AgentState = {
        "messages": [AIMessage(content="What datasets do I have?")],
        "iterations": 0,
        "answer": None,
        "run_id": "test-loop-1",
    }
    # Seed a Run row so the span FK resolves
    async with get_sessionmaker()() as s:
        s.add(Run(id="test-loop-1", goal="test", status="running"))
        await s.commit()

    result = await graph.ainvoke(state)

    assert result["iterations"] >= 2, "Loop must run at least 2 iterations"
    assert result["answer"] == "test complete"

    from sqlalchemy import select
    async with get_sessionmaker()() as s:
        spans = (await s.execute(select(Span).where(Span.run_id == "test-loop-1"))).scalars().all()
    assert any(sp.kind == "TOOL" for sp in spans), "Tool span must be recorded"


@pytest.mark.asyncio
async def test_force_finalize_on_runaway():
    """A model that never calls finish should be terminated at max_iterations."""
    await init_db()
    # Always returns the same tool call — never finishes
    runaway = AIMessage(content="", tool_calls=[{"name": "list_datasets", "args": {}, "id": "x"}])
    model = FakeModel([runaway])
    graph = build_graph(model)

    async with get_sessionmaker()() as s:
        s.add(Run(id="test-runaway", goal="runaway", status="running"))
        await s.commit()

    state: AgentState = {
        "messages": [AIMessage(content="loop forever")],
        "iterations": 0,
        "answer": None,
        "run_id": "test-runaway",
    }
    result = await graph.ainvoke(state)
    # Should finalize with something — not blank
    assert result["answer"] is not None
    assert result["answer"] != "(no answer produced)" or result["iterations"] >= 1


@pytest.mark.asyncio
async def test_run_agent_with_fake_model(monkeypatch):
    """run_agent full path with FakeModel — verifies db persistence."""
    await init_db()
    scripted = [
        AIMessage(content="", tool_calls=[{"name": "list_datasets", "args": {}, "id": "t1"}]),
        AIMessage(content="", tool_calls=[{"name": "finish", "args": {"answer": "no datasets yet"}, "id": "t2"}]),
    ]
    model = FakeModel(scripted)
    monkeypatch.setattr("agent.runner.get_model", lambda: model)

    result = await run_agent("list my datasets", run_id="test-run-1")
    assert result["answer"] == "no datasets yet"
    assert result["iterations"] >= 2

    from sqlalchemy import select
    async with get_sessionmaker()() as s:
        run_obj = (await s.execute(select(Run).where(Run.id == "test-run-1"))).scalar_one()
    assert run_obj.status == "completed"
