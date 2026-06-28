"""Route shape checks that do NOT burn an LLM call (404 / 400 / validation).

The golden-path (real Gemini) journey lives in tests/e2e/test_journey.py.
These assert the error-path contract from spec/api.md.
"""

import io


def _csv_upload(api_client, name: str, body: str):
    return api_client.post(
        "/datasets",
        files={"file": (name, io.BytesIO(body.encode()), "text/csv")},
    )


# --------------------------------------------------------------------------- #
# POST /datasets
# --------------------------------------------------------------------------- #
def test_upload_non_csv_rejected_400(api_client):
    r = api_client.post(
        "/datasets",
        files={"file": ("notes.txt", io.BytesIO(b"hello"), "text/plain")},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "BAD_REQUEST"


def test_upload_unreadable_csv_rejected_400(api_client):
    # A .csv name but bytes pandas cannot parse into columns.
    r = _csv_upload(api_client, "broken.csv", "")
    assert r.status_code == 400


def test_upload_csv_returns_schema_and_row_count(api_client):
    r = _csv_upload(api_client, "tiny.csv", "region,amount\nWest,10\nEast,20\n")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["row_count"] == 2
    names = [c["name"] for c in data["schema"]]
    assert names == ["region", "amount"]
    assert "session_id" in data and data["filename"] == "tiny.csv"
    assert len(data["sample_rows"]) == 2


def test_upload_missing_file_field_422(api_client):
    r = api_client.post("/datasets")
    assert r.status_code == 422


# --------------------------------------------------------------------------- #
# POST /sessions/{id}/ask  (error paths only — no real question asked)
# --------------------------------------------------------------------------- #
def test_ask_unknown_session_404(api_client):
    r = api_client.post("/sessions/does-not-exist/ask", json={"question": "hi"})
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "NOT_FOUND"


def test_ask_empty_question_400(api_client):
    up = _csv_upload(api_client, "tiny.csv", "a,b\n1,2\n")
    session_id = up.json()["data"]["session_id"]
    r = api_client.post(f"/sessions/{session_id}/ask", json={"question": "   "})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "BAD_REQUEST"


def test_ask_missing_body_422(api_client):
    up = _csv_upload(api_client, "tiny.csv", "a,b\n1,2\n")
    session_id = up.json()["data"]["session_id"]
    r = api_client.post(f"/sessions/{session_id}/ask", json={})
    assert r.status_code == 422


# --------------------------------------------------------------------------- #
# GET /sessions/{id}
# --------------------------------------------------------------------------- #
def test_get_unknown_session_404(api_client):
    r = api_client.get("/sessions/nope")
    assert r.status_code == 404


def test_get_session_returns_dataset_header_and_empty_transcript(api_client):
    up = _csv_upload(api_client, "tiny.csv", "region,amount\nWest,10\nEast,20\n")
    session_id = up.json()["data"]["session_id"]
    r = api_client.get(f"/sessions/{session_id}")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["session_id"] == session_id
    assert data["dataset"]["filename"] == "tiny.csv"
    assert data["dataset"]["row_count"] == 2
    assert [c["name"] for c in data["dataset"]["schema"]] == ["region", "amount"]
    # No questions asked yet -> empty transcript.
    assert data["messages"] == []
