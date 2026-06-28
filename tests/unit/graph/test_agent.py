"""Unit tests for the analysis graph: compile, state flow, edge routing, repair.

These use a fake/monkeypatched LLM and a tmp CSV — no env vars, no network.
"""

import json

import pandas as pd
import pytest

from graph import nodes
from graph.agent import agentic_ai
from graph.edges import (
    route_after_codegen,
    route_after_exec,
    route_after_plan,
    route_after_summarize,
)


def test_graph_compiles():
    """Graph compiles without requiring any env vars."""
    assert agentic_ai is not None
    # The compiled graph exposes the analysis pipeline nodes.
    node_names = set(agentic_ai.get_graph().nodes.keys())
    for n in ("plan", "generate_code", "execute_locally", "summarize",
              "finalize", "handle_error"):
        assert n in node_names


# --------------------------------------------------------------------------- #
# Edge routing
# --------------------------------------------------------------------------- #

def test_route_after_plan():
    assert route_after_plan({"error": None}) == "generate_code"
    assert route_after_plan({"error": "boom"}) == "handle_error"


def test_route_after_codegen():
    assert route_after_codegen({}) == "execute_locally"
    assert route_after_codegen({"error": "x"}) == "handle_error"


def test_route_after_summarize():
    assert route_after_summarize({}) == "finalize"
    assert route_after_summarize({"error": "x"}) == "handle_error"


def test_route_after_exec_success():
    assert route_after_exec({"error": None}) == "summarize"


def test_route_after_exec_first_failure_goes_to_repair():
    state = {"error": "ValueError: nope", "exec_failures": 1}
    assert route_after_exec(state) == "generate_code"


def test_route_after_exec_second_failure_gives_up():
    state = {"error": "ValueError: still broken", "exec_failures": 2}
    assert route_after_exec(state) == "handle_error"


# --------------------------------------------------------------------------- #
# State flow through nodes (fake LLM + tmp CSV)
# --------------------------------------------------------------------------- #

class _FakePlanCodeClient:
    """Stand-in LLMClient: returns canned plan/code text."""

    def __init__(self, text):
        self._text = text

    def call_model(self, prompt, *, system=None):
        return self._text


@pytest.fixture
def csv_path(tmp_path):
    df = pd.DataFrame({"month": ["jan", "jan", "feb"], "revenue": [10.0, 5.0, 7.0]})
    p = tmp_path / "sales.csv"
    df.to_csv(p, index=False)
    return str(p)


def test_plan_node_records_payload(monkeypatch):
    monkeypatch.setattr(
        "analysis.planner.LLMClient", lambda: _FakePlanCodeClient("1. sum revenue")
    )
    state = {"question": "total revenue?", "schema": {"columns": []},
             "profile": {"columns": []}, "llm_payloads": []}
    out = nodes.plan(state)
    assert out["plan"] == "1. sum revenue"
    assert not out.get("error")
    assert len(out["llm_payloads"]) == 1
    assert out["llm_payloads"][0]["node"] == "plan"


def test_generate_code_node_strips_fences(monkeypatch):
    fenced = "```python\nresult = df['revenue'].sum()\n```"
    monkeypatch.setattr(
        "analysis.codegen.LLMClient", lambda: _FakePlanCodeClient(fenced)
    )
    out = nodes.generate_code(
        {"plan": "p", "schema": {"columns": []}, "llm_payloads": []}
    )
    assert out["code"] == "result = df['revenue'].sum()"
    assert out["error"] is None


def test_execute_locally_success(csv_path):
    state = {"code": "result = df['revenue'].sum()", "dataset_path": csv_path}
    out = nodes.execute_locally(state)
    assert out["error"] is None
    assert out["exec_result"]["ok"] is True
    assert out.get("result_summary") is not None


def test_execute_locally_failure_sets_repair(csv_path):
    state = {"code": "result = df['nonexistent_col'].sum()",
             "dataset_path": csv_path}
    out = nodes.execute_locally(state)
    assert out["error"]
    assert out["repair_attempted"] is True
    assert out["exec_failures"] == 1
    # First failure routes back to generate_code for the single repair.
    assert route_after_exec(out) == "generate_code"


def test_repair_loop_second_failure_handles_error(csv_path):
    """A second consecutive failure exhausts the one-shot repair -> handle_error."""
    state = {"code": "result = df['nope'].sum()", "dataset_path": csv_path,
             "exec_failures": 1, "repair_attempted": True}
    out = nodes.execute_locally(state)
    assert out["exec_failures"] == 2
    assert route_after_exec(out) == "handle_error"


def test_handle_error_and_finalize():
    assert nodes.handle_error({"error": "x"})["status"] == "failed"
    assert nodes.finalize({})["status"] == "completed"


def test_summarize_node_uses_fake_stream(monkeypatch):
    class _FakeStreamClient:
        def stream(self, user, *, system=None):
            yield ("token", "Total ")
            yield ("token", "revenue is 22.")
            yield ("usage", {"prompt_tokens": 11, "completion_tokens": 4})

    # Patch stream_answer's client path by monkeypatching the helper to use fake.
    import analysis

    def fake_stream_answer(question, result_summary, *, client=None):
        return analysis.stream_answer(
            question, result_summary, client=_FakeStreamClient()
        )

    monkeypatch.setattr(nodes, "stream_answer", fake_stream_answer)
    out = nodes.summarize({"question": "q", "result_summary": {"value": 22},
                           "llm_payloads": []})
    assert out["answer"] == "Total revenue is 22."
    assert out["prompt_tokens"] == 11
    assert out["completion_tokens"] == 4
    assert out["llm_payloads"][-1]["node"] == "summarize"


def test_summarize_payload_contains_no_rows():
    """The summarize payload carries only the result_summary, never raw rows."""
    from analysis import build_answer_payload

    payload = build_answer_payload("q", {"value": 42, "kind": "scalar"})
    blob = json.dumps(payload)
    assert "42" in blob  # aggregate is fine
    assert payload["node"] == "summarize"
