from __future__ import annotations

import json

from data_analysis_agent.graph.state import AgentState

# Prompt tag the stub provider branches on — must not change without updating stub.py.
_PLAN_TAG = "<node:plan_action>"


def build_plan_prompt(state: AgentState, datasets: list[dict]) -> str:
    """Assemble the full plan_action prompt for the current ReAct turn.

    The available-tools block is grouped by dataset (tool = dataset name) with one capability per
    table; ``datasets`` is the grouped snapshot from the ``SessionPoolManager`` (not stored in
    state). Includes the durable conversation memory, the question, prior tool-call history, and the
    two-level response format.

    Args:
        state: The current agent state carrying the question and history.
        datasets: Grouped tool list ``[{dataset, tool_description, capabilities:[{table, description,
            columns, parameter_schema}]}]``.

    Returns:
        The complete prompt string sent to the LLM.
    """
    lines = _intro_lines()
    lines += _conversation_lines(state.get("conversation", []))
    lines += _tools_lines(datasets)
    lines.append(f"User question: {state['question']}")
    lines += _history_lines(state.get("action_history", []))
    lines += _response_format_lines()
    return "\n".join(lines)


def _conversation_lines(conversation: list[dict]) -> list[str]:
    """Return the durable per-session memory block, or empty when there is none."""
    if not conversation:
        return []
    lines = ["Conversation so far (prior questions and answers in this session):"]
    for i, turn in enumerate(conversation, 1):
        lines.append(f'[{i}] Q: {turn.get("question", "")}')
        lines.append(f'    A: {turn.get("answer", "")}')
    lines.append("")
    return lines


def _intro_lines() -> list[str]:
    """Return the static ReAct-loop introduction and DuckDB dialect notes."""
    return [
        _PLAN_TAG,
        "You are a data-analysis agent operating in a ReAct (Reason + Act) loop.",
        "On each turn you either (a) call a tool capability to gather more data, or (b) give the",
        "final answer. After each call you will see its result and may call another. Build up a plan",
        "across multiple queries — and across multiple tools/tables — until you can answer.",
        "",
        "SQL dialect: DuckDB. Notes:",
        "- Aggregates available natively: COUNT, SUM, AVG, MIN, MAX, STDDEV, VARIANCE, MEDIAN, QUANTILE.",
        "- Use SQRT/ABS/ROUND for math.",
        "- Only SELECT statements are permitted.",
        "- If a column is numeric but stored as text, CAST(col AS DOUBLE) before aggregating.",
        "",
    ]


def _tools_lines(datasets: list[dict]) -> list[str]:
    """Return the grouped available-tools block (tool = dataset, capability = table)."""
    if not datasets:
        return []
    lines = [
        "Available tools. Each TOOL is a dataset; each CAPABILITY is one of its tables.",
        "Call a tool by its dataset name and one of its table capabilities.",
        "",
    ]
    for ds in datasets:
        lines.append(f"Tool: {ds['dataset']}")
        if ds.get("tool_description"):
            lines.append(f"  {ds['tool_description']}")
        capabilities = ds.get("capabilities", [])
        for cap in capabilities:
            lines.append(f"  capability: {cap['table']}")
            if cap.get("description"):
                lines.append(f"    {cap['description']}")
            if cap.get("columns"):
                lines.append(f"    columns: {', '.join(cap['columns'])}")
        if len(capabilities) > 1:
            tables = ", ".join(c["table"] for c in capabilities)
            lines.append(f"  (a capability's SQL may JOIN sibling tables in this dataset: {tables})")
        lines.append("")
    return lines


def _history_lines(history: list[dict]) -> list[str]:
    """Return the prior tool-call trace, or an empty list when there is no history."""
    if not history:
        return []
    lines = ["", "Previous tool calls and results:"]
    for i, entry in enumerate(history, 1):
        lines.append(f'[{i}] tool: {entry["tool"]} capability: {entry.get("capability", "")}')
        lines.append(f'    arguments: {json.dumps(entry["arguments"])}')
        if entry.get("is_error"):
            lines.append(f'    result: Error: {entry["result"]}')
            lines.append("    → This call failed. Please write a corrected query.")
        else:
            lines.append(f'    result:\n{entry["result"]}')
    return lines


def _response_format_lines() -> list[str]:
    """Return the closing instructions that define the tool-call / FINAL ANSWER format."""
    return [
        "",
        "Decide your next step. Respond with EXACTLY ONE of the following, and nothing else",
        "(no explanations, no markdown, no backticks):",
        "",
        "1. A JSON tool call to gather more data:",
        '   {"tool": "<dataset>", "capability": "<table>", "arguments": {"query": "SELECT ..."}}',
        "   ('tool' is a dataset name above; 'capability' is one of that dataset's tables.)",
        "",
        "2. The final answer, when you have enough information:",
        "   FINAL ANSWER: <your complete answer here>",
    ]
