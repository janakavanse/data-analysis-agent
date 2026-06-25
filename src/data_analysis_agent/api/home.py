from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from data_analysis_agent.api import templates
from data_analysis_agent.api._common import render
from data_analysis_agent.api._repository import attached_sources, query_count
from data_analysis_agent.config.settings import get_settings
from data_analysis_agent.db.models import DataSourceRow, DatasetTableRow, SessionRow
from data_analysis_agent.db.session import get_session
from data_analysis_agent.tools.connectors.uri import DatasetURI

router = APIRouter()


@router.get("/")
def home(request: Request, session: Session = Depends(get_session)):
    """Render the home page listing all datasets and sessions."""
    rows = session.query(DataSourceRow).order_by(DataSourceRow.created_at.desc()).all()
    datasets = [_dataset_view(session, ds) for ds in rows]
    sessions = session.query(SessionRow).order_by(SessionRow.updated_at.desc()).all()
    session_sources, session_query_counts = _session_overview(session, sessions)
    return render(
        request, templates, "home.html",
        datasets=datasets,
        all_sessions=sessions,
        session_sources=session_sources,
        session_query_counts=session_query_counts,
        enable_external=get_settings().enable_external_datasets,
    )


def _dataset_view(db: Session, ds: DataSourceRow) -> dict:
    """Build a credential-free per-dataset view-model for the home page.

    Aggregates the dataset's tables (table count, total rows, a column sample). Falls back to the
    deprecated single-source columns for a legacy dataset with no child rows.
    """
    tables = (
        db.query(DatasetTableRow)
        .filter(DatasetTableRow.dataset_id == ds.id)
        .order_by(DatasetTableRow.created_at)
        .all()
    )
    if tables:
        columns = tables[0].column_names
        total_rows = sum(t.row_count or 0 for t in tables)
        table_count = len(tables)
    else:  # legacy single-CSV dataset (no child rows yet)
        columns = ds.column_names
        total_rows = ds.row_count or 0
        table_count = 1 if ds.parquet_path else 0
    return {
        "id": ds.id,
        "name": ds.name,
        "type": ds.type,
        "is_parquet": (ds.type or "").lower() in ("parquet", "csv"),
        "uri_display": DatasetURI(ds.dataset_uri).display(),
        "table_count": table_count,
        "total_rows": total_rows,
        "columns": columns,
        "last_synced_at": ds.last_synced_at,
        "connection_error": ds.connection_error,
    }


def _session_overview(
    db: Session, sessions: list[SessionRow]
) -> tuple[dict[str, list[DataSourceRow]], dict[str, int]]:
    """Build per-session attached-dataset lists and question counts for the home view."""
    sources_by_session = {s.id: attached_sources(db, s.id) for s in sessions}
    count_by_session = {s.id: query_count(db, s.id) for s in sessions}
    return sources_by_session, count_by_session
