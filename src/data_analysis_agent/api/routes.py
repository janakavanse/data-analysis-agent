import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import structlog
from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from data_analysis_agent.api import templates
from data_analysis_agent.api._common import api_error, render
from data_analysis_agent.config.settings import get_settings
from data_analysis_agent.db.models import (
    AgentRunRow,
    DataSourceRow,
    QueryRecordRow,
    SessionRow,
    ToolCapabilityRow,
    ToolRow,
)
from data_analysis_agent.db.session import get_session

log = structlog.get_logger()
router = APIRouter()


# ─── Home ────────────────────────────────────────────────────────────────────

@router.get("/")
def home(request: Request, session: Session = Depends(get_session)):
    sources = session.query(DataSourceRow).order_by(DataSourceRow.created_at.desc()).all()
    session_counts: dict[str, int] = {}
    last_activity: dict[str, datetime | None] = {}
    for src in sources:
        rows = (
            session.query(SessionRow)
            .filter(SessionRow.data_source_id == src.id)
            .all()
        )
        session_counts[src.id] = len(rows)
        dates = [r.updated_at for r in rows if r.updated_at]
        last_activity[src.id] = max(dates) if dates else None
    return render(
        request, templates, "home.html",
        sources=sources,
        session_counts=session_counts,
        last_activity=last_activity,
    )


# ─── Data Source: Upload ─────────────────────────────────────────────────────

@router.post("/datasources/upload")
def upload_csv(
    request: Request,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise api_error("INVALID_FILE", "Only CSV files are supported.")

    settings = get_settings()
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    # Create DataSource row first to get the id for filename
    ds = DataSourceRow(name=file.filename, type="csv", file_path="")
    session.add(ds)
    session.flush()

    dest = upload_dir / f"{ds.id}.csv"
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    # Parse schema
    try:
        df = pd.read_csv(str(dest))
        ds.file_path = str(dest)
        ds.row_count = len(df)
        ds.column_names = list(df.columns)
    except Exception as exc:
        dest.unlink(missing_ok=True)
        session.rollback()
        raise api_error("PARSE_FAILED", f"Could not parse CSV: {exc}")

    # Create Tool + ToolCapability
    tool = ToolRow(
        data_source_id=ds.id,
        name="csv_query",
        type="csv_query",
        description="Execute SQL SELECT queries against the uploaded CSV dataset.",
        config_json=json.dumps({"table_name": "data"}),
    )
    session.add(tool)
    session.flush()

    cap = ToolCapabilityRow(
        tool_id=tool.id,
        name="run_query",
        description="Execute a SQL SELECT statement. The table is always named 'data'.",
        parameter_schema_json=json.dumps({
            "query": {
                "type": "string",
                "description": "A valid SQL SELECT statement. Table name is always 'data'.",
            }
        }),
    )
    session.add(cap)
    session.flush()

    log.info("upload.success", data_source_id=ds.id, filename=file.filename,
             rows=ds.row_count, tool_id=tool.id)
    return RedirectResponse(url=f"/datasources/{ds.id}", status_code=303)


# ─── Data Source: Detail (Sessions List) ─────────────────────────────────────

@router.get("/datasources/{datasource_id}")
def datasource_detail(
    request: Request,
    datasource_id: str,
    session: Session = Depends(get_session),
):
    ds = session.get(DataSourceRow, datasource_id)
    if not ds:
        raise api_error("NOT_FOUND", "Data source not found.", status_code=404)

    tool = session.query(ToolRow).filter(ToolRow.data_source_id == datasource_id).first()
    capabilities: list[ToolCapabilityRow] = []
    if tool:
        capabilities = (
            session.query(ToolCapabilityRow)
            .filter(ToolCapabilityRow.tool_id == tool.id)
            .all()
        )

    sessions = (
        session.query(SessionRow)
        .filter(SessionRow.data_source_id == datasource_id)
        .order_by(SessionRow.updated_at.desc())
        .all()
    )
    query_counts: dict[str, int] = {}
    for s in sessions:
        query_counts[s.id] = (
            session.query(QueryRecordRow)
            .filter(QueryRecordRow.session_id == s.id)
            .count()
        )

    return render(
        request, templates, "datasource.html",
        ds=ds,
        tool=tool,
        capabilities=capabilities,
        sessions=sessions,
        query_counts=query_counts,
    )


# ─── Data Source: Delete ──────────────────────────────────────────────────────

@router.post("/datasources/{datasource_id}/delete")
def delete_datasource(
    request: Request,
    datasource_id: str,
    session: Session = Depends(get_session),
):
    ds = session.get(DataSourceRow, datasource_id)
    if not ds:
        raise api_error("NOT_FOUND", "Data source not found.", status_code=404)

    # Delete all agent runs for all query records in all sessions of this datasource
    all_sessions = session.query(SessionRow).filter(SessionRow.data_source_id == datasource_id).all()
    for s in all_sessions:
        qrs = session.query(QueryRecordRow).filter(QueryRecordRow.session_id == s.id).all()
        for qr in qrs:
            session.query(AgentRunRow).filter(AgentRunRow.query_record_id == qr.id).delete()
            session.delete(qr)
        session.delete(s)

    # Delete tools and capabilities
    tools = session.query(ToolRow).filter(ToolRow.data_source_id == datasource_id).all()
    for t in tools:
        session.query(ToolCapabilityRow).filter(ToolCapabilityRow.tool_id == t.id).delete()
        session.delete(t)

    # Delete CSV file
    if ds.file_path:
        Path(ds.file_path).unlink(missing_ok=True)

    session.delete(ds)
    log.info("datasource.deleted", datasource_id=datasource_id)
    return RedirectResponse(url="/", status_code=303)


# ─── Session: Create ──────────────────────────────────────────────────────────

@router.post("/datasources/{datasource_id}/sessions")
def create_session(
    request: Request,
    datasource_id: str,
    name: str = Form(default=""),
    session: Session = Depends(get_session),
):
    ds = session.get(DataSourceRow, datasource_id)
    if not ds:
        raise api_error("NOT_FOUND", "Data source not found.", status_code=404)

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    sess = SessionRow(
        data_source_id=datasource_id,
        name=name.strip() or f"Session {now_str}",
    )
    session.add(sess)
    session.flush()
    log.info("session.created", session_id=sess.id, data_source_id=datasource_id)
    return RedirectResponse(url=f"/sessions/{sess.id}", status_code=303)


# ─── Session: View (Chat) ─────────────────────────────────────────────────────

@router.get("/sessions/{session_id}")
def session_detail(
    request: Request,
    session_id: str,
    new: str | None = None,
    session: Session = Depends(get_session),
):
    sess = session.get(SessionRow, session_id)
    if not sess:
        raise api_error("NOT_FOUND", "Session not found.", status_code=404)

    ds = session.get(DataSourceRow, sess.data_source_id)
    records = (
        session.query(QueryRecordRow)
        .filter(QueryRecordRow.session_id == session_id)
        .order_by(QueryRecordRow.created_at.desc())
        .all()
    )
    return render(
        request, templates, "session.html",
        sess=sess,
        ds=ds,
        records=records,
        new_record_id=new,
    )


# ─── Session: Delete ─────────────────────────────────────────────────────────

@router.post("/sessions/{session_id}/delete")
def delete_session(
    request: Request,
    session_id: str,
    session: Session = Depends(get_session),
):
    sess = session.get(SessionRow, session_id)
    if not sess:
        raise api_error("NOT_FOUND", "Session not found.", status_code=404)
    datasource_id = sess.data_source_id

    qrs = session.query(QueryRecordRow).filter(QueryRecordRow.session_id == session_id).all()
    for qr in qrs:
        session.query(AgentRunRow).filter(AgentRunRow.query_record_id == qr.id).delete()
        session.delete(qr)
    session.delete(sess)
    log.info("session.deleted", session_id=session_id)
    return RedirectResponse(url=f"/datasources/{datasource_id}", status_code=303)


# ─── Session: Submit Query ────────────────────────────────────────────────────

@router.post("/sessions/{session_id}/query")
def submit_query(
    request: Request,
    session_id: str,
    question: str = Form(...),
    session: Session = Depends(get_session),
):
    if not question.strip():
        raise api_error("EMPTY_QUESTION", "Question cannot be empty.")

    sess = session.get(SessionRow, session_id)
    if not sess:
        raise api_error("NOT_FOUND", "Session not found.", status_code=404)

    ds = session.get(DataSourceRow, sess.data_source_id)
    if not ds:
        raise api_error("NOT_FOUND", "Data source not found.", status_code=404)

    qr = QueryRecordRow(session_id=session_id, question=question.strip())
    session.add(qr)
    session.flush()
    query_record_id = qr.id

    # Touch session updated_at
    sess.updated_at = datetime.now(timezone.utc)
    session.commit()

    try:
        from data_analysis_agent.graph.runner import run_pipeline
        final_state = run_pipeline(
            query_record_id=query_record_id,
            session_id=session_id,
            data_source_id=sess.data_source_id,
            question=question.strip(),
            csv_path=ds.file_path or "",
        )

        if final_state.get("error"):
            log.error("query.pipeline_error", error=final_state["error"])
            return render(request, templates, "error.html", detail=final_state["error"])

        return RedirectResponse(
            url=f"/sessions/{session_id}?new={query_record_id}",
            status_code=303,
        )
    except Exception as exc:
        log.error("query.unexpected_error", error=str(exc))
        return render(request, templates, "error.html", detail=str(exc))
