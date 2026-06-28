def test_graph_compiles():
    """Graph compiles without requiring any env vars."""
    from graph.agent import agentic_ai
    assert agentic_ai is not None


def test_graph_has_phase1_nodes():
    """The compiled graph exposes the new analysis nodes (not the old transform slot)."""
    from graph.agent import agentic_ai

    nodes = set(agentic_ai.get_graph().nodes.keys())
    expected = {
        "profile",
        "plan",
        "generate_code",
        "execute_locally",
        "summarize",
        "select_chart",
        "suggest_followups",
        "finalize",
        "handle_error",
    }
    assert expected.issubset(nodes), f"missing nodes: {expected - nodes}"
    assert "transform_text" not in nodes
