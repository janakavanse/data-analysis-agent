import logging
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from data_analyst.db.session import get_session
from data_analyst.duckdb_service import get_duckdb_service
from data_analyst.domain.schemas import HealthResponse

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/health", response_model=HealthResponse)
def health(db: Session = Depends(get_session)) -> HealthResponse:
    sqlite_status = "ok"
    duckdb_status = "ok"
    registered_tables = 0

    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        logger.error("SQLite health check failed: %s", exc)
        sqlite_status = "error"

    try:
        svc = get_duckdb_service()
        if not svc.health_check():
            duckdb_status = "error"
        else:
            registered_tables = len(svc.list_tables())
    except Exception as exc:
        logger.error("DuckDB health check failed: %s", exc)
        duckdb_status = "error"

    overall = "ok" if sqlite_status == "ok" and duckdb_status == "ok" else "error"

    response = HealthResponse(
        status=overall,
        sqlite=sqlite_status,
        duckdb=duckdb_status,
        registered_tables=registered_tables,
    )

    if overall != "ok":
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=503, content=response.model_dump(mode="json"))  # type: ignore[return-value]

    return response
