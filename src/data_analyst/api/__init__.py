from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles


@asynccontextmanager
async def _lifespan(app: FastAPI):
    from data_analyst.db.session import init_db
    from data_analyst.duckdb_service import get_duckdb_service
    from data_analyst.db.session import create_db_session

    init_db()

    svc = get_duckdb_service()
    with create_db_session() as db:
        svc.register_all_datasets(db)

    yield


def create_app() -> FastAPI:
    application = FastAPI(
        title="Data Analyst Agent",
        version="0.1.0",
        lifespan=_lifespan,
    )

    from data_analyst.api import health, datasets, chat, sessions

    application.include_router(health.router)
    application.include_router(datasets.router)
    application.include_router(chat.router)
    application.include_router(sessions.router)

    # Serve the frontend SPA at "/"
    static_dir = Path(__file__).parent.parent.parent / "static"
    if static_dir.exists():
        application.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

    return application


app = create_app()
