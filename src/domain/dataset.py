"""Pydantic models for the dataset-upload endpoint (``POST /datasets``).

The wire response uses the field name ``schema`` (per api.md). ``schema``
shadows ``BaseModel.schema``, so the model field is named ``schema_data``
and serialized under the alias ``schema``.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SchemaColumn(BaseModel):
    """One column of the privacy-safe schema: name + pandas dtype string."""

    name: str
    dtype: str


class DatasetUploadData(BaseModel):
    """Privacy-safe metadata returned after a CSV upload.

    The raw dataset never leaves the machine — only the schema, a tiny
    N-row sample, and the row count are surfaced.
    """

    model_config = ConfigDict(populate_by_name=True)

    session_id: str
    filename: str
    row_count: int
    schema_data: list[SchemaColumn] = Field(serialization_alias="schema")
    sample_rows: list[dict[str, Any]]
