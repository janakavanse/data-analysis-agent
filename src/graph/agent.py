from langgraph.graph import StateGraph, END

from graph.state import AgentState
from graph import nodes, edges


def _build_graph():
    g = StateGraph(AgentState)
    g.add_node("profile", nodes.profile)
    g.add_node("plan", nodes.plan)
    g.add_node("generate_code", nodes.generate_code)
    g.add_node("execute_locally", nodes.execute_locally)
    g.add_node("summarize", nodes.summarize)
    g.add_node("select_chart", nodes.select_chart)
    g.add_node("suggest_followups", nodes.suggest_followups)  # stub -> [] in Phase 1
    g.add_node("finalize", nodes.finalize)
    g.add_node("handle_error", nodes.handle_error)

    g.set_entry_point("profile")
    g.add_conditional_edges(
        "profile", edges.guard_error, {"ok": "plan", "handle_error": "handle_error"}
    )
    g.add_conditional_edges(
        "plan", edges.guard_error, {"ok": "generate_code", "handle_error": "handle_error"}
    )
    g.add_conditional_edges(
        "generate_code", edges.guard_error,
        {"ok": "execute_locally", "handle_error": "handle_error"},
    )
    g.add_conditional_edges(
        "execute_locally", edges.after_execute,
        {"revise": "generate_code", "summarize": "summarize"},
    )
    g.add_edge("summarize", "select_chart")
    g.add_edge("select_chart", "suggest_followups")
    g.add_edge("suggest_followups", "finalize")
    g.add_edge("finalize", END)
    g.add_edge("handle_error", END)
    return g.compile()


agentic_ai = _build_graph()   # keep the skeleton's exported name
