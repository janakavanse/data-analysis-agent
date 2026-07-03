import json
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session

from api._common import ok, api_error
from db.models import DatasetRow, QueryRow, SessionRow
from db.session import get_session
from domain.query import QueryHistoryItem, QueryRequest, QueryResponse
from graph.runner import run_query

router = APIRouter()

_NON_TERMINAL_STATUSES = ("pending", "generating_code", "running_analysis")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt) -> str | None:
    return dt.isoformat() if dt is not None else None


def _query_response(row: QueryRow) -> dict:
    token_usage = None
    if row.total_tokens is not None or row.prompt_tokens is not None:
        token_usage = {
            "prompt_tokens": row.prompt_tokens,
            "completion_tokens": row.completion_tokens,
            "total_tokens": row.total_tokens,
            "thinking_tokens": row.thinking_tokens or 0,
        }

    result_table = json.loads(row.result_table_json) if row.result_table_json else None
    chart_spec = json.loads(row.chart_spec_json) if row.chart_spec_json else None
    suggested_followups = (
        json.loads(row.suggested_followups_json) if row.suggested_followups_json else None
    )

    return QueryResponse(
        query_id=row.id,
        status=row.status,
        question=row.question,
        turn_index=row.turn_index,
        answer_text=row.answer_text,
        result_table=result_table,
        generated_code=row.generated_code,
        retry_count=row.retry_count,
        token_usage=token_usage,
        chart_spec=chart_spec,
        suggested_followups=suggested_followups,
        error=row.error_message,
        created_at=row.created_at.isoformat(),
        completed_at=_iso(row.completed_at),
    ).model_dump()


@router.post("/sessions/{session_id}/queries")
def create_query(
    session_id: str,
    req: QueryRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
) -> dict:
    session_row = session.get(SessionRow, session_id)
    if session_row is None:
        raise api_error("NOT_FOUND", f"Session {session_id} not found", 404)

    if not req.question or not req.question.strip():
        raise api_error("INVALID_QUESTION", "Question must not be empty.", 400)

    dataset_row = session.get(DatasetRow, req.dataset_id)
    if dataset_row is None:
        raise api_error("NOT_FOUND", f"Dataset {req.dataset_id} not found", 404)
    if dataset_row.session_id != session_id:
        raise api_error(
            "INVALID_DATASET", "dataset_id does not belong to session_id.", 400
        )

    in_flight = (
        session.query(QueryRow)
        .filter(QueryRow.session_id == session_id)
        .filter(QueryRow.status.in_(_NON_TERMINAL_STATUSES))
        .first()
    )
    if in_flight is not None:
        raise api_error(
            "QUERY_IN_FLIGHT",
            f"A query is already in flight for this session: {in_flight.id}",
            409,
        )

    turn_index = (
        session.query(QueryRow).filter(QueryRow.session_id == session_id).count()
    )

    row = QueryRow(
        session_id=session_id,
        dataset_id=req.dataset_id,
        turn_index=turn_index,
        question=req.question,
        status="pending",
    )
    session.add(row)
    session_row.last_active_at = _now()
    # Commit explicitly (not just flush) before scheduling the background
    # task: FastAPI/Starlette run BackgroundTasks *before* the request's
    # dependency-cleanup commit fires, so the background task's own DB
    # session would otherwise race against an uncommitted row.
    session.commit()
    query_id = row.id

    background_tasks.add_task(run_query, query_id)

    return ok({"query_id": query_id, "status": "pending", "turn_index": turn_index})


@router.get("/queries/{query_id}")
def get_query(query_id: str, session: Session = Depends(get_session)) -> dict:
    row = session.get(QueryRow, query_id)
    if row is None:
        raise api_error("NOT_FOUND", f"Query {query_id} not found", 404)
    return ok(_query_response(row))


@router.get("/sessions/{session_id}/queries")
def list_queries(session_id: str, session: Session = Depends(get_session)) -> dict:
    session_row = session.get(SessionRow, session_id)
    if session_row is None:
        raise api_error("NOT_FOUND", f"Session {session_id} not found", 404)

    rows = (
        session.query(QueryRow)
        .filter(QueryRow.session_id == session_id)
        .order_by(QueryRow.turn_index.asc())
        .all()
    )
    items = [
        QueryHistoryItem(
            query_id=r.id,
            turn_index=r.turn_index,
            question=r.question,
            status=r.status,
            answer_text=r.answer_text,
        ).model_dump()
        for r in rows
    ]
    return ok(items)
