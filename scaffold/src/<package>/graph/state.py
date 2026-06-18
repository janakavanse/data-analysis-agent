from typing import TypedDict


class AgentState(TypedDict, total=False):
    run_id: str
    error: str | None
    # add domain fields here.
    # For a ReAct loop, also carry action_history / iteration_count / llm_response / usage
    # fields — see ../../../spec/engineering/patterns/react-agent.md § State.
