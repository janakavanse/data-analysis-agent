"""API surface tests — fast unit checks, no LLM and no DB writes.

These assert the current Phase-1 app shape only: the /health envelope and that
the datasets + analyses routers are wired into the app. The live POST /analyses
round-trip (which needs an LLM key) is covered in tests/phase1.
"""


def test_health_envelope(api_client):
    r = api_client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"data": {"status": "ok"}, "error": None}


def test_app_constructs():
    from api import app  # noqa: F401  — import-time construction must not raise

    assert app is not None


def test_datasets_and_analyses_routers_registered():
    from api import app

    # The app's OpenAPI schema flattens every registered router path — this is the
    # stable way to assert the Phase-1 surface is wired (route objects vary by the
    # installed FastAPI's include_router internals).
    paths = set(app.openapi()["paths"].keys())
    # datasets router
    assert "/datasets" in paths
    assert "/datasets/{dataset_id}" in paths
    # analyses router
    assert "/analyses" in paths
    assert "/analyses/{run_id}" in paths
    # health
    assert "/health" in paths
