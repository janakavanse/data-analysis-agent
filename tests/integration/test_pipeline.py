"""Integration test: stubbed pipeline runs end-to-end with no OpenRouter key."""
import csv
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import data_analysis_agent.db.session as session_module
from data_analysis_agent.db.models import (
    Base, DataSourceRow, SessionDataSourceRow, ToolRow, ToolCapabilityRow,
    SessionRow, QueryRecordRow, AgentRunRow,
)


@pytest.fixture(autouse=True)
def _stub_env(monkeypatch):
    monkeypatch.setenv("DATAANALYSIS_DATABASE_URL", "sqlite:///stub_test.db")
    monkeypatch.setenv("DATAANALYSIS_OPENROUTER_API_KEY", "")


@pytest.fixture(autouse=True)
def _use_sqlite(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    monkeypatch.setattr(session_module, "_engine", engine)
    monkeypatch.setattr(session_module, "_SessionLocal", factory)
    monkeypatch.setattr(session_module, "init_db", lambda: None)

    yield

    engine.dispose()
    monkeypatch.setattr(session_module, "_engine", None)
    monkeypatch.setattr(session_module, "_SessionLocal", None)


@pytest.fixture
def csv_file(tmp_path):
    path = tmp_path / "sample.csv"
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["region", "sales", "units"])
        writer.writerow(["North", 10000, 50])
        writer.writerow(["South", 8000, 40])
        writer.writerow(["East", 12000, 60])
    return str(path)


@pytest.fixture
def session_and_query(csv_file):
    with session_module.create_db_session() as db:
        ds = DataSourceRow(name="sample.csv", type="csv", file_path=csv_file)
        db.add(ds)
        db.flush()

        tool = ToolRow(
            data_source_id=ds.id,
            name="csv_query",
            type="csv_query",
            description="Execute SQL SELECT queries against the dataset.",
            config_json=json.dumps({"table_name": "sample"}),
        )
        db.add(tool)
        db.flush()

        cap = ToolCapabilityRow(
            tool_id=tool.id,
            name="run_query",
            description="Execute a SQL SELECT statement. Table name is 'sample'.",
            parameter_schema_json=json.dumps({"query": {"type": "string"}}),
        )
        db.add(cap)
        db.flush()

        sess = SessionRow(name="Test session")
        db.add(sess)
        db.flush()

        db.add(SessionDataSourceRow(session_id=sess.id, data_source_id=ds.id))
        db.flush()

        qr = QueryRecordRow(session_id=sess.id, question="What is the total sales?")
        db.add(qr)
        db.flush()

        return sess.id, qr.id


def test_pipeline_runs_end_to_end(session_and_query):
    from data_analysis_agent.graph.runner import run_pipeline

    import data_analysis_agent.llm.client as llm_module
    llm_module._client = None

    session_id, query_record_id = session_and_query
    final_state = run_pipeline(
        query_record_id=query_record_id,
        session_id=session_id,
        question="What is the total sales?",
    )

    assert final_state.get("error") is None, f"Pipeline error: {final_state.get('error')}"

    with Session(session_module._engine) as s:
        qr = s.get(QueryRecordRow, query_record_id)
        assert qr is not None
        assert qr.status == "completed"
        assert qr.answer is not None
        assert len(qr.answer) > 0
        assert qr.iteration_count == 1

        runs = s.query(AgentRunRow).filter_by(query_record_id=query_record_id).all()
        assert len(runs) == 1
        assert runs[0].status == "completed"
