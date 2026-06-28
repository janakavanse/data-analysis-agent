"""Pydantic request model + payload shaping for the analysis endpoints.

Mirrors the contract in ``spec/api.md`` for ``POST /analyses`` and
``GET /analyses/{run_id}``. The request body is a typed model; the response is
built as a plain ``dict`` from a persisted ``RunRow`` to keep the wire shape exact
and avoid coupling serialization to optional/JSON columns.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

if TYPE_CHECKING:  # pragma: no cover - typing only
    from db.models import RunRow


class AnalysisRequest(BaseModel):
    """Body of ``POST /analyses``."""

    dataset_id: str
    question: str


def run_payload(run: "RunRow", *, include_run_detail: bool = False) -> dict[str, Any]:
    """Shape a ``RunRow`` into the ``POST /analyses`` response payload.

    ``include_run_detail`` adds the extra fields ``GET /analyses/{run_id}`` carries
    (``started_at``, ``completed_at``, ``revisions``, ``error_message``).
    """
    payload: dict[str, Any] = {
        "run_id": run.id,
        "status": run.status,
        "stage": run.stage,
        "answer": run.answer,
        "key_numbers": run.key_numbers_json,
        "summary_table": run.result_json,
        "chart_spec": run.chart_spec_json,
        "code": run.code,
        "llm_payload": run.llm_payload_json,
        "tokens_in": run.tokens_in,
        "tokens_out": run.tokens_out,
        "cost_estimate": run.cost_estimate,
        "flagged": run.flagged,
    }
    if include_run_detail:
        payload["started_at"] = (
            run.started_at.isoformat() if run.started_at is not None else None
        )
        payload["completed_at"] = (
            run.completed_at.isoformat() if run.completed_at is not None else None
        )
        payload["revisions"] = run.revisions
        payload["error_message"] = run.error_message
    return payload
