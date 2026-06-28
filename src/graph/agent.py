from langgraph.graph import StateGraph, END

from graph.state import AgentState
from graph.nodes import (
    extract_schema,
    plan_analysis,
    execute_analysis,
    format_answer,
    finalize,
    handle_error,
)
from graph.edges import (
    after_extract,
    after_plan,
    after_execute,
    after_format,
)


def _build_graph():
    graph = StateGraph(AgentState)

    graph.add_node("extract_schema", extract_schema)
    graph.add_node("plan_analysis", plan_analysis)
    graph.add_node("execute_analysis", execute_analysis)
    graph.add_node("format_answer", format_answer)
    graph.add_node("finalize", finalize)
    graph.add_node("handle_error", handle_error)

    graph.set_entry_point("extract_schema")

    graph.add_conditional_edges(
        "extract_schema",
        after_extract,
        {"handle_error": "handle_error", "plan_analysis": "plan_analysis"},
    )
    graph.add_conditional_edges(
        "plan_analysis",
        after_plan,
        {"handle_error": "handle_error", "execute_analysis": "execute_analysis"},
    )
    graph.add_conditional_edges(
        "execute_analysis",
        after_execute,
        {
            "format_answer": "format_answer",
            "plan_analysis": "plan_analysis",
            "handle_error": "handle_error",
        },
    )
    graph.add_conditional_edges(
        "format_answer",
        after_format,
        {"handle_error": "handle_error", "finalize": "finalize"},
    )
    graph.add_edge("finalize", END)
    graph.add_edge("handle_error", END)

    return graph.compile()


agentic_ai = _build_graph()
