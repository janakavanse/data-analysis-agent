from data_analysis_agent.domain.models import DataSource, Tool, ToolCapability, Session, QueryRecord, AgentRunRecord


def test_datasource_defaults():
    ds = DataSource(name="sales.csv")
    assert ds.id is not None
    assert ds.type == "csv"
    assert ds.column_names == []
    assert ds.row_count is None


def test_tool_fields():
    t = Tool(data_source_id="abc", name="csv_query", type="csv_query", description="Run SQL queries")
    assert t.id is not None
    assert t.config == {}


def test_tool_capability_fields():
    cap = ToolCapability(tool_id="t1", name="run_query", description="Execute SQL", parameter_schema={"query": {"type": "string"}})
    assert cap.id is not None
    assert cap.parameter_schema["query"]["type"] == "string"


def test_session_defaults():
    s = Session(data_source_id="ds1")
    assert s.id is not None
    assert s.name is None


def test_query_record_defaults():
    qr = QueryRecord(session_id="s1", question="What is the total?")
    assert qr.id is not None
    assert qr.status == "pending"
    assert qr.answer is None


def test_agent_run_record_defaults():
    run = AgentRunRecord(query_record_id="xyz")
    assert run.id is not None
    assert run.status == "pending"
