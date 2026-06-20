import os
import pytest
import pandas as pd
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from agent.guardrails import safe_eval
from agent.graph import build_graph
from agent.runner import DOMAIN_PROMPT
from agent.sessions import current_session_id, load_resource, release_session


class FakeModel:
    def __init__(self, scripted):
        self.s = list(scripted)
        self.i = 0

    def bind_tools(self, tools):
        return self

    async def ainvoke(self, msgs):
        m = self.s[min(self.i, len(self.s) - 1)]
        self.i += 1
        return m


# -----------------------------------------------------------
# Mechanical loop tests (no API key needed)
# -----------------------------------------------------------

async def test_fake_model_loop():
    """Graph loop runs, search_document executes, produces a grounded answer."""
    sid = "test-loop-sess"
    load_resource(sid, "Vacation: employees get 20 paid days per year.\n\nSick leave: 10 days per year.")

    scripted = [
        AIMessage(content="", tool_calls=[{"name": "search_document", "args": {"query": "vacation days"}, "id": "a"}]),
        AIMessage(content="", tool_calls=[{"name": "finish", "args": {"answer": "Employees get 20 vacation days."}, "id": "b"}]),
    ]

    graph = build_graph(FakeModel(scripted))
    state = {
        "messages": [SystemMessage(content=DOMAIN_PROMPT), HumanMessage(content="How many vacation days?")],
        "iterations": 0, "answer": None, "run_id": "test-loop-1",
    }
    token = current_session_id.set(sid)
    try:
        result = await graph.ainvoke(state, config={"recursion_limit": 50})
    finally:
        current_session_id.reset(token)
        release_session(sid)

    assert result["iterations"] >= 2
    assert result["answer"] is not None
    assert result["answer"] != "(no answer produced)"


async def test_force_finalize():
    """When the model loops without calling finish, force_finalize terminates it with an answer."""
    looping = AIMessage(content="thinking...", tool_calls=[])

    class LoopingModel:
        def bind_tools(self, tools): return self
        async def ainvoke(self, msgs): return looping

    graph = build_graph(LoopingModel())
    state = {
        "messages": [SystemMessage(content=DOMAIN_PROMPT), HumanMessage(content="test")],
        "iterations": 0, "answer": None, "run_id": "test-runaway",
    }
    result = await graph.ainvoke(state, config={"recursion_limit": 50})
    assert result["answer"] is not None, "force_finalize must produce an answer, never None"


# -----------------------------------------------------------
# Guardrail unit tests (no API key) — the AST-safe-eval utility (guardrails.py)
# -----------------------------------------------------------

def test_refuses_filesystem_escape():
    with pytest.raises(ValueError):
        safe_eval("open('/etc/passwd')", {})
    with pytest.raises(ValueError):
        safe_eval("__import__('os').system('id')", {})


def test_refuses_destructive():
    with pytest.raises(ValueError):
        safe_eval("().__class__.__mro__", {})
    with pytest.raises(ValueError):
        safe_eval("eval('1+1')", {})


def test_safe_eval_allows_pandas():
    df = pd.DataFrame({"age": [30, 25, 35]})
    assert abs(safe_eval("df['age'].mean()", {"df": df, "pd": pd}) - 30.0) < 0.01


# -----------------------------------------------------------
# Real LLM tests (require funded key)
# -----------------------------------------------------------

@pytest.mark.skipif(not os.getenv("APP_LLM_API_KEY"), reason="real run + LLM judge needs a funded key")
async def test_demo_gate():
    """Full round-trip: load the handbook → ask a grounded question → judge-stable outcome passes."""
    from agent.runner import run_agent
    from agent.evals import stable_outcome_eval

    sid = "gate-sess-demo"
    load_resource(sid, open("scripts/fixtures/handbook.txt").read())

    GOAL = "How many paid vacation days do full-time employees get per year?"
    state = await run_agent(GOAL, run_id="gate-test-1", session_id=sid)
    assert state["status"] == "completed"
    assert state["answer"] and state["answer"] != "(no answer produced)"

    from agent.gate_eval import CRITERION, EVALUATION_STEPS
    ok_o, mean, detail = await stable_outcome_eval(
        goal=GOAL, answer=state["answer"],
        criterion=CRITERION, evaluation_steps=EVALUATION_STEPS,
    )
    release_session(sid)
    assert ok_o, f"OUTCOME failed: judge mean {mean} {detail}"


@pytest.mark.skipif(not os.getenv("APP_LLM_API_KEY"), reason="real run needs a funded key")
async def test_followup_retains_document():
    """A follow-up on the same session is answered from the retained document — no re-upload."""
    from agent.runner import run_agent

    sid = "gate-sess-followup"
    load_resource(sid, open("scripts/fixtures/handbook.txt").read())

    s1 = await run_agent("How many paid vacation days do full-time employees get per year?",
                         run_id="ret-1", session_id=sid)
    assert s1["status"] == "completed"

    s2 = await run_agent("How far in advance must I request time off?",
                         run_id="ret-2", session_id=sid)
    release_session(sid)
    assert s2["status"] == "completed"
    ans = (s2["answer"] or "").lower()
    assert ans and "no document" not in ans, f"follow-up lost the retained document: {s2['answer']}"
    assert "week" in ans, f"expected the retained-doc answer to mention weeks, got: {s2['answer']}"
