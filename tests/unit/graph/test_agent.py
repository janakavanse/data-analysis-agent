def test_graph_compiles():
    """Graph compiles without requiring any env vars."""
    from graph.agent import agentic_ai
    assert agentic_ai is not None


def test_graph_has_finalize_clarification_node():
    """Phase 2: needs_clarification/unanswerable route to a distinct
    terminal node that never executes code."""
    from graph.agent import agentic_ai
    nodes = agentic_ai.get_graph().nodes
    assert "finalize_clarification" in nodes


def test_after_generate_code_routes_clarification_and_unanswerable_to_finalize():
    from graph.edges import after_generate_code

    assert after_generate_code({"status_decision": "needs_clarification"}) == "finalize_clarification"
    assert after_generate_code({"status_decision": "unanswerable"}) == "finalize_clarification"
    assert after_generate_code({"status_decision": "ok"}) == "execute_code"
    assert after_generate_code({"error": "boom", "status_decision": "ok"}) == "handle_error"
