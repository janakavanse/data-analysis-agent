"""Conditional-edge routers for the analysis loop."""

from graph.state import AgentState


def has_error(state: AgentState) -> bool:
    return bool(state.get("error"))


def after_extract(state: AgentState) -> str:
    return "handle_error" if state.get("error") else "plan_analysis"


def after_plan(state: AgentState) -> str:
    return "handle_error" if state.get("error") else "execute_analysis"


def after_execute(state: AgentState) -> str:
    """success -> format_answer; exec_error -> plan_analysis (repair); error -> handle_error.

    ``execute_analysis`` only leaves ``exec_error`` set (without ``error``)
    when a repair is still available — it promotes the failure to ``error``
    once the retry budget is exhausted — so this router can dispatch purely on
    which key is set.
    """
    if state.get("error"):
        return "handle_error"
    if state.get("exec_error"):
        return "plan_analysis"
    return "format_answer"


def after_format(state: AgentState) -> str:
    return "handle_error" if state.get("error") else "finalize"
