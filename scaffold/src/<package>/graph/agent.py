from langgraph.graph import StateGraph, END
from <package>.graph.state import AgentState
from <package>.graph.nodes import fetch_data, process, handle_error, finalize
from <package>.graph.edges import after_fetch, after_process


def _build_graph() -> StateGraph:
    g = StateGraph(AgentState)
    g.add_node("fetch_data", fetch_data)
    g.add_node("process", process)
    g.add_node("handle_error", handle_error)
    g.add_node("finalize", finalize)
    g.set_entry_point("fetch_data")
    g.add_conditional_edges("fetch_data", after_fetch, {"process": "process", "handle_error": "handle_error"})
    g.add_conditional_edges("process", after_process, {"finalize": "finalize", "handle_error": "handle_error"})
    g.add_edge("finalize", END)
    g.add_edge("handle_error", END)
    return g.compile()


agent_graph = _build_graph()
