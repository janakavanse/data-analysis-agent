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
    """Graph loop runs, tools execute, produces an answer."""
    sid = "test-loop-sess"
    csv_text = "name,age,salary\nAlice,30,70000\nBob,25,65000"
    load_resource(sid, csv_text)

    scripted = [
        AIMessage(content="", tool_calls=[{"name": "file_load", "args": {}, "id": "a"}]),
        AIMessage(content="", tool_calls=[{"name": "python_exec", "args": {"code": "df['age'].mean()"}, "id": "b"}]),
        AIMessage(content="", tool_calls=[{"name": "finish", "args": {"answer": "Mean age is 27.5"}, "id": "c"}]),
    ]

    model = FakeModel(scripted)
    graph = build_graph(model)
    state = {
        "messages": [SystemMessage(content=DOMAIN_PROMPT), HumanMessage(content="What is the mean age?")],
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
    """When the model loops without calling finish, force_finalize terminates it."""
    sid = "test-runaway-sess"
    load_resource(sid, "x,y\n1,2\n3,4")

    looping = AIMessage(content="thinking...", tool_calls=[])

    class LoopingModel:
        def bind_tools(self, tools): return self
        async def ainvoke(self, msgs): return looping

    graph = build_graph(LoopingModel())
    state = {
        "messages": [SystemMessage(content=DOMAIN_PROMPT), HumanMessage(content="test")],
        "iterations": 0, "answer": None, "run_id": "test-runaway",
    }

    token = current_session_id.set(sid)
    try:
        result = await graph.ainvoke(state, config={"recursion_limit": 50})
    finally:
        current_session_id.reset(token)
        release_session(sid)

    assert result["answer"] is not None, "force_finalize must produce an answer, never None"


# -----------------------------------------------------------
# Guardrail tests (no API key needed)
# -----------------------------------------------------------

def test_refuses_filesystem_escape():
    """safe_eval blocks filesystem escape attempts."""
    with pytest.raises(ValueError):
        safe_eval("open('/etc/passwd')", {})
    with pytest.raises(ValueError):
        safe_eval("__import__('os').system('id')", {})
    with pytest.raises(ValueError):
        safe_eval("os.listdir('/')", {"df": pd.DataFrame()})


def test_refuses_destructive():
    """safe_eval blocks dunder attribute walks and destructive builtins."""
    with pytest.raises(ValueError):
        safe_eval("().__class__.__mro__", {})
    with pytest.raises(ValueError):
        safe_eval("eval('1+1')", {})
    with pytest.raises(ValueError):
        safe_eval("exec('pass')", {})


def test_safe_eval_allows_pandas():
    """safe_eval allows normal pandas expressions."""
    df = pd.DataFrame({"age": [30, 25, 35], "salary": [70000, 65000, 90000]})
    result = safe_eval("df['age'].mean()", {"df": df, "pd": pd})
    assert abs(result - 30.0) < 0.01


# -----------------------------------------------------------
# Real LLM outcome test (requires funded key)
# -----------------------------------------------------------

@pytest.mark.skipif(not os.getenv("APP_LLM_API_KEY"), reason="real run + LLM judge needs a funded key")
async def test_demo_gate():
    """Full round-trip: load fixture → run real model → judge-stable outcome passes."""
    from agent.runner import run_agent
    from agent.evals import stable_outcome_eval
    from agent.sessions import load_resource

    sid = "gate-sess-demo"
    fixture = open("scripts/fixtures/sample_data.csv").read()
    load_resource(sid, fixture)

    GOAL = "What is the mean value of each numeric column?"
    state = await run_agent(GOAL, run_id="gate-test-1", session_id=sid)
    assert state["status"] == "completed"
    assert state["answer"] and state["answer"] != "(no answer produced)"

    ok_o, mean, detail = await stable_outcome_eval(
        goal=GOAL,
        answer=state["answer"],
        criterion=(
            "WHEN the user uploads a CSV file and asks a statistical question "
            "the system SHALL execute Python/pandas code and return the correct computed numeric result with the code shown."
        ),
        evaluation_steps=[
            "Does the answer contain a specific numeric result (a number, not a vague description)?",
            "Does the answer include or reference Python/pandas code used to compute the result?",
            "Is the numeric result consistent with what pandas would compute on the provided data (e.g. a correct mean, count, or sum)?",
            "Is the answer free of invented data values not derivable from the uploaded file?",
        ],
    )
    release_session(sid)
    assert ok_o, f"OUTCOME failed: judge mean {mean} {detail}"
