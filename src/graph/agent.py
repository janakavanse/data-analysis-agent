"""Graph assembly for the privacy-preserving analysis pipeline (see spec/agent.md).

Compiled once as ``agentic_ai``. Topology:

    plan -> generate_code -> execute_locally -> summarize -> finalize -> END
    (errors at any node -> handle_error -> END)
    (one-shot repair: execute_locally exec-error & first failure -> generate_code)
"""

from langgraph.graph import StateGraph, END

from graph.state import AgentState
from graph.nodes import (
    plan,
    generate_code,
    execute_locally,
    summarize,
    finalize,
    handle_error,
)
from graph.edges import (
    route_after_plan,
    route_after_codegen,
    route_after_exec,
    route_after_summarize,
)


def _build_graph():
    g = StateGraph(AgentState)
    g.add_node("plan", plan)
    g.add_node("generate_code", generate_code)
    g.add_node("execute_locally", execute_locally)
    g.add_node("summarize", summarize)
    g.add_node("finalize", finalize)
    g.add_node("handle_error", handle_error)

    g.set_entry_point("plan")
    g.add_conditional_edges(
        "plan", route_after_plan,
        {"generate_code": "generate_code", "handle_error": "handle_error"},
    )
    g.add_conditional_edges(
        "generate_code", route_after_codegen,
        {"execute_locally": "execute_locally", "handle_error": "handle_error"},
    )
    g.add_conditional_edges(
        "execute_locally", route_after_exec,
        {
            "summarize": "summarize",
            "generate_code": "generate_code",
            "handle_error": "handle_error",
        },
    )
    g.add_conditional_edges(
        "summarize", route_after_summarize,
        {"finalize": "finalize", "handle_error": "handle_error"},
    )
    g.add_edge("finalize", END)
    g.add_edge("handle_error", END)
    return g.compile()


agentic_ai = _build_graph()
