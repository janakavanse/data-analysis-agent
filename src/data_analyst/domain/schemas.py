from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, field_validator


class DatasetResponse(BaseModel):
    dataset_id: str
    name: str
    description: str | None
    table_name: str
    original_filename: str
    file_extension: str
    row_count: int
    column_count: int
    schema: list[dict[str, Any]] | None = None
    is_active: bool
    upload_timestamp: datetime

    @field_validator("schema", mode="before")
    @classmethod
    def _parse_schema(cls, v: Any) -> list[dict[str, Any]] | None:
        if isinstance(v, str):
            return json.loads(v)
        return v


class DatasetListResponse(BaseModel):
    datasets: list[DatasetResponse]
    count: int


class ChatRequest(BaseModel):
    session_id: str | None = None
    message: str


class ChatResponse(BaseModel):
    session_id: str
    response_markdown: str
    generated_sql: str | None
    datasets_touched: list[str]
    row_count_returned: int | None
    latency_ms: int


class TurnResponse(BaseModel):
    role: str
    content: str
    turn_index: int
    created_at: datetime


class SessionHistoryResponse(BaseModel):
    session_id: str
    created_at: datetime
    last_active: datetime
    turns: list[TurnResponse]


class HealthResponse(BaseModel):
    status: str
    sqlite: str
    duckdb: str
    registered_tables: int
