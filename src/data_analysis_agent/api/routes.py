import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

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
    SessionDataSourceRow,
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
    all_sessions = session.query(SessionRow).order_by(SessionRow.updated_at.desc()).all()

    # Build data_sources list per session and query counts
    session_sources: dict[str, list[DataSourceRow]] = {}
    session_query_counts: dict[str, int] = {}
    for sess in all_sessions:
        links = (
            session.query(SessionDataSourceRow)
            .filter(SessionDataSourceRow.session_id == sess.id)
            .all()
        )
        ds_list = [session.get(DataSourceRow, lnk.data_source_id) for lnk in links]
        session_sources[sess.id] = [ds for ds in ds_list if ds]
        session_query_counts[sess.id] = (
            session.query(QueryRecordRow)
            .filter(QueryRecordRow.session_id == sess.id)
            .count()
        )

    return render(
        request, templates, "home.html",
        sources=sources,
        all_sessions=all_sessions,
        session_sources=session_sources,
        session_query_counts=session_query_counts,
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

    ds = DataSourceRow(name=file.filename, type="csv", file_path="")
    session.add(ds)
    session.flush()

    dest = upload_dir / f"{ds.id}.csv"
    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    try:
        df = pd.read_csv(str(dest))
        ds.file_path = str(dest)
        ds.row_count = len(df)
        ds.column_names = list(df.columns)
    except Exception as exc:
        dest.unlink(missing_ok=True)
        session.rollback()
        raise api_error("PARSE_FAILED", f"Could not parse CSV: {exc}")

    # Derive SQL-safe table name from filename
    import re
    table_name = re.sub(r'[^\w]', '_', file.filename.rsplit('.', 1)[0]).lower()
    table_name = re.sub(r'_+', '_', table_name).strip('_') or 'data'
    if table_name[0].isdigit():
        table_name = 'ds_' + table_name

    tool = ToolRow(
        data_source_id=ds.id,
        name="csv_query",
        type="csv_query",
        description=f"Execute SQL SELECT queries against '{ds.name}' (table: {table_name}).",
        config_json=json.dumps({"table_name": table_name}),
    )
    session.add(tool)
    session.flush()

    cap = ToolCapabilityRow(
        tool_id=tool.id,
        name="run_query",
        description=f"Execute a SQL SELECT statement against '{ds.name}'. Table name is '{table_name}'.",
        parameter_schema_json=json.dumps({
            "query": {
                "type": "string",
                "description": f"A valid SQL SELECT statement. Table name is '{table_name}'.",
            }
        }),
    )
    session.add(cap)
    log.info("upload.success", data_source_id=ds.id, filename=file.filename, table=table_name)
    return RedirectResponse(url="/", status_code=303)


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

    # Remove from join table
    session.query(SessionDataSourceRow).filter(
        SessionDataSourceRow.data_source_id == datasource_id
    ).delete()

    # Delete tools and capabilities
    tools = session.query(ToolRow).filter(ToolRow.data_source_id == datasource_id).all()
    for t in tools:
        session.query(ToolCapabilityRow).filter(ToolCapabilityRow.tool_id == t.id).delete()
        session.delete(t)

    if ds.file_path:
        Path(ds.file_path).unlink(missing_ok=True)

    session.delete(ds)
    log.info("datasource.deleted", datasource_id=datasource_id)
    return RedirectResponse(url="/", status_code=303)


# ─── Session: Create ──────────────────────────────────────────────────────────

@router.post("/sessions")
def create_session(
    request: Request,
    name: Annotated[str, Form()] = "",
    data_source_ids: Annotated[list[str], Form()] = [],
    session: Session = Depends(get_session),
):
    if not data_source_ids:
        raise api_error("NO_DATA_SOURCES", "Select at least one data source.")

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    sess = SessionRow(name=name.strip() or f"Session {now_str}")
    session.add(sess)
    session.flush()

    for ds_id in data_source_ids:
        ds = session.get(DataSourceRow, ds_id)
        if not ds:
            session.rollback()
            raise api_error("NOT_FOUND", f"Data source {ds_id} not found.", status_code=404)
        session.add(SessionDataSourceRow(session_id=sess.id, data_source_id=ds_id))

    log.info("session.created", session_id=sess.id, ds_count=len(data_source_ids))
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

    links = (
        session.query(SessionDataSourceRow)
        .filter(SessionDataSourceRow.session_id == session_id)
        .all()
    )
    data_sources = [session.get(DataSourceRow, lnk.data_source_id) for lnk in links]
    data_sources = [ds for ds in data_sources if ds]

    records = (
        session.query(QueryRecordRow)
        .filter(QueryRecordRow.session_id == session_id)
        .order_by(QueryRecordRow.created_at.desc())
        .all()
    )
    return render(
        request, templates, "session.html",
        sess=sess,
        data_sources=data_sources,
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

    qrs = session.query(QueryRecordRow).filter(QueryRecordRow.session_id == session_id).all()
    for qr in qrs:
        session.query(AgentRunRow).filter(AgentRunRow.query_record_id == qr.id).delete()
        session.delete(qr)

    session.query(SessionDataSourceRow).filter(
        SessionDataSourceRow.session_id == session_id
    ).delete()
    session.delete(sess)
    log.info("session.deleted", session_id=session_id)
    return RedirectResponse(url="/", status_code=303)


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

    qr = QueryRecordRow(session_id=session_id, question=question.strip())
    session.add(qr)
    session.flush()
    query_record_id = qr.id
    sess.updated_at = datetime.now(timezone.utc)
    session.commit()

    try:
        from data_analysis_agent.graph.runner import run_pipeline
        final_state = run_pipeline(
            query_record_id=query_record_id,
            session_id=session_id,
            question=question.strip(),
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
