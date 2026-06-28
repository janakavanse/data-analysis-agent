"""API wiring tests — health + route registration (no LLM key required)."""


def test_health(api_client):
    r = api_client.get("/health")
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "ok"


def test_datasets_route_registered(api_client):
    # missing multipart file → 422 (route exists and validates)
    r = api_client.post("/datasets")
    assert r.status_code == 422


def test_query_route_registered(api_client):
    # blank body → pre-stream 400 from the query router
    r = api_client.post("/sessions/new/query", json={})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "BAD_REQUEST"
