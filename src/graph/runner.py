import json
from datetime import datetime, timezone

from config.settings import get_settings
from db.models import DatasetRow, QueryRow
from db.session import create_db_session
from graph.agent import agentic_ai
from graph.state import AgentState
from observability.events import get_logger

logger = get_logger("graph.runner")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _load_history(session, session_id: str, exclude_query_id: str, limit: int) -> list[dict]:
    if limit <= 0:
        return []
    rows = (
        session.query(QueryRow)
        .filter(QueryRow.session_id == session_id)
        .filter(QueryRow.answer_text.is_not(None))
        .filter(QueryRow.id != exclude_query_id)
        .order_by(QueryRow.turn_index.asc())
        .all()
    )
    recent = rows[-limit:]
    return [{"question": r.question, "answer": r.answer_text} for r in recent]


def run_query(query_id: str) -> None:
    """Loads the Query + Dataset rows, builds the initial AgentState, and
    invokes the graph. Terminal status writes happen inside the
    finalize/handle_error nodes; this function only guards against an
    exception escaping the graph entirely."""
    try:
        with create_db_session() as db:
            query_row = db.get(QueryRow, query_id)
            if query_row is None:
                logger.error("run_query.query_not_found", query_id=query_id)
                return

            dataset_row = db.get(DatasetRow, query_row.dataset_id)
            if dataset_row is None:
                query_row.status = "failed"
                query_row.error_message = "Dataset not found"
                query_row.completed_at = _now()
                return

            history = _load_history(
                db, query_row.session_id, query_id, get_settings().conversation_history_turns
            )

            initial: AgentState = {
                "query_id": query_id,
                "session_id": query_row.session_id,
                "dataset_id": query_row.dataset_id,
                "dataset_path": dataset_row.storage_path,
                "file_type": dataset_row.file_type,
                "dataset_schema": json.loads(dataset_row.schema_json),
                "question": query_row.question,
                "conversation_history": history,
                "generated_code": None,
                "retry_count": 0,
                "last_error": None,
                "status_decision": None,
                "followups": None,
                "clarification_message": None,
                "answer_text": None,
                "result_table": None,
                "token_usage": None,
                "chart_spec_json": None,
                "error": None,
                "status": None,
            }

        agentic_ai.invoke(initial)
    except Exception as exc:  # noqa: BLE001 - last-resort guard, query must never hang
        logger.error("run_query.unhandled_exception", query_id=query_id, error=str(exc))
        try:
            with create_db_session() as db:
                row = db.get(QueryRow, query_id)
                if row is not None and row.status not in ("completed", "failed"):
                    row.status = "failed"
                    row.error_message = str(exc)
                    row.completed_at = _now()
        except Exception:  # noqa: BLE001 - nothing more we can do
            logger.error("run_query.guard_write_failed", query_id=query_id)
