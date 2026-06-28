"""Analysis endpoints: ask a question (synchronous run) and fetch a run.

Contract: ``spec/api.md`` (POST /analyses, GET /analyses/{run_id}). ``POST /analyses``
is synchronous in Phase 1 — it invokes the LangGraph code-execution loop via
``graph.runner.run_agent`` and returns when the run completes. A run the graph
marks ``failed`` surfaces as 422 ANALYSIS_FAILED (with the attempted code/message),
never as a silent 200.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api._common import ok, api_error
from db.session import get_session
from db.models import DatasetRow, RunRow
from domain.analysis import AnalysisRequest, run_payload

router = APIRouter()


@router.post("/analyses")
def create_analysis(
    req: AnalysisRequest,
    session: Session = Depends(get_session),
) -> dict:
    question = (req.question or "").strip()
    if not question:
        raise api_error("EMPTY_QUESTION", "Question must not be empty.", 400)

    dataset = session.get(DatasetRow, req.dataset_id)
    if dataset is None:
        raise api_error(
            "DATASET_NOT_FOUND", f"Dataset {req.dataset_id} not found.", 404
        )

    from graph.runner import run_agent

    try:
        run_id = run_agent(question, req.dataset_id)
    except Exception as exc:
        raise api_error("INTERNAL", f"Analysis failed to start: {exc}", 500)

    # The runner persists via its own session; read the freshly-committed row.
    session.expire_all()
    run = session.get(RunRow, run_id)
    if run is None:
        raise api_error("INTERNAL", "Run vanished after creation.", 500)

    if run.status == "failed":
        detail = run.error_message or "The analysis could not be completed."
        if run.code:
            detail = f"{detail}\n\nAttempted code:\n{run.code}"
        raise api_error("ANALYSIS_FAILED", detail, 422)

    return ok(run_payload(run))


@router.get("/analyses/{run_id}")
def get_analysis(
    run_id: str,
    session: Session = Depends(get_session),
) -> dict:
    run = session.get(RunRow, run_id)
    if run is None:
        raise api_error("RUN_NOT_FOUND", f"Run {run_id} not found.", 404)
    return ok(run_payload(run, include_run_detail=True))
