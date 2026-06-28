from pydantic import BaseModel


class QueryRequest(BaseModel):
    dataset_id: str | None = None
    question: str | None = None
