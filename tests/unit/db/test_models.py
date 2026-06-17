import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from data_analysis_agent.db.models import (
    Base, DataSourceRow, ToolRow, ToolCapabilityRow,
    SessionRow, SessionDataSourceRow, QueryRecordRow, AgentRunRow,
)


@pytest.fixture
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/test.db")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def test_create_datasource(db):
    ds = DataSourceRow(name="sales.csv", type="csv")
    db.add(ds)
    db.commit()
    assert ds.id is not None
    assert ds.name == "sales.csv"


def test_datasource_column_names(db):
    ds = DataSourceRow(name="data.csv", type="csv")
    ds.column_names = ["a", "b", "c"]
    db.add(ds)
    db.commit()
    db.refresh(ds)
    assert ds.column_names == ["a", "b", "c"]


def test_create_tool_and_capability(db):
    ds = DataSourceRow(name="data.csv", type="csv")
    db.add(ds)
    db.flush()

    tool = ToolRow(
        data_source_id=ds.id,
        name="csv_query",
        type="csv_query",
        description="Run SQL queries",
    )
    db.add(tool)
    db.flush()

    cap = ToolCapabilityRow(
        tool_id=tool.id,
        name="run_query",
        description="Execute SQL SELECT",
        parameter_schema_json='{"query": {"type": "string"}}',
    )
    db.add(cap)
    db.commit()

    assert cap.id is not None
    assert cap.parameter_schema["query"]["type"] == "string"


def test_create_session_and_query_record(db):
    ds = DataSourceRow(name="data.csv", type="csv")
    db.add(ds)
    db.flush()

    sess = SessionRow(name="Test session")
    db.add(sess)
    db.flush()

    db.add(SessionDataSourceRow(session_id=sess.id, data_source_id=ds.id))
    db.flush()

    qr = QueryRecordRow(session_id=sess.id, question="What is the average?")
    db.add(qr)
    db.commit()
    assert qr.id is not None
    assert qr.status == "pending"


def test_session_many_datasources(db):
    ds1 = DataSourceRow(name="sales.csv", type="csv")
    ds2 = DataSourceRow(name="customers.csv", type="csv")
    db.add_all([ds1, ds2])
    db.flush()

    sess = SessionRow(name="Multi-source session")
    db.add(sess)
    db.flush()

    db.add(SessionDataSourceRow(session_id=sess.id, data_source_id=ds1.id))
    db.add(SessionDataSourceRow(session_id=sess.id, data_source_id=ds2.id))
    db.commit()

    links = db.query(SessionDataSourceRow).filter_by(session_id=sess.id).all()
    assert len(links) == 2


def test_create_agent_run(db):
    ds = DataSourceRow(name="data.csv", type="csv")
    db.add(ds)
    db.flush()
    sess = SessionRow()
    db.add(sess)
    db.flush()
    db.add(SessionDataSourceRow(session_id=sess.id, data_source_id=ds.id))
    db.flush()
    qr = QueryRecordRow(session_id=sess.id, question="Q")
    db.add(qr)
    db.flush()
    run = AgentRunRow(query_record_id=qr.id)
    db.add(run)
    db.commit()
    assert run.id is not None
    assert run.status == "pending"
