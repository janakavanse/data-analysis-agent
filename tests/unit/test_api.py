"""Top-level API smoke — no LLM key required."""


def test_health(api_client):
    r = api_client.get("/health")
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "ok"


def test_runs_endpoint_is_gone(api_client):
    """The baseline transform endpoints do not survive Phase 1 (api.md)."""
    assert api_client.post("/runs", json={"input_text": "x"}).status_code == 404
    assert api_client.get("/runs/whatever").status_code == 404
