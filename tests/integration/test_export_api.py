"""HTTP-level tests for POST /queries/{query_id}/export.

Most tests below mount the export router directly on a throwaway FastAPI app
(hand-crafted `generated_code`, no LLM key required — export re-executes
already-stored code, no new LLM call). The final test in this file exercises
the FULL wired app (`api.export.router` is included in `create_app()`) with a
real Gemini `generate_code` call end-to-end, to catch prompt-behavior
regressions (e.g. the model itself re-introducing a row cap) that
hand-crafted `generated_code` strings can't catch.
"""
import io
import re
import time

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.export import router as export_router
from config.settings import get_settings
from db.models import DatasetRow, QueryRow, SessionRow
from db import session as session_module

LARGE_ROW_COUNT = 6000


@pytest.fixture
def export_client(_isolated_db):
    app = FastAPI()
    app.include_router(export_router)
    with TestClient(app) as client:
        yield client


def _make_large_csv_path(tmp_path):
    df = pd.DataFrame(
        {
            "id": range(1, LARGE_ROW_COUNT + 1),
            "amount": [float(i) for i in range(1, LARGE_ROW_COUNT + 1)],
        }
    )
    path = tmp_path / "large.csv"
    df.to_csv(path, index=False)
    return path, df


def _seed_query(tmp_path, generated_code: str, status: str = "completed") -> str:
    csv_path, _df = _make_large_csv_path(tmp_path)
    with Session(session_module._engine) as s:
        sess_row = SessionRow()
        s.add(sess_row)
        s.flush()

        dataset_row = DatasetRow(
            session_id=sess_row.id,
            original_filename="large.csv",
            storage_path=str(csv_path),
            file_type="csv",
            row_count=LARGE_ROW_COUNT,
            column_count=2,
            schema_json="[]",
        )
        s.add(dataset_row)
        s.flush()

        query_row = QueryRow(
            session_id=sess_row.id,
            dataset_id=dataset_row.id,
            turn_index=0,
            question="show rows where amount > 100",
            status=status,
            generated_code=generated_code,
        )
        s.add(query_row)
        s.commit()
        return query_row.id


def test_export_csv_matches_independently_recomputed_row_count(tmp_path, export_client):
    code = (
        "filtered = df[df['amount'] > 100]\n"
        "answer = f'{len(filtered)} rows matched.'\n"
        "table = filtered\n"
    )
    query_id = _seed_query(tmp_path, code)
    expected_rows = LARGE_ROW_COUNT - 100  # amounts 101..6000

    r = export_client.post(f"/queries/{query_id}/export", json={"format": "csv"})

    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert 'filename="export.csv"' in r.headers["content-disposition"]

    exported_df = pd.read_csv(io.BytesIO(r.content))
    assert len(exported_df) == expected_rows


def test_export_csv_for_chart_generating_code_using_px_go(tmp_path, export_client):
    """A previously-audited query whose generated_code references px/go to
    build an optional chart must still export successfully (bug regression:
    export's restricted globals were missing go/px)."""
    code = (
        "filtered = df[df['amount'] > 100]\n"
        "answer = f'{len(filtered)} rows matched.'\n"
        "table = filtered\n"
        "chart = px.histogram(filtered, x='amount')\n"
        "fig2 = go.Figure()\n"
    )
    query_id = _seed_query(tmp_path, code)
    expected_rows = LARGE_ROW_COUNT - 100

    r = export_client.post(f"/queries/{query_id}/export", json={"format": "csv"})

    assert r.status_code == 200
    exported_df = pd.read_csv(io.BytesIO(r.content))
    assert len(exported_df) == expected_rows


def test_export_xlsx_format(tmp_path, export_client):
    code = (
        "filtered = df[df['amount'] > 100]\n"
        "answer = f'{len(filtered)} rows matched.'\n"
        "table = filtered\n"
    )
    query_id = _seed_query(tmp_path, code)

    r = export_client.post(f"/queries/{query_id}/export", json={"format": "xlsx"})

    assert r.status_code == 200
    assert "spreadsheet" in r.headers["content-type"]
    assert 'filename="export.xlsx"' in r.headers["content-disposition"]


def test_export_defaults_to_csv_when_format_omitted(tmp_path, export_client):
    code = "table = df\nanswer = 'ok'\n"
    query_id = _seed_query(tmp_path, code)

    r = export_client.post(f"/queries/{query_id}/export", json={})

    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")


def test_export_scalar_only_result_returns_400(tmp_path, export_client):
    code = "answer = 'the total is 42'\n"
    query_id = _seed_query(tmp_path, code)

    r = export_client.post(f"/queries/{query_id}/export", json={"format": "csv"})

    assert r.status_code == 400
    body = r.json()
    assert body["detail"]["code"] == "NO_DATAFRAME_RESULT"


def test_export_nonexistent_query_returns_404(export_client):
    r = export_client.post("/queries/does-not-exist/export", json={"format": "csv"})

    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "NOT_FOUND"


def test_export_non_completed_query_returns_400(tmp_path, export_client):
    code = "table = df\nanswer = 'ok'\n"
    query_id = _seed_query(tmp_path, code, status="running_analysis")

    r = export_client.post(f"/queries/{query_id}/export", json={"format": "csv"})

    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "QUERY_NOT_COMPLETED"


def test_export_dataset_file_moved_returns_500(tmp_path, export_client):
    code = "table = df\nanswer = 'ok'\n"
    query_id = _seed_query(tmp_path, code)

    # Simulate the dataset file having moved/been deleted since the run.
    with Session(session_module._engine) as s:
        row = s.get(QueryRow, query_id)
        dataset_row = s.get(DatasetRow, row.dataset_id)
        import os

        os.remove(dataset_row.storage_path)

    r = export_client.post(f"/queries/{query_id}/export", json={"format": "csv"})

    assert r.status_code == 500
    assert r.json()["detail"]["code"] == "EXPORT_FAILED"


@pytest.fixture(autouse=True)
def _use_gemini_provider_for_real_llm_test(monkeypatch):
    monkeypatch.setenv("AGENT_LLM_PROVIDER", "gemini")
    import config.settings as m
    m._settings = None
    yield
    m._settings = None


def _poll_query(client, query_id: str, timeout: float = 90.0) -> dict:
    deadline = time.monotonic() + timeout
    data = None
    while time.monotonic() < deadline:
        r = client.get(f"/queries/{query_id}")
        data = r.json()["data"]
        if data["status"] in ("completed", "failed", "needs_clarification", "unanswerable"):
            return data
        time.sleep(0.25)
    pytest.fail(f"Query {query_id} did not reach a terminal status within {timeout}s: {data}")


def test_real_gemini_filtering_question_exports_full_uncapped_rows(tmp_path):
    """End-to-end regression test against the real prompt/model behavior
    (not hand-crafted generated_code): asks a real filtering question over a
    large fixture via the actual pipeline, then exports the result and
    asserts the exported row count is the FULL matching count, not capped at
    50. Requires AGENT_GEMINI_API_KEY in .env."""
    if not get_settings().gemini_api_key:
        pytest.skip("AGENT_GEMINI_API_KEY not set in .env — required for real-provider integration test")

    from api import create_app

    n = 6000
    categories = ["food", "travel", "rent"]
    lines = ["id,amount,category"]
    for i in range(1, n + 1):
        lines.append(f"{i},{float(i)},{categories[i % 3]}")
    csv_bytes = ("\n".join(lines) + "\n").encode("utf-8")
    expected_matching = sum(1 for i in range(1, n + 1) if float(i) > 100)
    assert expected_matching > 50

    app = create_app()
    with TestClient(app) as client:
        session_id = client.post("/sessions").json()["data"]["session_id"]
        upload = client.post(
            f"/sessions/{session_id}/datasets",
            files={"file": ("large.csv", io.BytesIO(csv_bytes), "text/csv")},
        ).json()["data"]
        dataset_id = upload["dataset_id"]

        r = client.post(
            f"/sessions/{session_id}/queries",
            json={
                "dataset_id": dataset_id,
                "question": "Show me all rows where amount is greater than 100, as a table.",
            },
        )
        assert r.status_code == 200
        query_id = r.json()["data"]["query_id"]

        data = _poll_query(client, query_id)
        assert data["status"] == "completed", data.get("error")

        export_response = client.post(f"/queries/{query_id}/export", json={"format": "csv"})
        assert export_response.status_code == 200, export_response.json()

        exported_df = pd.read_csv(io.BytesIO(export_response.content))
        assert len(exported_df) == expected_matching, (
            f"Exported {len(exported_df)} rows but expected {expected_matching} "
            "— the export path (or the model's generated code) is capping rows."
        )
