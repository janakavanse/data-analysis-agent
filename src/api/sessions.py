"""Session endpoints: ask a question, and load the transcript for replay.

- ``POST /sessions/{session_id}/ask`` runs one analysis turn over the
  session's DataFrame (the runner persists the user + assistant messages).
- ``GET /sessions/{session_id}`` returns the dataset header + the full ordered
  transcript for replay.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from analysis.store import ensure_loaded
from api._common import api_error, ok
from db.models import Dataset, Message, Session as SessionRow
from db.session import get_session
from domain.message import AskRequest
from graph.runner import run_analysis

router = APIRouter()


def _get_dataset(db: Session, session_id: str) -> Dataset:
    """Return the dataset for a session or raise 404 for an unknown session."""
    session_row = db.get(SessionRow, session_id)
    if session_row is None:
        raise api_error("NOT_FOUND", f"Session {session_id!r} not found.", 404)
    dataset = db.execute(
        select(Dataset).where(Dataset.session_id == session_id)
    ).scalars().first()
    if dataset is None:
        raise api_error("NOT_FOUND", f"Session {session_id!r} has no dataset.", 404)
    return dataset


def _parse_json(raw: str | None) -> Any:
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


@router.post("/sessions/{session_id}/ask")
def ask(
    session_id: str,
    req: AskRequest,
    db: Session = Depends(get_session),
) -> dict:
    question = (req.question or "").strip()

    dataset = _get_dataset(db, session_id)

    if not question:
        raise api_error("BAD_REQUEST", "The question must not be empty.")

    # Ensure the DataFrame is loaded (lazily reload from disk after a restart);
    # the graph also lazy-reloads, but failing fast here gives a clean error.
    try:
        ensure_loaded(session_id, dataset.file_path, dataset.file_type)
    except Exception as exc:  # noqa: BLE001
        raise api_error(
            "INTERNAL",
            f"The dataset for this session could not be loaded: {exc}",
            500,
        )

    # run_analysis persists the user + assistant messages via the finalize node.
    result = run_analysis(session_id, question)

    return ok(
        {
            "answer": result.get("answer") or "",
            "code": result.get("code"),
            "result_table": result.get("result_table"),
            "status": result.get("status", "completed"),
        }
    )


@router.get("/sessions/{session_id}")
def get_session_transcript(
    session_id: str,
    db: Session = Depends(get_session),
) -> dict:
    dataset = _get_dataset(db, session_id)

    messages = db.execute(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at.asc())
    ).scalars().all()

    transcript: list[dict[str, Any]] = []
    for m in messages:
        entry: dict[str, Any] = {
            "role": m.role,
            "content": m.content,
            "code": m.code,
            "result_table": _parse_json(m.result_json),
            "status": m.status,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        transcript.append(entry)

    return ok(
        {
            "session_id": session_id,
            "dataset": {
                "filename": dataset.filename,
                "row_count": dataset.row_count,
                "schema": _parse_json(dataset.schema_json) or [],
            },
            "messages": transcript,
        }
    )
