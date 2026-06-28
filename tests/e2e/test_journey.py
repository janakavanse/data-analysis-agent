"""Golden-path end-to-end journey against the REAL Gemini API.

Skips when no LLM key is set. Walks the full primary journey through the
FastAPI app via TestClient against an isolated tmp SQLite DB (the autouse
``_isolated_db`` fixture), and ASSERTS RESPONSE CONTENT — not just status
codes. The computed answer is checked numerically against a direct pandas
computation on the same data, proving the full-data (not sampled) path.
"""

import io

import pandas as pd
import pytest

# ≥ a handful of rows with a clear numeric column to ask about.
_CSV = (
    "region,amount\n"
    "West,10\n"
    "East,20\n"
    "West,30\n"
    "East,40\n"
    "North,50\n"
    "South,60\n"
)
_EXPECTED_AVG = 35.0  # mean of 10,20,30,40,50,60


def _upload(api_client) -> dict:
    r = api_client.post(
        "/datasets",
        files={"file": ("sales.csv", io.BytesIO(_CSV.encode()), "text/csv")},
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]


def test_full_journey_real_gemini(api_client, _require_llm_key):
    # Sanity: the direct full-data pandas answer we will compare against.
    df = pd.read_csv(io.StringIO(_CSV))
    assert float(df["amount"].mean()) == _EXPECTED_AVG

    # 1) Upload -> session + correct schema/row_count.
    data = _upload(api_client)
    session_id = data["session_id"]
    assert data["row_count"] == 6
    assert [c["name"] for c in data["schema"]] == ["region", "amount"]
    assert data["filename"] == "sales.csv"

    # 2) Ask a real question -> completed, with the work shown + correct number.
    r = api_client.post(
        f"/sessions/{session_id}/ask",
        json={"question": "What is the average of the amount column?"},
    )
    assert r.status_code == 200, r.text
    ask = r.json()["data"]
    assert ask["status"] == "completed", ask
    assert ask["answer"], "answer must be non-empty"
    assert ask["code"], "code (the work shown) must be non-empty"
    assert ask["result_table"] is not None, "result_table must be present"

    # The computed number must match the full-data pandas mean (35), not a
    # sampled approximation. The mean may surface as a scalar value or in a
    # one-cell table — check both shapes for 35.
    found = _result_contains_value(ask["result_table"], _EXPECTED_AVG)
    assert found, f"expected {_EXPECTED_AVG} in result_table {ask['result_table']!r}"

    # 3) Load the transcript -> user + assistant turns preserved with the work.
    r = api_client.get(f"/sessions/{session_id}")
    assert r.status_code == 200, r.text
    sess = r.json()["data"]
    assert sess["session_id"] == session_id
    assert sess["dataset"]["filename"] == "sales.csv"
    assert sess["dataset"]["row_count"] == 6

    msgs = sess["messages"]
    roles = [m["role"] for m in msgs]
    assert "user" in roles and "assistant" in roles
    user_msg = next(m for m in msgs if m["role"] == "user")
    assistant_msg = next(m for m in msgs if m["role"] == "assistant")
    assert "average" in user_msg["content"].lower()
    assert assistant_msg["content"]  # the answer text
    assert assistant_msg["code"], "assistant code preserved in transcript"
    assert assistant_msg["result_table"] is not None
    assert assistant_msg["status"] == "completed"


def test_ask_unknown_session_is_404(api_client):
    r = api_client.post("/sessions/missing/ask", json={"question": "hi"})
    assert r.status_code == 404


def test_upload_non_csv_is_400(api_client):
    r = api_client.post(
        "/datasets",
        files={"file": ("notes.txt", io.BytesIO(b"data"), "text/plain")},
    )
    assert r.status_code == 400


def test_empty_question_is_400(api_client):
    up = _upload_no_llm(api_client)
    r = api_client.post(f"/sessions/{up}/ask", json={"question": ""})
    assert r.status_code == 400


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _upload_no_llm(api_client) -> str:
    """Upload without requiring the LLM (used by error-path tests)."""
    r = api_client.post(
        "/datasets",
        files={"file": ("sales.csv", io.BytesIO(_CSV.encode()), "text/csv")},
    )
    assert r.status_code == 200, r.text
    return r.json()["data"]["session_id"]


def _result_contains_value(result_table: dict, expected: float) -> bool:
    """True if ``expected`` (within tolerance) appears anywhere in the result."""
    if not isinstance(result_table, dict):
        return False

    def _close(x) -> bool:
        try:
            return abs(float(x) - expected) < 1e-6
        except (TypeError, ValueError):
            return False

    if "value" in result_table and _close(result_table["value"]):
        return True
    for row in result_table.get("rows") or []:
        cells = row if isinstance(row, (list, tuple)) else [row]
        if any(_close(c) for c in cells):
            return True
    return False
