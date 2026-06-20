from agent.tools import sql_explorer

STUB_SENTINEL = "SQL explorer coming in v2"


def test_sql_explorer_stub():
    """sql_explorer returns the v2 stub sentinel when queried."""
    result = sql_explorer.invoke({"query": "show tables"})
    assert STUB_SENTINEL in result, f"Expected stub sentinel in: {result!r}"


def test_sql_explorer_stub_no_connection():
    """sql_explorer stub does not attempt a real database connection."""
    result = sql_explorer.invoke({})
    assert STUB_SENTINEL in result, f"Expected stub sentinel in: {result!r}"
    assert "coming in v2" in result
