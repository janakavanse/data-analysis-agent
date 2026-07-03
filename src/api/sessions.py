from datetime import datetime, timezone
from uuid import uuid4

import pandas as pd
from fastapi import APIRouter, Depends, UploadFile
from sqlalchemy.orm import Session

from analysis.profiling import profile_dataframe
from analysis.storage import load_dataframe, save_upload
from api._common import ok, api_error
from db.models import DatasetRow, SessionRow
from db.session import get_session
from domain.dataset import DatasetResponse
from domain.session import SessionResponse
from observability.events import get_logger

router = APIRouter()
logger = get_logger("api.sessions")

_SUPPORTED_EXTENSIONS = {"csv", "xlsx"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _dataset_response(row: DatasetRow) -> dict:
    import json

    from domain.dataset import ColumnSchema

    schema_data = json.loads(row.schema_json)
    columns = [ColumnSchema(**c) for c in schema_data.get("columns", [])]
    return DatasetResponse(
        dataset_id=row.id,
        original_filename=row.original_filename,
        file_type=row.file_type,
        row_count=row.row_count,
        column_count=row.column_count,
        schema=columns,
    ).model_dump()


@router.post("/sessions")
def create_session(session: Session = Depends(get_session)) -> dict:
    row = SessionRow()
    session.add(row)
    session.flush()
    return ok(SessionResponse(session_id=row.id, created_at=row.created_at.isoformat()).model_dump())


@router.post("/sessions/{session_id}/datasets")
def upload_dataset(
    session_id: str,
    file: UploadFile,
    session: Session = Depends(get_session),
) -> dict:
    session_row = session.get(SessionRow, session_id)
    if session_row is None:
        raise api_error("NOT_FOUND", f"Session {session_id} not found", 404)

    filename = file.filename or ""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if not filename or ext not in _SUPPORTED_EXTENSIONS:
        raise api_error(
            "INVALID_FILE",
            "Missing file or unsupported file type — only .csv/.xlsx are supported.",
            400,
        )

    content = file.file.read()
    if not content:
        raise api_error("INVALID_FILE", "Uploaded file is empty.", 400)

    dataset_id = str(uuid4())

    try:
        storage_path = save_upload(session_id, dataset_id, filename, content)
    except OSError as exc:
        raise api_error("STORAGE_ERROR", f"Failed to save uploaded file: {exc}", 500) from exc

    try:
        df = load_dataframe(str(storage_path), ext)
        schema = profile_dataframe(df)
    except (ValueError, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise api_error("INVALID_FILE", f"Could not parse file: {exc}", 400) from exc
    except Exception as exc:  # noqa: BLE001
        logger.error("dataset.profiling_failed", session_id=session_id, error=str(exc))
        raise api_error("PROFILING_ERROR", f"Unexpected error profiling file: {exc}", 500) from exc

    row = DatasetRow(
        id=dataset_id,
        session_id=session_id,
        original_filename=filename,
        storage_path=str(storage_path),
        file_type=ext,
        row_count=schema.row_count,
        column_count=len(schema.columns),
        schema_json=schema.model_dump_json(),
    )
    session.add(row)
    session_row.last_active_at = _now()
    session.flush()

    return ok(_dataset_response(row))


@router.get("/sessions/{session_id}/datasets/{dataset_id}")
def get_dataset(session_id: str, dataset_id: str, session: Session = Depends(get_session)) -> dict:
    session_row = session.get(SessionRow, session_id)
    if session_row is None:
        raise api_error("NOT_FOUND", f"Session {session_id} not found", 404)

    row = session.get(DatasetRow, dataset_id)
    if row is None or row.session_id != session_id:
        raise api_error("NOT_FOUND", f"Dataset {dataset_id} not found", 404)

    return ok(_dataset_response(row))
