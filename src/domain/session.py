"""Pydantic models for the session-load endpoint (``GET /sessions/{id}``)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from domain.message import TranscriptMessage


class SessionDatasetHeader(BaseModel):
    """The dataset header shown at the top of a loaded session."""

    model_config = ConfigDict(populate_by_name=True)

    filename: str
    row_count: int
    schema_data: list[dict[str, Any]] = Field(serialization_alias="schema")


class SessionData(BaseModel):
    """A loaded session: dataset header + full ordered transcript for replay."""

    session_id: str
    dataset: SessionDatasetHeader
    messages: list[TranscriptMessage]
