"""``POST /datasets`` — upload a CSV, load it locally, open a session.

Privacy invariant: the raw file is saved to disk and loaded into the
in-process DataFrame store; only schema + an N-row sample + the row count are
persisted to the DB and returned to the client. The full rows never leave the
machine.
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from analysis.store import (
    extract_sample,
    extract_schema,
    load_dataframe,
    register,
    row_count,
)
from api._common import api_error, ok
from db.models import Dataset, Session as SessionRow
from db.session import get_session
from domain.dataset import DatasetUploadData

router = APIRouter()

_SAMPLE_ROWS = 5
# repo root = src/api/datasets.py -> three parents up
_UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "uploads"


@router.post("/datasets")
def upload_dataset(
    file: UploadFile = File(...),
    db: Session = Depends(get_session),
) -> dict:
    filename = file.filename or ""
    if not filename.lower().endswith(".csv"):
        raise api_error(
            "BAD_REQUEST",
            "Only CSV files are supported in Phase 1. Please upload a .csv file.",
        )

    _UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    saved_path = _UPLOAD_DIR / f"{uuid4()}.csv"

    try:
        contents = file.file.read()
        saved_path.write_bytes(contents)
    except Exception as exc:  # noqa: BLE001
        raise api_error("INTERNAL", f"Failed to save the upload: {exc}", 500)

    try:
        df = load_dataframe(str(saved_path), file_type="csv")
    except Exception as exc:  # noqa: BLE001 — pandas couldn't parse the file
        saved_path.unlink(missing_ok=True)
        raise api_error(
            "BAD_REQUEST",
            f"The file could not be read as CSV: {exc}",
        )

    if df.shape[1] == 0:
        saved_path.unlink(missing_ok=True)
        raise api_error("BAD_REQUEST", "The uploaded CSV has no columns.")

    schema = extract_schema(df)
    sample_rows = extract_sample(df, n=_SAMPLE_ROWS)
    rows = row_count(df)

    session_row = SessionRow(id=str(uuid4()))
    db.add(session_row)
    db.flush()  # assign + materialize session id
    session_id = session_row.id

    db.add(
        Dataset(
            id=str(uuid4()),
            session_id=session_id,
            filename=filename,
            file_path=str(saved_path),
            file_type="csv",
            row_count=rows,
            schema_json=json.dumps(schema, ensure_ascii=False),
            sample_json=json.dumps(sample_rows, ensure_ascii=False),
        )
    )

    # Make the DataFrame immediately available for the first question.
    register(session_id, df)

    payload = DatasetUploadData(
        session_id=session_id,
        filename=filename,
        row_count=rows,
        schema_data=schema,
        sample_rows=sample_rows,
    )
    return ok(payload.model_dump(by_alias=True))
