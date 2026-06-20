from agent.tools import multi_source_fetch

STUB_SENTINEL = "Multi-source analysis coming in v3"


def test_multi_source_stub():
    """multi_source_fetch returns the v3 stub sentinel when invoked."""
    result = multi_source_fetch.invoke({"source": "google-sheets://example"})
    assert STUB_SENTINEL in result, f"Expected stub sentinel in: {result!r}"


def test_multi_source_stub_no_http():
    """multi_source_fetch stub does not make any external HTTP requests."""
    result = multi_source_fetch.invoke({})
    assert STUB_SENTINEL in result, f"Expected stub sentinel in: {result!r}"
    assert "coming in v3" in result
