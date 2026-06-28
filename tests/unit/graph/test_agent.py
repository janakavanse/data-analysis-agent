"""The analysis graph must compile and expose the six nodes — no env/LLM needed."""


def test_graph_compiles():
    from graph.agent import agentic_ai

    assert agentic_ai is not None


def test_graph_has_expected_nodes():
    from graph.agent import agentic_ai

    nodes = set(agentic_ai.get_graph().nodes)
    for expected in (
        "extract_schema",
        "plan_analysis",
        "execute_analysis",
        "format_answer",
        "finalize",
        "handle_error",
    ):
        assert expected in nodes, f"missing node {expected!r}"


def test_entry_point_is_extract_schema():
    from graph.agent import agentic_ai

    g = agentic_ai.get_graph()
    # LangGraph models the entry point as an edge from the START sentinel.
    targets = {e.target for e in g.edges if e.source == "__start__"}
    assert "extract_schema" in targets


def test_after_execute_routing():
    from graph.edges import after_execute

    assert after_execute({"result_repr": {"kind": "scalar", "value": 1}}) == "format_answer"
    assert after_execute({"exec_error": "boom", "retries": 1}) == "plan_analysis"
    assert after_execute({"error": "fatal"}) == "handle_error"
