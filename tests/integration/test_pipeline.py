"""Integration tests — require a real Gemini key (AGENT_GEMINI_API_KEY in .env).

These exercise the full HTTP flow: POST /sessions -> POST datasets -> POST
queries -> poll GET /queries/{id}, against a real >=5,000-row CSV fixture with
a pre-computed expected answer, so a sampled/truncated implementation would
fail these assertions.
"""
import io
import re
import time
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from config.settings import get_settings
from db import session as session_module
from db.models import QueryRow

LARGE_ROW_COUNT = 5000


@pytest.fixture(autouse=True)
def _use_gemini_provider(monkeypatch):
    """This project is tuned for and gated against Gemini (spec/architecture.md);
    force provider selection even if an Anthropic key also happens to be set."""
    monkeypatch.setenv("AGENT_LLM_PROVIDER", "gemini")
    import config.settings as m
    m._settings = None
    yield
    m._settings = None


@pytest.fixture(autouse=True)
def _require_gemini_key():
    if not get_settings().gemini_api_key:
        pytest.skip("AGENT_GEMINI_API_KEY not set in .env — required for real-provider integration tests")


def _poll_query(api_client, query_id: str, timeout: float = 90.0) -> dict:
    deadline = time.monotonic() + timeout
    data = None
    while time.monotonic() < deadline:
        r = api_client.get(f"/queries/{query_id}")
        data = r.json()["data"]
        if data["status"] in ("completed", "failed"):
            return data
        time.sleep(0.25)
    pytest.fail(f"Query {query_id} did not reach a terminal status within {timeout}s: {data}")


def _extract_number(text: str | None) -> float | None:
    if not text:
        return None
    match = re.search(r"[-+]?\d[\d,]*\.?\d*", text)
    if not match:
        return None
    return float(match.group(0).replace(",", ""))


def _make_large_csv() -> tuple[bytes, float]:
    categories = ["food", "travel", "rent"]
    lines = ["id,amount,category,secret_marker"]
    for i in range(1, LARGE_ROW_COUNT + 1):
        lines.append(f"{i},{float(i)},{categories[i % 3]},secret-row-value-{i}")
    content = ("\n".join(lines) + "\n").encode("utf-8")
    expected_mean = sum(range(1, LARGE_ROW_COUNT + 1)) / LARGE_ROW_COUNT
    return content, expected_mean


def _create_session_and_dataset(api_client, csv_bytes: bytes) -> tuple[str, str]:
    session_id = api_client.post("/sessions").json()["data"]["session_id"]
    upload = api_client.post(
        f"/sessions/{session_id}/datasets",
        files={"file": ("large.csv", io.BytesIO(csv_bytes), "text/csv")},
    ).json()["data"]
    return session_id, upload["dataset_id"]


def test_full_pipeline_computes_correct_answer_over_full_dataset(api_client):
    csv_bytes, expected_mean = _make_large_csv()
    session_id, dataset_id = _create_session_and_dataset(api_client, csv_bytes)

    r = api_client.post(
        f"/sessions/{session_id}/queries",
        json={
            "dataset_id": dataset_id,
            "question": "What is the average of the amount column? State the exact numeric average.",
        },
    )
    assert r.status_code == 200
    query_id = r.json()["data"]["query_id"]

    data = _poll_query(api_client, query_id)

    assert data["status"] == "completed", data.get("error")
    assert data["generated_code"]
    assert data["token_usage"] and data["token_usage"]["total_tokens"] > 0

    number = _extract_number(data["answer_text"])
    assert number is not None, data["answer_text"]
    # The full dataset's true mean is 2500.5 — a sampled/truncated
    # implementation would compute a materially different value.
    assert abs(number - expected_mean) < 1.0

    with Session(session_module._engine) as s:
        row = s.get(QueryRow, query_id)
        assert row is not None
        assert row.status == "completed"
        assert row.answer_text == data["answer_text"]
        assert row.generated_code


def test_two_turn_conversation_uses_context(api_client):
    csv_bytes, _ = _make_large_csv()
    session_id, dataset_id = _create_session_and_dataset(api_client, csv_bytes)

    r1 = api_client.post(
        f"/sessions/{session_id}/queries",
        json={"dataset_id": dataset_id, "question": "What is the average of the amount column?"},
    )
    q1 = _poll_query(api_client, r1.json()["data"]["query_id"])
    assert q1["status"] == "completed", q1.get("error")

    r2 = api_client.post(
        f"/sessions/{session_id}/queries",
        json={"dataset_id": dataset_id, "question": "And what is the maximum value of that same column?"},
    )
    q2 = _poll_query(api_client, r2.json()["data"]["query_id"])
    assert q2["status"] == "completed", q2.get("error")

    number = _extract_number(q2["answer_text"])
    assert number is not None, q2["answer_text"]
    assert abs(number - LARGE_ROW_COUNT) < 1.0

    history = api_client.get(f"/sessions/{session_id}/queries").json()["data"]
    assert len(history) == 2
    assert history[0]["turn_index"] == 0
    assert history[1]["turn_index"] == 1
    assert history[1]["status"] == "completed"


def test_execution_retry_never_exceeds_one(api_client):
    csv_bytes, _ = _make_large_csv()
    session_id, dataset_id = _create_session_and_dataset(api_client, csv_bytes)

    r = api_client.post(
        f"/sessions/{session_id}/queries",
        json={
            "dataset_id": dataset_id,
            "question": (
                "What is the average of the 'amont' column? "
                "(Note: reference the column exactly as spelled here: 'amont'.)"
            ),
        },
    )
    data = _poll_query(api_client, r.json()["data"]["query_id"])

    assert data["retry_count"] in (0, 1)
    if data["status"] == "failed":
        assert data["retry_count"] == 1
        assert data["error"]
    else:
        assert data["status"] == "completed"


def test_concurrent_query_rejected_with_409(api_client):
    csv_bytes, _ = _make_large_csv()
    session_id, dataset_id = _create_session_and_dataset(api_client, csv_bytes)

    # Deterministically simulate an in-flight query at the DB layer — under
    # FastAPI's TestClient, BackgroundTasks run synchronously within the
    # request/response cycle, so a real race can't be observed here. The
    # concurrency guard itself is enforced at the API layer (spec/agent.md),
    # so exercising it directly against the DB state is the correct test.
    with Session(session_module._engine) as s:
        in_flight = QueryRow(
            session_id=session_id,
            dataset_id=dataset_id,
            turn_index=0,
            question="in flight question",
            status="running_analysis",
        )
        s.add(in_flight)
        s.commit()
        in_flight_id = in_flight.id

    r = api_client.post(
        f"/sessions/{session_id}/queries",
        json={"dataset_id": dataset_id, "question": "a new question"},
    )
    assert r.status_code == 409
    assert in_flight_id in r.json()["detail"]["message"]


def test_privacy_no_raw_row_values_reach_the_llm_prompt(api_client):
    csv_bytes, _ = _make_large_csv()
    session_id, dataset_id = _create_session_and_dataset(api_client, csv_bytes)

    captured_prompts: list[str] = []
    from llm.client import LLMClient

    original = LLMClient.call_model_with_usage

    def _spy(self, prompt, *, system=None):
        captured_prompts.append(prompt)
        if system:
            captured_prompts.append(system)
        return original(self, prompt, system=system)

    with patch.object(LLMClient, "call_model_with_usage", _spy):
        r = api_client.post(
            f"/sessions/{session_id}/queries",
            json={"dataset_id": dataset_id, "question": "What is the average of the amount column?"},
        )
        data = _poll_query(api_client, r.json()["data"]["query_id"])

    assert data["status"] == "completed", data.get("error")
    assert captured_prompts, "LLM was never called"

    combined_prompt_text = "\n".join(captured_prompts)
    # Distinctive per-row values from the high-cardinality "secret_marker"
    # column must never appear — only aggregate schema metadata may.
    assert "secret-row-value-1," not in combined_prompt_text
    assert "secret-row-value-2500" not in combined_prompt_text
    assert "secret-row-value-5000" not in combined_prompt_text
