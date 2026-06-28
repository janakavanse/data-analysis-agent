"""Dataset endpoints: upload + ingest, and fetch metadata.

Contract: ``spec/api.md`` (POST /datasets, GET /datasets/{dataset_id}). The upload
is streamed to disk, ingested into DuckDB + parquet via the analysis engine, and a
``DatasetRow`` is persisted to SQLite app state. Only schema + a small sample + row
count cross back to the caller — the privacy boundary lives in the analysis engine,
not here.
"""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, UploadFile, File
from sqlalchemy.orm import Session

from api._common import ok, api_error
from db.session import get_session
from db.models import DatasetRow
from domain.dataset import dataset_payload

router = APIRouter()

# ~100MB upload cap (spec: "> ~100MB" -> 413 TOO_LARGE).
MAX_UPLOAD_BYTES = 100 * 1024 * 1024

# Accepted file extensions (CSV + Excel per the stack).
_ALLOWED_EXTS = {"csv", "tsv", "txt", "xlsx", "xls"}


def _uploads_dir() -> Path:
    """Resolve the uploads directory, preferring the analysis engine's storage."""
    try:
        from analysis.storage import uploads_dir

        return uploads_dir()
    except Exception:
        d = Path("data") / "uploads"
        d.mkdir(parents=True, exist_ok=True)
        return d


def _extension(filename: str | None) -> str:
    if not filename:
        return ""
    return Path(filename).suffix.lstrip(".").lower()


@router.post("/datasets")
def create_dataset(
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
) -> dict:
    original_name = file.filename or "upload"
    ext = _extension(original_name)
    if ext and ext not in _ALLOWED_EXTS:
        raise api_error(
            "BAD_FILE",
            f"Unsupported file type '.{ext}'. Upload a CSV or Excel (.xlsx) file.",
            400,
        )

    dataset_id = str(uuid.uuid4())
    dest = _uploads_dir() / f"{dataset_id}.{ext or 'csv'}"

    # Stream to disk while enforcing the size cap (no full read into memory).
    bytes_written = 0
    try:
        with dest.open("wb") as out:
            while True:
                chunk = file.file.read(1024 * 1024)
                if not chunk:
                    break
                bytes_written += len(chunk)
                if bytes_written > MAX_UPLOAD_BYTES:
                    out.close()
                    dest.unlink(missing_ok=True)
                    raise api_error(
                        "TOO_LARGE",
                        f"File exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)}MB limit.",
                        413,
                    )
                out.write(chunk)
    except Exception as exc:  # propagate our own HTTPExceptions unchanged
        from fastapi import HTTPException

        if isinstance(exc, HTTPException):
            raise
        dest.unlink(missing_ok=True)
        raise api_error("INGEST_ERROR", f"Could not store upload: {exc}", 500)

    if bytes_written == 0:
        dest.unlink(missing_ok=True)
        raise api_error("BAD_FILE", "Uploaded file is empty.", 400)

    # Ingest into DuckDB + parquet. BadFileError -> 400; anything else -> 500.
    from analysis.engine import ingest_file, BadFileError

    try:
        ingested = ingest_file(str(dest), original_name, dataset_id)
    except BadFileError as exc:
        dest.unlink(missing_ok=True)
        raise api_error("BAD_FILE", f"Could not parse the file: {exc}", 400)
    except Exception as exc:
        raise api_error("INGEST_ERROR", f"Failed to ingest the dataset: {exc}", 500)

    schema = ingested["schema"]
    sample = ingested["sample"]
    row_count = int(ingested["row_count"])
    duckdb_table = ingested.get("duckdb_table", f"ds_{dataset_id}")
    parquet_path = ingested.get("parquet_path", "")

    row = DatasetRow(
        id=dataset_id,
        name=original_name,
        storage_path=str(dest),
        parquet_path=parquet_path,
        duckdb_table=duckdb_table,
        schema_json=schema,
        sample_json=sample,
        row_count=row_count,
    )
    session.add(row)
    session.flush()

    return ok(
        dataset_payload(
            dataset_id=dataset_id,
            name=original_name,
            schema=schema,
            sample=sample,
            row_count=row_count,
        )
    )


@router.get("/datasets/{dataset_id}")
def get_dataset(
    dataset_id: str,
    session: Session = Depends(get_session),
) -> dict:
    row = session.get(DatasetRow, dataset_id)
    if row is None:
        raise api_error("DATASET_NOT_FOUND", f"Dataset {dataset_id} not found.", 404)
    return ok(
        dataset_payload(
            dataset_id=row.id,
            name=row.name,
            schema=row.schema_json,
            sample=row.sample_json,
            row_count=row.row_count,
        )
    )
