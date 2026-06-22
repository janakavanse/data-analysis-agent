from contextlib import contextmanager
from collections.abc import Generator
from pathlib import Path
from sqlalchemy import create_engine, Engine, event
from sqlalchemy.orm import Session, sessionmaker
import logging

logger = logging.getLogger(__name__)

_engine: Engine | None = None
_SessionLocal: sessionmaker | None = None


def _get_engine() -> Engine:
    global _engine
    if _engine is None:
        from data_analyst.config.settings import get_settings
        url = get_settings().database_url
        # Create data/ directory if needed for SQLite
        if url.startswith("sqlite:///"):
            path = url[len("sqlite:///"):]
            if path:
                Path(path).parent.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(
            url,
            echo=False,
            connect_args={"check_same_thread": False},
        )

        @event.listens_for(_engine, "connect")
        def set_wal(dbapi_conn, _):
            dbapi_conn.execute("PRAGMA journal_mode=WAL")

    return _engine


def _get_session_factory() -> sessionmaker:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=_get_engine(), autoflush=False, autocommit=False)
    return _SessionLocal


def get_session() -> Generator[Session, None, None]:
    """FastAPI dependency."""
    with _get_session_factory()() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise


@contextmanager
def create_db_session() -> Generator[Session, None, None]:
    """Standalone — for agent runner, scripts."""
    with _get_session_factory()() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise


def init_db() -> None:
    from data_analyst.db.models import Base
    Base.metadata.create_all(bind=_get_engine())
