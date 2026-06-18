from contextlib import asynccontextmanager
from fastapi import FastAPI


@asynccontextmanager
async def _lifespan(app: FastAPI):
    from <package>.db.session import init_db
    init_db()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="<Agent Name>", version="0.1.0", lifespan=_lifespan)
    from <package>.api import health
    app.include_router(health.router)
    return app


app = create_app()
