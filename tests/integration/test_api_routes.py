"""API-level tests for the api-routes slice (Phase 1).

- POST /datasets: real CSV upload → store, profile, persist.
- GET  /datasets/{id}/profile: fetch stored profile; 404 unknown.
- POST /sessions/{id}/query: SSE stream against REAL Gemini.

Privacy: asserts no raw row values appear in the upload/profile responses.
"""

import json
import io

import pytest


CSV_TEXT = (
    "month,revenue,region\n"
    "2024-01,100.0,North\n"
    "2024-01,250.5,South\n"
    "2024-02,300.0,North\n"
    "2024-02,,South\n"
    "2024-03,420.0,East\n"
)


@pytest.fixture(autouse=True)
def _tmp_datasets_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_DATASETS_DIR", str(tmp_path / "datasets"))
    yield


def _upload(api_client, text=CSV_TEXT, name="sales.csv"):
    return api_client.post(
        "/datasets",
        files={"file": (name, io.BytesIO(text.encode()), "text/csv")},
    )


# --------------------------------------------------------------------------- #
# POST /datasets
# --------------------------------------------------------------------------- #

def test_upload_csv_returns_profile(api_client):
    r = _upload(api_client)
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["dataset_id"]
    assert data["name"] == "sales.csv"
    assert data["row_count"] == 5
    cols = data["profile"]["columns"]
    names = {c["name"] for c in cols}
    assert names == {"month", "revenue", "region"}
    rev = next(c for c in cols if c["name"] == "revenue")
    assert rev["missing"] == 1
    assert rev["min"] == 100.0
    assert rev["max"] == 420.0


def test_upload_response_contains_no_raw_rows(api_client):
    """Privacy: only aggregate stats — no raw cell values in the payload."""
    r = _upload(api_client)
    blob = json.dumps(r.json())
    # raw categorical values / specific cells must not leak
    assert "North" not in blob
    assert "South" not in blob
    assert "East" not in blob
    assert "250.5" not in blob
    assert "2024-01" not in blob


def test_upload_bad_csv_returns_400(api_client):
    r = _upload(api_client, text="", name="empty.csv")
    assert r.status_code == 400, r.text
    assert r.json()["detail"]["code"] in ("PARSE_ERROR", "INGEST_ERROR")


def test_upload_too_large_returns_413(api_client, monkeypatch):
    import data.ingest as ingest
    monkeypatch.setattr(ingest, "MAX_UPLOAD_BYTES", 10)
    # check_size uses the default arg captured at def time; pass via the module
    # default by monkeypatching the function's default through a wrapper.
    orig = ingest.check_size

    def small_cap(size_bytes, limit_bytes=10):
        return orig(size_bytes, 10)

    monkeypatch.setattr("api.datasets.check_size", small_cap)
    r = _upload(api_client)
    assert r.status_code == 413, r.text
    assert r.json()["detail"]["code"] == "TOO_LARGE"


# --------------------------------------------------------------------------- #
# GET /datasets/{id}/profile
# --------------------------------------------------------------------------- #

def test_get_profile_returns_same_shape(api_client):
    up = _upload(api_client).json()["data"]
    ds_id = up["dataset_id"]
    r = api_client.get(f"/datasets/{ds_id}/profile")
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["dataset_id"] == ds_id
    assert {c["name"] for c in data["profile"]["columns"]} == {
        "month",
        "revenue",
        "region",
    }


def test_get_profile_unknown_returns_404(api_client):
    r = api_client.get("/datasets/does-not-exist/profile")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "NOT_FOUND"


# --------------------------------------------------------------------------- #
# POST /sessions/{id}/query  (pre-stream validation)
# --------------------------------------------------------------------------- #

def test_query_blank_question_returns_400(api_client):
    up = _upload(api_client).json()["data"]
    r = api_client.post(
        f"/sessions/new/query",
        json={"dataset_id": up["dataset_id"], "question": "   "},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "BAD_REQUEST"


def test_query_missing_dataset_returns_400(api_client):
    r = api_client.post(
        "/sessions/new/query",
        json={"dataset_id": "", "question": "total revenue?"},
    )
    assert r.status_code == 400


def test_query_unknown_dataset_returns_404(api_client):
    r = api_client.post(
        "/sessions/new/query",
        json={"dataset_id": "nope", "question": "total revenue?"},
    )
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "NOT_FOUND"


# --------------------------------------------------------------------------- #
# POST /sessions/{id}/query  (REAL Gemini SSE stream)
# --------------------------------------------------------------------------- #

def test_query_streams_real_answer(api_client, _require_llm_key):
    up = _upload(api_client).json()["data"]
    ds_id = up["dataset_id"]

    events: list[tuple[str, dict]] = []
    with api_client.stream(
        "POST",
        "/sessions/new/query",
        json={"dataset_id": ds_id, "question": "What is the total revenue?"},
    ) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        cur_event = None
        for raw in resp.iter_lines():
            line = raw if isinstance(raw, str) else raw.decode()
            if line.startswith("event: "):
                cur_event = line[len("event: "):]
            elif line.startswith("data: "):
                payload = json.loads(line[len("data: "):])
                events.append((cur_event, payload))

    names = [e[0] for e in events]
    assert "step" in names, names
    assert "code" in names, names
    assert "done" in names, names
    # streamed answer chunks present and non-empty
    tokens = "".join(p.get("text", "") for n, p in events if n == "token")
    done = next(p for n, p in events if n == "done")
    assert done["status"] in ("completed", "failed")
    if done["status"] == "completed":
        assert tokens.strip(), "expected a non-empty streamed answer"
