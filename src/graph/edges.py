"""Conditional edge routers for the analysis pipeline (see spec/agent.md)."""

from __future__ import annotations

from graph.state import AgentState


def route_after_plan(state: AgentState) -> str:
    return "handle_error" if state.get("error") else "generate_code"


def route_after_codegen(state: AgentState) -> str:
    return "handle_error" if state.get("error") else "execute_locally"


def route_after_exec(state: AgentState) -> str:
    """One-shot repair loop.

    - success (no error) -> summarize
    - exec error & not yet repaired -> generate_code (the repair attempt)
    - exec error & already repaired -> handle_error

    ``execute_locally`` sets ``repair_attempted=True`` whenever it records an
    error, so the FIRST failure routes back to generate_code (which clears the
    error and regenerates), and a SECOND failure routes to handle_error.
    """
    if not state.get("error"):
        return "summarize"
    # An error is present. The first sandbox failure (exec_failures == 1) routes
    # back to generate_code for the single repair attempt; a second failure
    # (exec_failures >= 2) gives up to handle_error.
    if int(state.get("exec_failures", 0)) >= 2:
        return "handle_error"
    return "generate_code"


def route_after_summarize(state: AgentState) -> str:
    return "handle_error" if state.get("error") else "finalize"
