from <package>.graph.state import AgentState


def after_fetch(state: AgentState) -> str:
    if state.get("error"):
        return "handle_error"
    return "process"


def after_process(state: AgentState) -> str:
    if state.get("error"):
        return "handle_error"
    return "finalize"
