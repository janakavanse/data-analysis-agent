"""Streaming query endpoint (spec/api.md, Phase 1).

POST /sessions/{session_id}/query — SSE stream of the analysis run.

The graph runner (:func:`graph.runner.stream_query`) yields event dicts; this
router serializes each to the SSE wire format and streams it to the client.
``session_id`` may be ``"new"`` to create a session on the fly.
"""

from __future__ import annotations

import json
from typing import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from api._common import api_error
from domain.query import QueryRequest
from graph.runner import DatasetNotFoundError, stream_query
from observability.events import get_logger

router = APIRouter()
logger = get_logger("api.query")

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
    "Connection": "keep-alive",
}


def _sse(event: dict) -> str:
    """Serialize an event dict to the SSE wire format."""
    name = event.get("event", "message")
    data = json.dumps(event.get("data", {}))
    return f"event: {name}\ndata: {data}\n\n"


@router.post("/sessions/{session_id}/query")
async def query_session(session_id: str, req: QueryRequest) -> StreamingResponse:
    # ---- pre-stream validation → 400 ------------------------------------- #
    dataset_id = (req.dataset_id or "").strip()
    question = (req.question or "").strip()
    if not dataset_id:
        raise api_error("BAD_REQUEST", "dataset_id is required", 400)
    if not question:
        raise api_error("BAD_REQUEST", "question is required", 400)

    # ---- start the generator; surface a 404 before the first byte -------- #
    agen = stream_query(session_id, dataset_id, question)
    try:
        first = await agen.__anext__()
    except DatasetNotFoundError as exc:
        await agen.aclose()
        raise api_error("NOT_FOUND", str(exc), 404) from exc
    except StopAsyncIteration:
        first = None

    logger.info(
        "query.stream_start",
        session_id=session_id,
        dataset_id=dataset_id,
        question_len=len(question),
    )

    async def _event_stream() -> AsyncIterator[str]:
        if first is not None:
            yield _sse(first)
        async for event in agen:
            yield _sse(event)

    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )
