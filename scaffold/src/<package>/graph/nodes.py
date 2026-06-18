from <package>.graph.state import AgentState

STUB_RESULT = {"stub": True}  # replace with real call in Phase 3+


def fetch_data(state: AgentState) -> AgentState:
    return {**state, "data": STUB_RESULT}


def process(state: AgentState) -> AgentState:
    return {**state, "processed": True}


def handle_error(state: AgentState) -> AgentState:
    return {**state, "status": "failed"}


def finalize(state: AgentState) -> AgentState:
    return {**state, "status": "completed"}
