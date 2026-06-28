"""Conditional edge functions for the analysis graph.

Edge functions are PURE routers — they only choose the next node and never
mutate state (LangGraph does not merge a router's return value). The revise
counter is bumped inside ``generate_code`` (it knows it is a revise pass when a
prior exec error is present); the best-guess ``flagged`` marker is set inside
``summarize`` when it is reached with an unresolved exec error.
"""

from graph.state import AgentState

# Phase 1 revise cap = 1 retry. Raised to 2 in later phases (spec/agent.md).
MAX_REVISIONS = 1


def guard_error(state: AgentState) -> str:
    """Route to handle_error if a node set a fatal error, else continue."""
    if state.get("error"):
        return "handle_error"
    return "ok"


def after_execute(state: AgentState) -> str:
    """Route after execute_locally.

    - exec error and revisions < MAX -> revise (regenerate code)
    - exec error and revisions >= MAX -> summarize (best-guess, flagged)
    - no error -> summarize
    """
    exec_result = state.get("exec_result") or {}
    if exec_result.get("error") and state.get("revisions", 0) < MAX_REVISIONS:
        return "revise"
    return "summarize"
