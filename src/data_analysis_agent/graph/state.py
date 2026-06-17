from typing import TypedDict


class AgentState(TypedDict, total=False):
    run_id: str
    query_record_id: str
    session_id: str
    data_source_id: str
    question: str
    csv_path: str

    # Tool registry (loaded from DB by load_data)
    tools: list[dict]  # [{"name", "type", "capabilities": [{"name", "description", "parameter_schema"}]}]

    # Schema info (CSV sources)
    column_names: list[str]
    row_count: int

    # ReAct loop state
    action_history: list[dict]  # [{"capability", "parameters", "result", "is_error"}]
    iteration_count: int
    llm_response: str  # raw LLM output from last plan_action call

    # Final output
    answer: str

    # Usage tracking
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost_usd: float | None
    api_request_count: int

    # Control
    error: str | None
