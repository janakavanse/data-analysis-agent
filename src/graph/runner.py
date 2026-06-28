"""Run the analysis graph end-to-end and persist the result to the runs table."""

from __future__ import annotations

import time
from datetime import datetime, timezone

from db.models import RunRow
from db.session import create_db_session, init_db
from graph.agent import agentic_ai
from graph.state import AgentState
from observability.events import get_logger

_log = get_logger("agent.runner")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def run_agent(question: str, dataset_id: str, session_id: str | None = None) -> str:
    """Create a runs row, invoke the graph, persist the full result. Returns run_id."""
    init_db()

    with create_db_session() as session:
        run = RunRow(
            dataset_id=dataset_id,
            session_id=session_id,
            question=question,
            status="running",
            stage="planning",
            llm_payload_json={},
            started_at=_now(),
        )
        session.add(run)
        session.flush()
        run_id = run.id

    initial: AgentState = {
        "run_id": run_id,
        "dataset_id": dataset_id,
        "session_id": session_id,
        "question": question,
        "messages": [],
        "revisions": 0,
        "error": None,
    }

    started = time.monotonic()
    final = agentic_ai.invoke(initial)
    latency_ms = int((time.monotonic() - started) * 1000)

    error = final.get("error")
    status = "failed" if error else "completed"

    _log.info(
        "run_complete",
        run_id=run_id,
        dataset_id=dataset_id,
        status=status,
        stage=final.get("stage"),
        revisions=final.get("revisions", 0),
        flagged=final.get("flagged", False),
        tokens_in=final.get("tokens_in", 0),
        tokens_out=final.get("tokens_out", 0),
        cost_estimate=final.get("cost_estimate", 0.0),
        latency_ms=latency_ms,
        error=error,
    )

    with create_db_session() as session:
        run = session.get(RunRow, run_id)
        run.code = final.get("code")
        run.result_json = final.get("summary_table")
        run.key_numbers_json = final.get("key_numbers")
        run.chart_spec_json = final.get("chart_spec")
        run.answer = final.get("answer")
        run.llm_payload_json = final.get("llm_payload") or {}
        run.tokens_in = final.get("tokens_in", 0)
        run.tokens_out = final.get("tokens_out", 0)
        run.cost_estimate = final.get("cost_estimate", 0.0)
        run.stage = final.get("stage", "done")
        run.status = status
        run.flagged = bool(final.get("flagged", False))
        run.error_message = error
        run.revisions = final.get("revisions", 0)
        run.completed_at = _now()

    return run_id
