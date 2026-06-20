from langchain_core.messages import BaseMessage
from typing import TypedDict


class AgentState(TypedDict):
    messages: list[BaseMessage]   # plain list — NO add_messages reducer (react-agent.md WARNING)
    iterations: int
    answer: str | None
    run_id: str
