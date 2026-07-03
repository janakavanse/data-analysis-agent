"""API contract tests — no LLM key required, graph is not invoked."""
import io

from unittest.mock import patch


def test_health(api_client):
    r = api_client.get("/health")
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "ok"


def test_create_session_returns_id_and_created_at(api_client):
    r = api_client.post("/sessions")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["session_id"]
    assert data["created_at"]


def test_upload_dataset_returns_schema(api_client):
    session_id = api_client.post("/sessions").json()["data"]["session_id"]

    csv_bytes = b"amount,category\n10,food\n20,travel\n30,food\n"
    r = api_client.post(
        f"/sessions/{session_id}/datasets",
        files={"file": ("expenses.csv", io.BytesIO(csv_bytes), "text/csv")},
    )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["dataset_id"]
    assert data["file_type"] == "csv"
    assert data["row_count"] == 3
    assert data["column_count"] == 2
    names = {c["name"] for c in data["schema"]}
    assert names == {"amount", "category"}


def test_upload_dataset_rejects_unsupported_extension(api_client):
    session_id = api_client.post("/sessions").json()["data"]["session_id"]
    r = api_client.post(
        f"/sessions/{session_id}/datasets",
        files={"file": ("data.txt", io.BytesIO(b"not a real file"), "text/plain")},
    )
    assert r.status_code == 400


def test_upload_dataset_rejects_empty_file(api_client):
    session_id = api_client.post("/sessions").json()["data"]["session_id"]
    r = api_client.post(
        f"/sessions/{session_id}/datasets",
        files={"file": ("empty.csv", io.BytesIO(b""), "text/csv")},
    )
    assert r.status_code == 400


def test_upload_dataset_unknown_session_404(api_client):
    r = api_client.post(
        "/sessions/nonexistent/datasets",
        files={"file": ("a.csv", io.BytesIO(b"a,b\n1,2\n"), "text/csv")},
    )
    assert r.status_code == 404


def test_get_dataset_roundtrip(api_client):
    session_id = api_client.post("/sessions").json()["data"]["session_id"]
    upload = api_client.post(
        f"/sessions/{session_id}/datasets",
        files={"file": ("a.csv", io.BytesIO(b"a,b\n1,2\n3,4\n"), "text/csv")},
    ).json()["data"]

    r = api_client.get(f"/sessions/{session_id}/datasets/{upload['dataset_id']}")
    assert r.status_code == 200
    assert r.json()["data"]["dataset_id"] == upload["dataset_id"]


def test_get_dataset_not_found(api_client):
    session_id = api_client.post("/sessions").json()["data"]["session_id"]
    r = api_client.get(f"/sessions/{session_id}/datasets/nonexistent")
    assert r.status_code == 404


def test_create_query_empty_question_rejected(api_client):
    session_id = api_client.post("/sessions").json()["data"]["session_id"]
    dataset_id = api_client.post(
        f"/sessions/{session_id}/datasets",
        files={"file": ("a.csv", io.BytesIO(b"a,b\n1,2\n"), "text/csv")},
    ).json()["data"]["dataset_id"]

    r = api_client.post(
        f"/sessions/{session_id}/queries",
        json={"dataset_id": dataset_id, "question": "   "},
    )
    assert r.status_code == 400


def test_create_query_unknown_dataset_404(api_client):
    session_id = api_client.post("/sessions").json()["data"]["session_id"]
    r = api_client.post(
        f"/sessions/{session_id}/queries",
        json={"dataset_id": "nonexistent", "question": "what is the average?"},
    )
    assert r.status_code == 404


def test_create_query_dataset_mismatch_400(api_client):
    session_a = api_client.post("/sessions").json()["data"]["session_id"]
    session_b = api_client.post("/sessions").json()["data"]["session_id"]
    dataset_id = api_client.post(
        f"/sessions/{session_a}/datasets",
        files={"file": ("a.csv", io.BytesIO(b"a,b\n1,2\n"), "text/csv")},
    ).json()["data"]["dataset_id"]

    r = api_client.post(
        f"/sessions/{session_b}/queries",
        json={"dataset_id": dataset_id, "question": "what is the average?"},
    )
    assert r.status_code == 400


def test_create_query_kicks_off_background_task(api_client):
    session_id = api_client.post("/sessions").json()["data"]["session_id"]
    dataset_id = api_client.post(
        f"/sessions/{session_id}/datasets",
        files={"file": ("a.csv", io.BytesIO(b"a,b\n1,2\n"), "text/csv")},
    ).json()["data"]["dataset_id"]

    with patch("api.queries.run_query") as mock_run_query:
        r = api_client.post(
            f"/sessions/{session_id}/queries",
            json={"dataset_id": dataset_id, "question": "what is the average?"},
        )
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["status"] == "pending"
    assert data["turn_index"] == 0
    mock_run_query.assert_called_once()


def test_get_query_not_found(api_client):
    r = api_client.get("/queries/nonexistent-id")
    assert r.status_code == 404


def test_list_queries_unknown_session_404(api_client):
    r = api_client.get("/sessions/nonexistent/queries")
    assert r.status_code == 404


def test_list_queries_empty_thread(api_client):
    session_id = api_client.post("/sessions").json()["data"]["session_id"]
    r = api_client.get(f"/sessions/{session_id}/queries")
    assert r.status_code == 200
    assert r.json()["data"] == []
