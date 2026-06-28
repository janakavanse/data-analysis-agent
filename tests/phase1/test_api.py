"""Phase 1 — API contract tests for datasets + analyses.

These run the REAL surface: a real CSV is uploaded and ingested into DuckDB, then
a real question is answered by the LangGraph loop against the REAL Gemini key from
``.env``. The DB is isolated per test (conftest ``_isolated_db``) and DuckDB/parquet
are written under a tmp data dir.
"""

from __future__ import annotations

import io

import pytest

from analysis import storage


SAMPLE_CSV = (
    "month,region,amount\n"
    "2024-01,North,1200.0\n"
    "2024-01,South,800.0\n"
    "2024-02,North,1500.0\n"
    "2024-02,South,950.0\n"
    "2024-03,North,2100.0\n"
    "2024-03,South,1300.0\n"
)


@pytest.fixture
def isolated_data_dir(tmp_path, monkeypatch):
    """Point the analysis engine's DuckDB + parquet at a fresh tmp dir."""
    monkeypatch.setenv("AGENT_DATA_DIR", str(tmp_path))
    storage.reset_connection()
    yield tmp_path
    storage.reset_connection()


def _upload(api_client, csv_text: str, filename: str = "sales.csv"):
    return api_client.post(
        "/datasets",
        files={"file": (filename, io.BytesIO(csv_text.encode()), "text/csv")},
    )


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------


def test_upload_returns_schema_sample_rowcount(isolated_data_dir, api_client):
    r = _upload(api_client, SAMPLE_CSV)
    assert r.status_code == 200, r.text
    data = r.json()["data"]

    assert data["dataset_id"]
    assert data["name"] == "sales.csv"
    assert data["row_count"] == 6

    schema_names = {c["name"] for c in data["schema"]}
    assert {"month", "region", "amount"} <= schema_names
    for col in data["schema"]:
        assert "name" in col and "dtype" in col

    assert isinstance(data["sample"], list)
    assert 0 < len(data["sample"]) <= 20
    assert "month" in data["sample"][0]


def test_get_dataset_roundtrip(isolated_data_dir, api_client):
    dataset_id = _upload(api_client, SAMPLE_CSV).json()["data"]["dataset_id"]
    r = api_client.get(f"/datasets/{dataset_id}")
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["dataset_id"] == dataset_id
    assert data["row_count"] == 6


def test_upload_empty_file_is_bad_file(isolated_data_dir, api_client):
    r = _upload(api_client, "", filename="empty.csv")
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "BAD_FILE"


def test_unknown_dataset_is_404(isolated_data_dir, api_client):
    r = api_client.get("/datasets/does-not-exist")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "DATASET_NOT_FOUND"


# ---------------------------------------------------------------------------
# Analyse (REAL Gemini)
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("_require_llm_key")
def test_analyse_returns_full_payload(isolated_data_dir, api_client):
    dataset_id = _upload(api_client, SAMPLE_CSV).json()["data"]["dataset_id"]

    r = api_client.post(
        "/analyses",
        json={"dataset_id": dataset_id, "question": "What were total sales by month?"},
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]

    assert data["run_id"]
    assert data["status"] == "completed"
    # Full contract payload present.
    for key in (
        "stage",
        "answer",
        "key_numbers",
        "summary_table",
        "chart_spec",
        "code",
        "llm_payload",
        "tokens_in",
        "tokens_out",
        "cost_estimate",
        "flagged",
    ):
        assert key in data, f"missing key {key}"

    assert data["answer"] and len(data["answer"]) > 0
    assert data["code"]
    assert data["chart_spec"]
    assert data["tokens_in"] > 0
    assert data["cost_estimate"] > 0

    # GET the same run back.
    g = api_client.get(f"/analyses/{data['run_id']}")
    assert g.status_code == 200, g.text
    gd = g.json()["data"]
    assert gd["run_id"] == data["run_id"]
    # Run-detail extras present on GET.
    for key in ("started_at", "completed_at", "revisions", "error_message"):
        assert key in gd


def test_analyse_empty_question_is_400(isolated_data_dir, api_client):
    dataset_id = _upload(api_client, SAMPLE_CSV).json()["data"]["dataset_id"]
    r = api_client.post(
        "/analyses", json={"dataset_id": dataset_id, "question": "   "}
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "EMPTY_QUESTION"


def test_analyse_unknown_dataset_is_404(isolated_data_dir, api_client):
    r = api_client.post(
        "/analyses", json={"dataset_id": "nope", "question": "total sales?"}
    )
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "DATASET_NOT_FOUND"


def test_get_unknown_run_is_404(isolated_data_dir, api_client):
    r = api_client.get("/analyses/not-a-real-run")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "RUN_NOT_FOUND"
