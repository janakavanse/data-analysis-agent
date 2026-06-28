"""Dataset upload + profile endpoints (spec/api.md, Phase 1).

POST /datasets               — multipart CSV upload → store, profile, persist.
GET  /datasets/{id}/profile  — fetch the stored privacy-safe profile.

Privacy boundary: only the aggregate column profile is returned to the client;
raw rows never appear in any response here (and never reach the LLM).
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from api._common import ok, api_error
from data.ingest import (
    DatasetError,
    DatasetParseError,
    DatasetTooLargeError,
    check_size,
    load_csv,
    row_count,
)
from data.profile import build_profile
from data.storage import save_upload
from db.models import Dataset, DatasetProfile
from db.session import get_session
from observability.events import get_logger

router = APIRouter()
logger = get_logger("api.datasets")


def _schema_map(profile: dict) -> dict[str, str]:
    """Compact {column-name: dtype} map for the LLM-bound schema payload."""
    return {col["name"]: col["dtype"] for col in profile.get("columns", [])}


@router.post("/datasets")
async def create_dataset(
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
) -> dict:
    filename = file.filename or "upload.csv"
    file_bytes = await file.read()

    # ---- size cap → 413 --------------------------------------------------- #
    try:
        check_size(len(file_bytes))
    except DatasetTooLargeError as exc:
        raise api_error("TOO_LARGE", str(exc), 413) from exc

    # ---- store + load + profile ------------------------------------------ #
    dataset_id, storage_path = save_upload(file_bytes, filename)
    try:
        df = load_csv(storage_path)
    except DatasetParseError as exc:
        raise api_error("PARSE_ERROR", str(exc), 400) from exc
    except DatasetError as exc:  # any other ingest failure
        raise api_error("INGEST_ERROR", str(exc), 400) from exc

    profile = build_profile(df)
    rows = row_count(df)

    # ---- persist Dataset + DatasetProfile -------------------------------- #
    try:
        ds = Dataset(
            id=dataset_id,
            name=filename,
            kind="csv",
            storage_path=storage_path,
            size_bytes=len(file_bytes),
            row_count=rows,
        )
        session.add(ds)
        session.add(
            DatasetProfile(
                dataset_id=dataset_id,
                schema_json=json.dumps(_schema_map(profile)),
                profile_json=json.dumps(profile),
            )
        )
        session.flush()
    except Exception as exc:  # noqa: BLE001
        logger.error("dataset.persist_failed", dataset_id=dataset_id, error=str(exc))
        raise api_error("INTERNAL", f"failed to persist dataset: {exc}", 500) from exc

    logger.info(
        "dataset.uploaded",
        dataset_id=dataset_id,
        name=filename,
        row_count=rows,
        size_bytes=len(file_bytes),
        columns=len(profile.get("columns", [])),
    )
    return ok(
        {
            "dataset_id": dataset_id,
            "name": filename,
            "row_count": rows,
            "profile": profile,
        }
    )


@router.get("/datasets/{dataset_id}/profile")
def get_dataset_profile(
    dataset_id: str,
    session: Session = Depends(get_session),
) -> dict:
    ds = session.get(Dataset, dataset_id)
    if ds is None:
        raise api_error("NOT_FOUND", f"unknown dataset: {dataset_id}", 404)

    prof = (
        session.query(DatasetProfile)
        .filter(DatasetProfile.dataset_id == dataset_id)
        .order_by(DatasetProfile.created_at.asc())
        .first()
    )
    if prof is None:
        raise api_error("NOT_FOUND", f"no profile for dataset: {dataset_id}", 404)

    profile = json.loads(prof.profile_json)
    return ok(
        {
            "dataset_id": dataset_id,
            "name": ds.name,
            "row_count": ds.row_count,
            "profile": profile,
        }
    )
