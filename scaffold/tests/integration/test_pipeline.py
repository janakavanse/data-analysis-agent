import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from <package>.db.models import Base, RunRow
from <package>.db import session as session_module
from <package>.graph.runner import run_agent


@pytest.fixture(autouse=True)
def _use_sqlite(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path}/test.db")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(session_module, "_engine", engine)
    monkeypatch.setattr(session_module, "_SessionLocal", factory)
    monkeypatch.setattr(session_module, "init_db", lambda: None)
    yield
    engine.dispose()


@pytest.fixture(autouse=True)
def _stub_env(monkeypatch):
    monkeypatch.setenv("APP_DATABASE_URL", "sqlite:///stub.db")
    monkeypatch.setenv("APP_ANTHROPIC_API_KEY", "stub-key")


def test_pipeline_runs_end_to_end(_use_sqlite, _stub_env):
    from sqlalchemy.orm import Session
    run_id = run_agent()
    assert run_id is not None
    with Session(session_module._engine) as s:
        run = s.get(RunRow, run_id)
        assert run is not None
        assert run.status == "completed"
