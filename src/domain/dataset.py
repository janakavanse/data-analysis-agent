"""Dataset payload shaping for the dataset endpoints.

Mirrors the contract in ``spec/api.md`` for ``POST /datasets`` and
``GET /datasets/{dataset_id}``. ``POST /datasets`` takes a multipart ``file`` (no
JSON body), so there is no request model — only a helper that shapes the response
payload from a persisted ``DatasetRow``.

The response payload uses a ``schema`` key (required by the contract). ``schema``
collides with a reserved Pydantic ``BaseModel`` attribute, so the payload is built
as a plain ``dict`` rather than via a model — keeping the wire shape exact.
"""

from __future__ import annotations

from typing import Any


def dataset_payload(
    *,
    dataset_id: str,
    name: str,
    schema: list[dict[str, Any]],
    sample: list[dict[str, Any]],
    row_count: int,
) -> dict[str, Any]:
    """Build the exact ``{dataset_id, name, schema, sample, row_count}`` payload."""
    return {
        "dataset_id": dataset_id,
        "name": name,
        "schema": schema,
        "sample": sample,
        "row_count": row_count,
    }
