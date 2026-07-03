from typing import TypedDict


class AgentState(TypedDict, total=False):
    # Identity
    query_id: str
    session_id: str
    dataset_id: str

    # Input (populated at initialisation, read-only during the run)
    dataset_path: str
    file_type: str
    dataset_schema: dict                 # DatasetSchema.model_dump() — the ONLY dataset info ever in state
    question: str
    conversation_history: list[dict]     # [{"question": str, "answer": str}, ...]

    # Pipeline data (populated progressively by nodes)
    generated_code: str | None
    retry_count: int
    last_error: str | None

    # Output
    answer_text: str | None
    result_table: list[dict] | None
    token_usage: dict | None

    # Control
    error: str | None
    status: str | None
