from graph.state import AgentState


def after_generate_code(state: AgentState) -> str:
    if state.get("error"):
        return "handle_error"
    return "execute_code"


def after_execute_code(state: AgentState) -> str:
    if state.get("last_error") is None:
        return "finalize"
    if state.get("retry_count", 0) >= 1:
        return "handle_error"
    return "generate_code"
