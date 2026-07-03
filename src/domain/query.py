from pydantic import BaseModel


class QueryRequest(BaseModel):
    dataset_id: str
    question: str


class QueryResponse(BaseModel):
    query_id: str
    status: str
    question: str
    turn_index: int
    answer_text: str | None = None
    result_table: list[dict] | None = None
    generated_code: str | None = None
    retry_count: int = 0
    token_usage: dict | None = None
    chart_spec: dict | None = None
    suggested_followups: list[str] | None = None
    error: str | None = None
    created_at: str
    completed_at: str | None = None


class QueryHistoryItem(BaseModel):
    query_id: str
    turn_index: int
    question: str
    status: str
    answer_text: str | None = None
