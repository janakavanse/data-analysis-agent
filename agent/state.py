from langchain_core.messages import BaseMessage
from typing import TypedDict


class AgentState(TypedDict):
    messages: list[BaseMessage]  # plain list — no add_messages reducer (see patterns/react-agent.md)
    iterations: int
    answer: str | None
    run_id: str
