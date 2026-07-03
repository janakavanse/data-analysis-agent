from langgraph.graph import StateGraph, END

from graph.state import AgentState
from graph.nodes import generate_code, execute_code, handle_error, finalize
from graph.edges import after_generate_code, after_execute_code


def _build_graph() -> StateGraph:
    g = StateGraph(AgentState)
    g.add_node("generate_code", generate_code)
    g.add_node("execute_code", execute_code)
    g.add_node("handle_error", handle_error)
    g.add_node("finalize", finalize)

    g.set_entry_point("generate_code")

    g.add_conditional_edges(
        "generate_code",
        after_generate_code,
        {"execute_code": "execute_code", "handle_error": "handle_error"},
    )
    g.add_conditional_edges(
        "execute_code",
        after_execute_code,
        {"generate_code": "generate_code", "finalize": "finalize", "handle_error": "handle_error"},
    )

    g.add_edge("finalize", END)
    g.add_edge("handle_error", END)
    return g.compile()


agentic_ai = _build_graph()
