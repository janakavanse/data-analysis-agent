from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from analysis.export import (
    DatasetUnavailableError,
    NoDataframeResultError,
    export_query_result,
)
from api._common import api_error
from db.models import DatasetRow, QueryRow
from db.session import get_session

router = APIRouter()


class ExportRequest(BaseModel):
    format: str = "csv"


@router.post("/queries/{query_id}/export")
def export_query(
    query_id: str,
    req: ExportRequest = ExportRequest(),
    session: Session = Depends(get_session),
) -> Response:
    row = session.get(QueryRow, query_id)
    if row is None:
        raise api_error("NOT_FOUND", f"Query {query_id} not found", 404)

    if row.status != "completed":
        raise api_error(
            "QUERY_NOT_COMPLETED",
            f"Query {query_id} is not completed (status={row.status}).",
            400,
        )

    export_format = req.format if req.format in ("csv", "xlsx") else "csv"

    dataset_row = session.get(DatasetRow, row.dataset_id)
    if dataset_row is None:
        raise api_error("NOT_FOUND", f"Dataset {row.dataset_id} not found", 404)

    if not row.generated_code:
        raise api_error(
            "NO_DATAFRAME_RESULT",
            "Query has no generated code to re-execute for export.",
            400,
        )

    try:
        content, filename, content_type = export_query_result(
            row.generated_code, dataset_row.storage_path, dataset_row.file_type, export_format
        )
    except NoDataframeResultError as exc:
        raise api_error("NO_DATAFRAME_RESULT", str(exc), 400) from exc
    except DatasetUnavailableError as exc:
        raise api_error("EXPORT_FAILED", str(exc), 500) from exc

    return Response(
        content=content,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
