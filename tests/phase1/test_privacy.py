"""Phase 1 — privacy boundary gate (API surface).

The LLM must only ever see schema + a tiny sample + small aggregates — never bulk
rows. This test uploads a LARGE CSV carrying a unique SENTINEL value buried in a
deep row, runs a REAL analysis, then asserts the run's serialized ``llm_payload``
contains no bulk-row leakage (the sentinel never appears) and the sample stays
bounded (<= 20 rows). This is the privacy-by-construction gate at the API edge.
"""

from __future__ import annotations

import io
import json

import pandas as pd
import pytest

from analysis import storage

LARGE_ROWS = 250_000
SENTINEL = "SENTINEL_ZZZ"
SENTINEL_ROW = 200_000


@pytest.fixture
def isolated_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_DATA_DIR", str(tmp_path))
    storage.reset_connection()
    yield tmp_path
    storage.reset_connection()


def _large_csv_bytes() -> bytes:
    """A >=250k-row CSV where SENTINEL appears ONLY in one deep row."""
    labels = [f"item_{i % 7}" for i in range(LARGE_ROWS)]
    labels[SENTINEL_ROW] = SENTINEL
    df = pd.DataFrame(
        {
            "id": range(LARGE_ROWS),
            "label": labels,
            "amount": [1.0 for _ in range(LARGE_ROWS)],
        }
    )
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode()


@pytest.mark.usefixtures("_require_llm_key")
def test_bulk_rows_never_reach_the_llm(isolated_data_dir, api_client):
    csv_bytes = _large_csv_bytes()

    up = api_client.post(
        "/datasets",
        files={"file": ("big.csv", io.BytesIO(csv_bytes), "text/csv")},
    )
    assert up.status_code == 200, up.text
    up_data = up.json()["data"]
    assert up_data["row_count"] == LARGE_ROWS
    # The upload-returned sample is itself bounded and sentinel-free.
    assert len(up_data["sample"]) <= 20
    assert SENTINEL not in json.dumps(up_data["sample"])

    dataset_id = up_data["dataset_id"]

    r = api_client.post(
        "/analyses",
        json={"dataset_id": dataset_id, "question": "What is the total amount?"},
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]

    llm_payload = data["llm_payload"]
    assert llm_payload is not None, "llm_payload must be recorded for transparency"

    serialized = json.dumps(llm_payload)
    # The deep sentinel row must NOT have leaked into the LLM context.
    assert SENTINEL not in serialized, "bulk row leaked into the LLM payload"

    # The payload sample is bounded to the privacy cap.
    sample = llm_payload.get("sample", [])
    assert isinstance(sample, list)
    assert len(sample) <= 20, "LLM sample exceeds the privacy cap"


@pytest.mark.usefixtures("_require_llm_key")
def test_llm_payload_is_persisted_and_fetchable(isolated_data_dir, api_client):
    csv_bytes = _large_csv_bytes()
    dataset_id = api_client.post(
        "/datasets",
        files={"file": ("big.csv", io.BytesIO(csv_bytes), "text/csv")},
    ).json()["data"]["dataset_id"]

    run_id = api_client.post(
        "/analyses",
        json={"dataset_id": dataset_id, "question": "Count the rows."},
    ).json()["data"]["run_id"]

    g = api_client.get(f"/analyses/{run_id}")
    assert g.status_code == 200, g.text
    assert SENTINEL not in json.dumps(g.json()["data"]["llm_payload"])
