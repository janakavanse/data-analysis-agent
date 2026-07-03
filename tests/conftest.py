import pytest


@pytest.fixture(autouse=True)
def _reset_settings_singleton():
    import config.settings as m
    m._settings = None
    yield
    m._settings = None


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from db.models import Base
    import db.session as session_module

    engine = create_engine(f"sqlite:///{tmp_path}/test.db")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(session_module, "_engine", engine)
    monkeypatch.setattr(session_module, "_SessionLocal", factory)
    monkeypatch.setattr(session_module, "init_db", lambda: None)
    yield engine
    engine.dispose()


@pytest.fixture
def _require_llm_key():
    """Skip if no LLM provider key is set — works for Anthropic or Gemini."""
    from config.settings import get_settings
    s = get_settings()
    if not s.anthropic_api_key and not s.gemini_api_key:
        pytest.skip("No LLM key set in .env (AGENT_ANTHROPIC_API_KEY or AGENT_GEMINI_API_KEY)")


@pytest.fixture
def api_client(_isolated_db):
    """FastAPI test client with isolated DB."""
    from fastapi.testclient import TestClient
    from api import app
    with TestClient(app) as client:
        yield client


@pytest.fixture(autouse=True)
def _isolated_uploads(tmp_path, monkeypatch):
    """Redirect uploaded-file storage to a per-test temp directory so tests
    never write into the real data/uploads/ directory."""
    import analysis.storage as storage_module

    uploads_root = tmp_path / "uploads"
    monkeypatch.setattr(storage_module, "_uploads_root", lambda: uploads_root)
    yield uploads_root


@pytest.fixture
def sample_csv(tmp_path):
    """A small, deterministic CSV fixture with a pre-computed expected mean."""
    import csv

    path = tmp_path / "sample.csv"
    rows = [{"id": i, "amount": float(i), "category": "a" if i % 2 == 0 else "b"} for i in range(1, 11)]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "amount", "category"])
        writer.writeheader()
        writer.writerows(rows)
    expected_mean = sum(r["amount"] for r in rows) / len(rows)
    return {"path": path, "expected_mean": expected_mean, "row_count": len(rows)}
